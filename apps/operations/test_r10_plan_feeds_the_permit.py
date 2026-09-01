"""R10: el KMZ alimenta al permiso desde su propia etapa.

Corrección de una premisa equivocada de R9, pedida por el usuario el 2026-08-24:

> *"debe suministrar luego eso al permiso […] no cuando lo separe, ya que
> separar es sólo en casos especiales donde tenemos muchos KMZ. La norma es que
> sea uno solo […] ya que debe estar en la etapa del KMZ."*

R9 dejó **separar** como la única puerta para que un KMZ entregara su
información. Eso convertía el caso excepcional —un archivo con cuarenta y siete
circunferencias, como el de MLP— en el camino obligatorio del caso normal, que
es una sola circunferencia: quien subía un KMZ corriente tenía que "separar"
algo que no estaba junto.

Acá se fija el flujo corregido: los datos se leen en la ficha del plan, el plan
se puede vincular a un permiso que ya existe, y al vincularlo **rellena** su
ubicación sin pisar nada.
"""

import math
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.geo.kml.canonical import empty_document, new_uid
from apps.geo.models import GeoPlan, GeoPlanVersion
from apps.operations.flight_requests import plan_sections
from apps.operations.models import FlightPermission
from apps.registry.models import Aerodrome, CostCenter

# Centro real del KMZ de MLP y el aeródromo que el cálculo debe elegir.
LAT, LON = -31.89439167, -70.70220833


def _ring(lat, lon, radius_m, vertices=36):
    ring = []
    for step in range(vertices):
        angle = 2 * math.pi * step / vertices
        dlat = (radius_m * math.cos(angle)) / 111_320
        dlon = (radius_m * math.sin(angle)) / (111_320 * math.cos(math.radians(lat)))
        ring.append([lon + dlon, lat + dlat, 0])
    ring.append(list(ring[0]))
    return ring


def _placemark(name, geometry):
    return {
        "kind": "placemark",
        "uid": new_uid("placemark"),
        "name": name,
        "description": "",
        "visibility": True,
        "style_url": None,
        "geometry": geometry,
        "extended_data": None,
        "extras": [],
    }


def _document(circles):
    """`circles` = [(nombre, lat, lon, radio_m), ...]"""
    document = empty_document()
    for name, lat, lon, radius_m in circles:
        document["children"].append(
            _placemark(name, {"type": "Point", "coordinates": [lon, lat, 0]})
        )
        document["children"].append(
            _placemark(
                "", {"type": "Polygon", "coordinates": [_ring(lat, lon, radius_m)]}
            )
        )
    return document


@pytest.fixture
def cost_center(db):
    return CostCenter.objects.create(code="CC738", name="MLP")


@pytest.fixture
def aerodromes(db):
    Aerodrome.objects.create(
        code="SCER", name="Ad. Militar Quintero", latitude=-32.7902, longitude=-71.5216
    )
    # Sin coordenadas: no puede ganar el cálculo ni romperlo.
    Aerodrome.objects.create(code="OMAA", name="Abu Dhabi")


def _user(*groups):
    user = User.objects.create_user("ops", "ops@test.com", "password")
    for name in groups:
        user.groups.add(Group.objects.get(name=name))
    client = Client()
    assert client.login(username="ops", password="password")
    return client


def _plan(cost_center, circles, *, title="Quebradas MLP", user=None):
    author = user or User.objects.create_user("author", "a@test.com", "x")
    plan = GeoPlan.objects.create(
        title=title, cost_center=cost_center, created_by=author, status="draft"
    )
    version = GeoPlanVersion.objects.create(
        plan=plan,
        version_number=1,
        content=_document(circles),
        content_checksum="x" * 64,
        source="import",
        feature_count=len(circles) * 2,
        size_bytes=10,
        created_by=author,
    )
    plan.current_version = version
    plan.save(update_fields=["current_version", "updated_at"])
    return plan


def _permission(cost_center, **kwargs):
    today = timezone.localdate()
    return FlightPermission.objects.create(
        cost_center=cost_center,
        purpose="photogrammetry",
        valid_from=today,
        valid_until=today + timezone.timedelta(days=30),
        location="Quebradas STR MLP",
        area_type="unpopulated",
        **kwargs,
    )


class TestTheDataIsReadableAtTheKmzStage:
    """Lo que antes exigía separar."""

    @pytest.mark.django_db
    def test_one_circle_yields_its_sigo_data(self, cost_center, aerodromes):
        plan = _plan(cost_center, [("Quebrada km 13.760", LAT, LON, 30)])

        rows = plan_sections(plan)

        assert len(rows) == 1
        row = rows[0]
        assert row["name"] == "Quebrada km 13.760"
        assert abs(row["radius_m"] - 30) <= 1
        assert row["lat_readable"] == "31° 53' 39.81\" S"
        assert row["dms_lat"]["hemisphere"] == "S"

    @pytest.mark.django_db
    def test_it_proposes_the_nearest_aerodrome_with_its_distance(
        self, cost_center, aerodromes
    ):
        """El requisito que el usuario llama obligatorio: la base más cercana y
        los kilómetros hasta el punto central."""
        plan = _plan(cost_center, [("Quebrada km 13.760", LAT, LON, 30)])

        row = plan_sections(plan)[0]

        assert row["amc"].code == "SCER"
        assert 120 < row["amc_distance_km"] < 130

    @pytest.mark.django_db
    def test_an_aerodrome_without_coordinates_never_wins(self, cost_center):
        """`seed_aerodromes` deja sin posición lo no verificable. Un aeródromo
        sin coordenadas no puede elegirse, y su ausencia no puede romper el
        cálculo -- que es lo que pasaría si se colara con `None`."""
        Aerodrome.objects.create(code="OMAA", name="Abu Dhabi")
        plan = _plan(cost_center, [("Quebrada", LAT, LON, 30)])

        row = plan_sections(plan)[0]

        assert row["amc"] is None
        assert row["amc_distance_km"] is None

    @pytest.mark.django_db
    def test_a_plan_without_content_is_empty_not_an_error(self, cost_center):
        """La ficha se dibuja igual mientras el plan no tenga versión: devolver
        una lista vacía es lo que permite llamar esto al pintar sin guardas."""
        author = User.objects.create_user("author", "a@test.com", "x")
        plan = GeoPlan.objects.create(
            title="Vacío", cost_center=cost_center, created_by=author
        )

        assert plan_sections(plan) == []

    @pytest.mark.django_db
    def test_it_shows_on_the_plan_page(self, cost_center, aerodromes):
        call_command("bootstrap_roles")
        plan = _plan(cost_center, [("Quebrada km 13.760", LAT, LON, 30)])

        content = (
            _user("Operations", "Viewer")
            .get(reverse("geo-plan-detail", args=[plan.pk]))
            .content.decode()
        )

        assert "Datos para SIGO" in content
        assert "SCER" in content
        # Sin las comillas del formato GMS: Django escapa `'` y `"` a entidades
        # HTML, así que afirmar la cadena literal comprobaría el escapado y no
        # que el dato llegó. Los grados y los segundos bastan y no se escapan.
        assert "31°" in content and "39.81" in content
        # La distancia **no** se afirma acá a propósito: con el locale español
        # activo Django la formatea con coma decimal, así que buscar "125.9"
        # comprobaría el formateo y no el cálculo. El valor lo fija
        # `test_it_proposes_the_nearest_aerodrome_with_its_distance`, sin pasar
        # por una plantilla.
        assert "Quebrada km 13.760" in content


class TestSplitIsNowTheException:
    @pytest.mark.django_db
    def test_a_single_circle_plan_does_not_offer_to_split(
        self, cost_center, aerodromes
    ):
        """No hay nada que partir: ofrecerlo invitaba a "separar" algo que no
        estaba junto, que es el defecto que R10 corrige."""
        call_command("bootstrap_roles")
        plan = _plan(cost_center, [("Quebrada", LAT, LON, 30)])

        content = (
            _user("Operations")
            .get(reverse("geo-plan-detail", args=[plan.pk]))
            .content.decode()
        )

        assert reverse("geo-plan-split", args=[plan.pk]) not in content

    @pytest.mark.django_db
    def test_a_multi_circle_plan_still_offers_it_and_says_how_many(
        self, cost_center, aerodromes
    ):
        call_command("bootstrap_roles")
        plan = _plan(
            cost_center,
            [("A", LAT, LON, 30), ("B", LAT + 0.01, LON + 0.01, 30)],
        )

        content = (
            _user("Operations")
            .get(reverse("geo-plan-detail", args=[plan.pk]))
            .content.decode()
        )

        assert reverse("geo-plan-split", args=[plan.pk]) in content
        assert "Separar en 2 solicitudes" in content


class TestLinkingAnAlreadyUploadedPlan:
    """El hueco que el usuario reportó: sólo se podía **importar** un KMZ nuevo."""

    @pytest.mark.django_db
    def test_it_links_and_fills_the_empty_location(self, cost_center, aerodromes):
        call_command("bootstrap_roles")
        plan = _plan(cost_center, [("Quebrada km 13.760", LAT, LON, 30)])
        permission = _permission(cost_center)

        response = _user("Operations").post(
            reverse("permission-link-plan", args=[permission.pk]),
            {"plan": str(plan.pk)},
        )

        assert response.status_code == 302
        plan.refresh_from_db()
        permission.refresh_from_db()
        assert plan.flight_permission_id == permission.pk
        assert float(permission.latitude) == pytest.approx(LAT, abs=1e-5)
        assert float(permission.longitude) == pytest.approx(LON, abs=1e-5)
        assert float(permission.radius_km) == pytest.approx(0.03, abs=0.002)
        assert permission.area_name == "Quebrada km 13.760"

    @pytest.mark.django_db
    def test_it_never_overwrites_what_the_permit_already_says(
        self, cost_center, aerodromes
    ):
        """El papel DGAC manda sobre lo que se preparó antes de presentar."""
        call_command("bootstrap_roles")
        plan = _plan(cost_center, [("Quebrada", LAT, LON, 30)])
        permission = _permission(
            cost_center,
            latitude=Decimal("-33.000000"),
            longitude=Decimal("-70.000000"),
            radius_km=Decimal("5.00"),
            area_name="Lo que dice el papel",
        )

        _user("Operations").post(
            reverse("permission-link-plan", args=[permission.pk]),
            {"plan": str(plan.pk)},
        )

        permission.refresh_from_db()
        assert float(permission.latitude) == -33.0
        assert float(permission.radius_km) == 5.0
        assert permission.area_name == "Lo que dice el papel"

    @pytest.mark.django_db
    def test_the_link_records_who_did_it(self, cost_center, aerodromes):
        """`GeoPlanPermissionLink` existía desde OPS-7 pero su columna de autor
        nacía **nula**: la señal lee `plan._changed_by_user` y nadie lo seteaba.
        Es el mismo defecto que `LV-101` encontró como "system"."""
        call_command("bootstrap_roles")
        plan = _plan(cost_center, [("Quebrada", LAT, LON, 30)])
        permission = _permission(cost_center)

        _user("Operations").post(
            reverse("permission-link-plan", args=[permission.pk]),
            {"plan": str(plan.pk)},
        )

        link = plan.permission_links.get()
        assert link.new_permission_id == permission.pk
        assert link.changed_by_user is not None
        assert link.changed_by_user.username == "ops"

    @pytest.mark.django_db
    def test_a_multi_circle_plan_links_but_fills_nothing(self, cost_center, aerodromes):
        """Con varias circunferencias, elegir una sería inventar cuál manda. El
        vínculo vale; las coordenadas se resuelven separando."""
        call_command("bootstrap_roles")
        plan = _plan(
            cost_center, [("A", LAT, LON, 30), ("B", LAT + 0.01, LON + 0.01, 30)]
        )
        permission = _permission(cost_center)

        _user("Operations").post(
            reverse("permission-link-plan", args=[permission.pk]),
            {"plan": str(plan.pk)},
        )

        plan.refresh_from_db()
        permission.refresh_from_db()
        assert plan.flight_permission_id == permission.pk
        assert permission.latitude is None

    @pytest.mark.django_db
    def test_a_plan_from_another_cost_center_is_refused(self, cost_center, aerodromes):
        call_command("bootstrap_roles")
        other = CostCenter.objects.create(code="CC999", name="Otra")
        plan = _plan(other, [("Quebrada", LAT, LON, 30)])
        permission = _permission(cost_center)

        _user("Operations").post(
            reverse("permission-link-plan", args=[permission.pk]),
            {"plan": str(plan.pk)},
        )

        plan.refresh_from_db()
        assert plan.flight_permission_id is None

    @pytest.mark.django_db
    def test_the_permit_page_offers_the_picker(self, cost_center, aerodromes):
        call_command("bootstrap_roles")
        _plan(cost_center, [("Quebrada", LAT, LON, 30)], title="Un plan ya subido")
        permission = _permission(cost_center)

        content = (
            _user("Operations")
            .get(reverse("permission-detail", args=[permission.pk]))
            .content.decode()
        )

        assert "Vincular un plan ya subido" in content
        assert "Un plan ya subido" in content

    @pytest.mark.django_db
    def test_an_already_linked_plan_is_not_offered_again(self, cost_center, aerodromes):
        """Reasignar un plan de un permiso a otro es un movimiento distinto;
        ofrecerlo entre iguales invitaría a hacerlo sin querer."""
        call_command("bootstrap_roles")
        first = _permission(cost_center)
        plan = _plan(cost_center, [("Quebrada", LAT, LON, 30)], title="Ya vinculado")
        plan.flight_permission = first
        plan.save(update_fields=["flight_permission", "updated_at"])
        second = _permission(cost_center)

        content = (
            _user("Operations")
            .get(reverse("permission-detail", args=[second.pk]))
            .content.decode()
        )

        assert "Ya vinculado" not in content


class TestTheFillRuleItself:
    """`fill_location_gaps` se extrajo para que la solicitud y el plan usen la
    misma aritmética. Estos tests fijan la regla, sin pasar por una vista."""

    @pytest.mark.django_db
    def test_metres_arrive_as_metres(self, cost_center):
        """**Renombrado en `LV-221`: la conversión que este test protegía ya no existe.**

        Se llamaba `test_metres_become_feet` y afirmaba
        `max_altitude_ft == 394`, con este docstring: *"copiar el número tal cual
        convertiría 120 m en 120 ft: un tercio de la altura real, y sin que nada
        avise"*. El razonamiento era correcto y la defensa funcionaba **en este
        camino** — pero el formulario manual no tenía ninguna, y por ahí entraron
        los tres permisos que producción tenía cargados con `120 ft` donde se
        querían 120 m.

        Con el permiso guardando metros (`LV-221`), la conversión desaparece en
        vez de quedar cubierta en una ruta y descubierta en la otra: el plan trae
        metros y el permiso los recibe sin tocar. Los pies siguen existiendo para
        el formulario del SIGO, pero **calculados** en
        `max_altitude_ft_equivalent`, no guardados.
        """
        permission = _permission(cost_center)

        permission.fill_location_gaps(altitude_m=120)

        permission.refresh_from_db()
        assert permission.max_altitude_m == 120
        # Y los 394 ft siguen disponibles para transcribir, sin ser el dato.
        assert permission.max_altitude_ft_equivalent == 394

    @pytest.mark.django_db
    def test_a_radius_is_never_saved_without_its_coordinates(self, cost_center):
        """`clean()` prohíbe radio sin par de coordenadas, así que rellenarlo
        solo dejaría el permiso inválido contra su propia validación."""
        permission = _permission(cost_center)

        filled = permission.fill_location_gaps(radius_m=30)

        assert filled == []
        permission.refresh_from_db()
        assert permission.radius_km is None

    @pytest.mark.django_db
    def test_coordinates_are_written_as_a_pair(self, cost_center):
        permission = _permission(cost_center)

        filled = permission.fill_location_gaps(latitude=Decimal("-31.894392"))

        assert filled == []
        permission.refresh_from_db()
        assert permission.latitude is None

    @pytest.mark.django_db
    def test_it_reports_what_it_filled(self, cost_center):
        """Sin la lista, la pantalla tendría que dejar a la persona comparando
        para saber qué cambió."""
        permission = _permission(cost_center)

        filled = permission.fill_location_gaps(
            latitude=Decimal("-31.894392"),
            longitude=Decimal("-70.702208"),
            radius_m=30,
            commune="Salamanca",
        )

        assert set(filled) == {"latitude", "longitude", "radius_km", "commune"}
