"""LV-166: el permiso deja de pedir lo que el plan geoespacial provee.

Pedido del usuario el 2026-08-27: *"en el permiso de vuelo quitar región, comuna,
nombre, latitud, longitud, radio, altitud; toda información la debe sacar sí o sí
al momento de vincular el plan de vuelo, así ahorramos espacio y mejoramos el
permiso"*.

Lo que estos tests sujetan no es tanto lo que se esconde como **lo que no**. Una
lista fija de siete campos era la lectura obvia del pedido y habría escondido
casillas que nada rellena: un plan con varias circunferencias no aporta
coordenadas, y la altitud máxima no está en ningún KMZ. La regla queda atada al
valor, así que esos casos siguen a la vista porque siguen haciendo falta.
"""

from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission, User
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.geo.models import GeoPlan
from apps.operations.forms import FlightPermissionUpdateForm
from apps.operations.models import FlightPermission
from apps.registry.models import CostCenter

LOCATION_FIELDS = (
    "region",
    "commune",
    "area_name",
    "latitude",
    "longitude",
    "radius_km",
)


@pytest.fixture
def world(db):
    center = CostCenter.objects.create(code="CC738", name="Los Pelambres")
    owner = User.objects.create_user("owner", password="password")
    today = timezone.localdate()
    permission = FlightPermission.objects.create(
        cost_center=center,
        status="requested",
        purpose="survey",
        valid_from=today,
        valid_until=today.replace(year=today.year + 1),
        location="Quebrada km 13.760",
        area_type="dan_91",
    )
    return {"center": center, "owner": owner, "permission": permission}


def _plan(world, *, linked=True, active=True):
    plan = GeoPlan.objects.create(
        title="CC738 · CG-01",
        cost_center=world["center"],
        created_by=world["owner"],
        flight_permission=world["permission"] if linked else None,
        is_active=active,
    )
    return plan


def _filled(permission):
    """El permiso como queda después de que un plan de una circunferencia lo
    rellenó: es el estado que produce `link_to_permission`."""
    permission.region = "Región de Coquimbo"
    permission.commune = "Salamanca"
    permission.area_name = "Quebrada km 13.760"
    permission.latitude = Decimal("-31.918000")
    permission.longitude = Decimal("-70.949000")
    permission.radius_km = Decimal("2.396")
    permission.save()
    return permission


# -- lo que se esconde -----------------------------------------------------


def test_with_a_linked_plan_the_boxes_it_provides_are_gone(world):
    _plan(world)
    _filled(world["permission"])

    form = FlightPermissionUpdateForm(instance=world["permission"])

    for name in LOCATION_FIELDS:
        assert name not in form.fields, name
    assert sorted(form.hidden_plan_fields) == sorted(LOCATION_FIELDS)
    assert form.plan_providing_location is not None


def test_what_the_plan_never_provides_stays(world):
    """La altitud máxima no está en ningún KMZ, y `location` es el texto libre
    obligatorio que el usuario no pidió sacar. Esconderlos los dejaría sin
    ninguna forma de cargarse."""
    _plan(world)
    _filled(world["permission"])

    form = FlightPermissionUpdateForm(instance=world["permission"])

    assert "max_altitude_ft" in form.fields
    assert "location" in form.fields
    assert "area_type" in form.fields


# -- lo que NO se esconde, que es el punto ---------------------------------


def test_a_plan_that_provided_no_coordinates_leaves_them_visible(world):
    """El caso del plan multi-círculo: se vincula, el vínculo es válido, y
    `link_to_permission` **no rellena coordenadas** porque elegir una sería
    inventar cuál manda. Con una lista fija esas casillas habrían desaparecido
    dejando el permiso sin forma de declarar su punto central."""
    _plan(world)  # vinculado, pero el permiso quedó sin coordenadas

    form = FlightPermissionUpdateForm(instance=world["permission"])

    for name in LOCATION_FIELDS:
        assert name in form.fields, name
    assert form.hidden_plan_fields == []


def test_a_half_filled_permit_only_hides_what_it_has(world):
    """Mezcla real: el plan resolvió comuna y región pero el permiso no tiene
    radio. Se esconde lo que está y se pide lo que falta."""
    _plan(world)
    permission = world["permission"]
    permission.region = "Región de Coquimbo"
    permission.commune = "Salamanca"
    permission.save()

    form = FlightPermissionUpdateForm(instance=permission)

    assert "region" not in form.fields
    assert "commune" not in form.fields
    assert "latitude" in form.fields
    assert "radius_km" in form.fields


def test_without_a_plan_nothing_is_hidden(world):
    _filled(world["permission"])

    form = FlightPermissionUpdateForm(instance=world["permission"])

    for name in LOCATION_FIELDS:
        assert name in form.fields, name
    assert form.plan_providing_location is None


def test_an_archived_plan_does_not_count(world):
    """Archivar un plan lo saca de los listados; si además siguiera escondiendo
    casillas, el permiso quedaría sin ubicación editable y sin plan visible que
    lo explique."""
    _plan(world, active=False)
    _filled(world["permission"])

    form = FlightPermissionUpdateForm(instance=world["permission"])

    assert form.hidden_plan_fields == []


def test_creating_a_permit_never_hides_anything(world):
    """En el alta el plan se elige en el mismo formulario, así que todavía no hay
    nada de dónde sacar el dato -- y el relleno ocurre al guardar (LV-153)."""
    from apps.operations.forms import FlightPermissionForm

    form = FlightPermissionForm()

    for name in LOCATION_FIELDS:
        assert name in form.fields, name
    assert form.hidden_plan_fields == []


# -- la puerta del papel de la DGAC ----------------------------------------


def test_the_manual_override_brings_them_back(world):
    """`fill_location_gaps` rellena **sin pisar** porque una resolución de la
    DGAC puede traer otra coordenada y tiene más autoridad que lo que se preparó
    antes de presentar. Si esconder los campos cerrara ese camino, el permiso no
    podría reflejar el papel."""
    _plan(world)
    _filled(world["permission"])

    form = FlightPermissionUpdateForm(
        instance=world["permission"], manual_location=True
    )

    for name in LOCATION_FIELDS:
        assert name in form.fields, name
    assert form.hidden_plan_fields == []


@pytest.mark.django_db
def test_the_edit_screen_offers_the_override_and_honours_it(world):
    _plan(world)
    _filled(world["permission"])
    user = User.objects.create_user("editor", password="password")
    for codename in ("change_flightpermission", "view_flightpermission"):
        user.user_permissions.add(Permission.objects.get(codename=codename))
    client = Client()
    assert client.login(username="editor", password="password")
    url = reverse("permission-update", args=[world["permission"].pk])

    plain = client.get(url)
    body = plain.content.decode()
    assert plain.status_code == 200
    assert "region" not in plain.context["form"].fields
    assert "ubicacion=manual" in body
    # El aviso sale en español y en plural. Se afirma acá porque el guardián de
    # i18n **no lee los `blocktranslate`** (su punto ciego, capturado como fila
    # propia), así que ésta es la única prueba de que la entrada del catálogo
    # existe y calza: sin ella el aviso saldría en inglés sin fallar nada.
    assert "6 casillas de ubicación vienen del plan" in body
    assert "no se vuelven a pedir" in body

    manual = client.get(url, {"ubicacion": "manual"})
    assert "region" in manual.context["form"].fields


@pytest.mark.django_db
def test_the_ficha_names_the_plan_the_location_came_from(world):
    """La otra mitad de esconderlas: desde que el formulario no las pide, la
    ficha es el único lugar donde se ven, y un dato sin fuente no se puede
    discutir con la DGAC."""
    plan = _plan(world)
    _filled(world["permission"])
    user = User.objects.create_user("lector", password="password")
    user.user_permissions.add(Permission.objects.get(codename="view_flightpermission"))
    client = Client()
    assert client.login(username="lector", password="password")

    body = client.get(
        reverse("permission-detail", args=[world["permission"].pk])
    ).content.decode()

    assert plan.folio in body
    assert reverse("geo-plan-detail", args=[plan.pk]) in body
