"""`LV-381` F1: el menú lateral como datos, con el permiso de cada entrada.

El defecto que cierra (V5 del diseño): diecisiete enlaces del menú no llevaban
condición de permiso en la plantilla aunque sus vistas exigen `view_*`, así que
Operations, Maintenance y Compliance veían enlaces que terminaban en 403 (según
`bootstrap_roles`), y `admin:index` se mostraba a todos sin mirar `is_staff`.
`LV-130` ya lo había fijado como principio —*un enlace que falla enseña a
desconfiar de la pantalla*— y nadie lo comprobaba contra el menú entero.

El guardián que importa es el primero: **por cada rol de `bootstrap_roles`, cada
enlace que el menú dibuja responde distinto de 403.** Lo demás protege que el
registro siga diciendo la verdad sobre las vistas (`test_every_entry_asks_at_
least_what_its_view_asks`) y los casos de borde del menú (sin permisos, sin
`is_staff`, grupos vacíos).
"""

import re

import pytest
from django.contrib.auth.models import Group, Permission, User
from django.core.management import call_command
from django.test import Client
from django.urls import resolve, reverse

from apps.core.management.commands.bootstrap_roles import ROLE_PERMISSIONS
from apps.core.navigation import NAV_GROUPS, all_items, build_sidebar

LINK = re.compile(r'<a href="([^"]+)" class="nav-item (?!nav-shortcut)[^"]*"')


def _menu_hrefs(body):
    """Los enlaces del menú (no los atajos del rol) de una página renderizada."""
    sidebar = body[body.index('<aside class="sidebar') : body.index("</aside>")]
    return LINK.findall(sidebar)


def _client_for(group_name=None, *, staff=False, codenames=()):
    _client_for.n = getattr(_client_for, "n", 0) + 1
    user = User.objects.create_user(  # nosec B106 - base de datos de test
        f"nav{_client_for.n}", password="pw", is_staff=staff
    )
    if group_name:
        user.groups.add(Group.objects.get(name=group_name))
    if codenames:
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
    client = Client()
    client.force_login(user)
    client.user = user
    return client


@pytest.fixture
def roles(db):
    call_command("bootstrap_roles")


@pytest.mark.django_db
@pytest.mark.parametrize("role", sorted(ROLE_PERMISSIONS))
def test_no_menu_link_answers_403_to_the_role_that_sees_it(roles, role):
    """El guardián de V5: lo que el menú ofrece, el rol lo puede abrir."""
    client = _client_for(role)
    body = client.get(reverse("dashboard")).content.decode()
    hrefs = _menu_hrefs(body)

    assert reverse("dashboard") in hrefs  # el menú se está leyendo de verdad
    for href in hrefs:
        status = client.get(href).status_code
        assert status != 403, f"{role}: el menú ofrece {href} y responde 403"
        assert status < 500, f"{role}: {href} responde {status}"


@pytest.mark.django_db
def test_the_roles_are_the_ones_that_bootstrap_creates(roles):
    """El parametrizado de arriba recorre `ROLE_PERMISSIONS`; si un rol existe en
    la base y no ahí (o al revés), este test avisa en vez de dejar un rol sin
    revisar."""
    assert set(ROLE_PERMISSIONS) <= set(Group.objects.values_list("name", flat=True))


@pytest.mark.django_db
def test_a_user_without_permissions_sees_only_the_dashboard_and_the_work_tray(roles):
    """El panel y la bandeja sólo piden iniciar sesión (cada fuente de la bandeja
    se gatea sola). Todo lo demás exige un permiso."""
    client = _client_for()
    body = client.get(reverse("dashboard")).content.decode()

    assert _menu_hrefs(body) == [reverse("dashboard"), reverse("work-tray")]


@pytest.mark.django_db
def test_a_user_who_can_do_everything_sees_every_live_entry(db):
    user = User.objects.create_superuser("root", password="pw")  # nosec B106

    menu = build_sidebar(user, "")
    drawn = {item.key for item in (*menu.top, *menu.footer)} | {
        item.key for group in menu.groups for item in group.items
    }

    assert drawn == {item.url_name for item in all_items()}


@pytest.mark.django_db
def test_admin_index_is_only_offered_to_staff(roles):
    plain = _client_for("Administrator", codenames=["view_auditevent"])
    staff = _client_for("Administrator", staff=True, codenames=["view_auditevent"])

    plain_body = plain.get(reverse("dashboard")).content.decode()
    staff_body = staff.get(reverse("dashboard")).content.decode()

    assert reverse("admin:index") not in _menu_hrefs(plain_body)
    assert reverse("admin:index") in _menu_hrefs(staff_body)
    # El centro de administración, en cambio, va por permisos y no por `is_staff`.
    assert reverse("administration") in _menu_hrefs(plain_body)


@pytest.mark.django_db
def test_the_technical_admin_does_not_open_for_someone_who_is_not_staff(roles):
    """Django admin manda a quien no es `is_staff` al inicio de sesión del admin
    (302) y no a un 403: lo que importa es que no abre, y que el menú ya no lo
    ofrece (prueba de arriba)."""
    plain = _client_for("Administrator")

    response = plain.get(reverse("admin:index"))

    assert response.status_code == 302
    assert "/admin/login/" in response["Location"]


@pytest.mark.django_db
def test_a_group_without_any_permitted_entry_is_not_drawn(db):
    """Un título sin filas debajo es un callejón sin salida."""
    client = _client_for(codenames=["view_battery"])
    body = client.get(reverse("dashboard")).content.decode()
    sidebar = body[body.index('<aside class="sidebar') : body.index("</aside>")]

    assert 'data-nav-group="inventory"' in sidebar
    assert 'data-nav-group="flight"' not in sidebar
    assert 'data-nav-group="registry"' not in sidebar


@pytest.mark.django_db
def test_the_current_page_is_marked_even_on_its_child_screens(db):
    """`geo-plan-detail` marca «Planificación geoespacial», como siempre."""
    user = User.objects.create_superuser("root2", password="pw")  # nosec B106

    menu = build_sidebar(user, "geo-plan-detail")
    active = [
        item.key
        for item in (
            *menu.top,
            *(i for g in menu.groups for i in g.items),
            *menu.footer,
        )
        if item.active
    ]

    assert active == ["geo-plan-list"]


@pytest.mark.django_db
def test_every_permission_the_registry_names_exists(db):
    """Un typo en un permiso no falla: `has_perm` responde `False` y la entrada
    desaparece del menú para todos sin que nadie lo note."""
    named = {perm for item in all_items() for perm in item.permissions}
    named |= {perm for item in all_items() for perm in item.any_permissions}
    existing = {
        f"{app}.{code}"
        for app, code in Permission.objects.values_list(
            "content_type__app_label", "codename"
        )
    }

    assert named - existing == set()


@pytest.mark.django_db
def test_every_entry_asks_at_least_what_its_view_asks(db):
    """El registro no puede ser más flojo que la vista: es el origen de V5.

    Se instancia la clase de la vista y se le pide su permiso (`get_permission_
    required`); la entrada tiene que exigir **al menos** eso. Las vistas que sólo
    piden iniciar sesión (el panel, la bandeja, el centro de administración, que
    se gatea fila por fila) no declaran ninguno y se saltan.
    """
    checked = 0
    for item in all_items():
        if item.url_name == "admin:index" or item.dynamic_url:
            continue
        view_class = getattr(resolve(reverse(item.url_name)).func, "view_class", None)
        getter = getattr(view_class, "get_permission_required", None)
        if getter is None:
            continue
        required = set(getter(view_class()))
        assert required <= set(item.permissions), (
            f"{item.url_name}: la vista exige {sorted(required)} y la entrada "
            f"sólo {sorted(item.permissions)}"
        )
        checked += 1

    assert checked >= 15  # el guardián del guardián: no pasó en verde sin mirar


def test_every_group_key_is_unique_and_has_items():
    keys = [group.key for group in NAV_GROUPS]

    assert len(keys) == len(set(keys))
    assert all(group.items for group in NAV_GROUPS)
