"""`UX-31` · Vistas por rol: dónde aterriza cada quien y qué tiene a mano.

**La regla que estos tests protegen es una sola: nada se esconde.** Sale textual
de la fila del plan — *"ocultar genera desconfianza; priorizar genera
velocidad"*— y es lo que separa esta implementación de la que parecía más
obvia. Los permisos siguen decidiendo qué se ve; lo único que cambia por rol es
el orden y la pantalla de entrada.

Los roles son los grupos que ya crea `bootstrap_roles`, no una taxonomía nueva:
un segundo juego "para la interfaz" sería una lista paralela que se
desincroniza, y desincronizada quiere decir aterrizar donde no se tiene permiso.
"""

import pytest
from django.contrib.auth.models import Group, Permission, User
from django.urls import reverse

from apps.core.roles import ROLE_LANDING, SHORTCUT_LABELS, SHORTCUT_PERMISSIONS
from apps.core.roles import landing_url_name, role_of, shortcuts_for


def _user(*groups, permissions=()):
    # El nombre lleva un contador porque un mismo test crea dos usuarios del
    # mismo rol —uno con permiso y otro sin él— y el nombre derivado sólo de los
    # grupos chocaba con la restricción de unicidad.
    _user.n = getattr(_user, "n", 0) + 1
    user = User.objects.create_user(
        f"u{_user.n}-{'-'.join(groups) or 'none'}", password="pw"
    )
    for name in groups:
        user.groups.add(Group.objects.get_or_create(name=name)[0])
    if permissions:
        user.user_permissions.add(*Permission.objects.filter(codename__in=permissions))
    return user


class TestWhereEachRoleLands:
    @pytest.mark.django_db
    @pytest.mark.parametrize(
        ("group", "expected"),
        [
            ("Operations", "can-i-fly"),
            ("Compliance", "work-tray"),
        ],
    )
    def test_the_role_decides_the_first_screen(self, db, group, expected):
        assert landing_url_name(_user(group)) == expected

    @pytest.mark.django_db
    def test_maintenance_needs_its_permission_to_land_there(self, db):
        """⚠️ Un grupo puede quedar sin el permiso de su propia pantalla —alguien
        lo edita en el administrador— y aterrizar en un 403 es la peor forma
        posible de empezar el día. Sin permiso, el destino de siempre."""
        assert landing_url_name(_user("Maintenance")) is None
        assert (
            landing_url_name(
                _user("Maintenance", permissions=["view_maintenancerecord"])
            )
            == "maintenance-list"
        )

    @pytest.mark.django_db
    def test_without_a_role_nothing_is_decided(self, db):
        """`None` y no `"dashboard"`: así quien llama conserva su propio destino
        por defecto en vez de que este módulo se lo pise."""
        assert landing_url_name(_user()) is None
        assert landing_url_name(_user("Viewer")) is None

    @pytest.mark.django_db
    def test_two_roles_always_resolve_the_same_way(self, db):
        """⚠️ Alguien puede estar en dos grupos —pasa: quien opera y además
        revisa cumplimiento— y el orden de `groups.all()` es el que quiera el
        motor. Una pantalla de inicio que cambia sola entre dos logins es de las
        cosas que nadie reporta como defecto y todos desconfían."""
        both = _user("Compliance", "Operations")

        assert role_of(both) == next(iter(ROLE_LANDING))

    def test_anonymous_has_no_role(self):
        from django.contrib.auth.models import AnonymousUser

        assert role_of(AnonymousUser()) is None


class TestTheLoginHonoursIt:
    @pytest.mark.django_db
    def test_signing_in_lands_on_the_role_screen(self, client, db):
        user = _user("Operations")
        user.set_password("pw")
        user.save()

        response = client.post(
            reverse("login"), {"username": user.username, "password": "pw"}
        )

        assert response.url == reverse("can-i-fly")

    @pytest.mark.django_db
    def test_but_an_explicit_next_always_wins(self, client, db):
        """⚠️ Quien siguió un enlace a una ficha y tuvo que autenticarse quiere
        esa ficha, no su pantalla de rol: pisarlo convertiría cada enlace
        compartido en un viaje al inicio."""
        user = _user("Operations")
        user.set_password("pw")
        user.save()

        response = client.post(
            reverse("login") + "?next=/alerts/",
            {"username": user.username, "password": "pw"},
        )

        assert response.url == "/alerts/"


class TestNothingIsHidden:
    """La mitad que importa de la fila."""

    @pytest.mark.django_db
    def test_the_dashboard_is_still_reachable_for_every_role(self, client, db):
        """No hay redirección desde `/`. Redirigir la raíz habría vuelto el panel
        inalcanzable para tres de los cinco roles, que es esconder con otro
        nombre."""
        user = _user("Operations")
        client.force_login(user)

        response = client.get(reverse("dashboard"))

        assert response.status_code == 200

    @pytest.mark.django_db
    def test_the_full_menu_is_still_drawn(self, client, db):
        """Los atajos son un **añadido**: cada destino sigue estando más abajo,
        en su grupo de siempre."""
        client.force_login(_user("Operations"))

        body = client.get(reverse("dashboard")).content.decode()

        # El grupo de padrón no es de este rol y tiene que seguir ahí.
        assert reverse("aircraft-list") in body
        assert reverse("costcenter-list") in body

    @pytest.mark.django_db
    def test_a_user_without_a_role_sees_the_menu_of_always(self, client, db):
        client.force_login(_user())

        body = client.get(reverse("dashboard")).content.decode()

        assert "nav-shortcuts" not in body


class TestTheShortcuts:
    @pytest.mark.django_db
    def test_they_are_filtered_by_permission(self, db):
        """Un enlace que termina en 403 enseña a desconfiar de la pantalla
        (`LV-130`), así que se filtran acá y no en el HTML: un `if` por atajo
        repartido en la plantilla es un `if` que alguien olvida."""
        bare = _user("Operations")

        assert shortcuts_for(bare) == ["can-i-fly"]

    @pytest.mark.django_db
    def test_and_appear_once_the_permission_is_there(self, db):
        able = _user(
            "Operations", permissions=["view_flightpermission", "view_flightrecord"]
        )

        assert shortcuts_for(able) == ["can-i-fly", "permission-list", "record-list"]

    @pytest.mark.django_db
    def test_they_reach_the_page(self, client, db):
        client.force_login(_user("Operations"))

        body = client.get(reverse("dashboard")).content.decode()

        assert "nav-shortcuts" in body
        assert reverse("can-i-fly") in body

    def test_every_shortcut_declares_its_gate_and_its_label(self):
        """Sin `get` y sin valor por defecto en el código: un atajo nuevo sin
        entrada en estas tablas tiene que levantar en el momento, no dibujarse
        sin rótulo o sin control para siempre."""
        from apps.core.roles import ROLE_SHORTCUTS

        every = {name for names in ROLE_SHORTCUTS.values() for name in names}

        assert every <= set(SHORTCUT_PERMISSIONS)
        assert every <= set(SHORTCUT_LABELS)

    def test_the_labels_are_the_ones_the_menu_already_uses(self):
        """Dos nombres para la misma pantalla es cómo alguien cree que son dos
        pantallas."""
        from pathlib import Path

        from django.conf import settings

        base = (Path(settings.BASE_DIR) / "templates" / "base.html").read_text(
            encoding="utf-8"
        )

        for label in SHORTCUT_LABELS.values():
            assert f'{{% translate "{label}" %}}' in base, label
