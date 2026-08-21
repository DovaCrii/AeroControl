"""R9.3/R9.4: la solicitud de vuelo SIGO — de un KMZ multi-círculo al formulario.

El caso real que motiva todo esto: el KMZ de MLP trae 47 pares punto+círculo y
SIGO acepta **uno por solicitud**. Estos tests recorren el camino completo:
separar el plan → crear las solicitudes → armar la hoja que se copia → adjuntar
el KMZ individual → vincular al permiso cuando la DGAC responde.
"""

import math
from datetime import time

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.utils import timezone

from apps.geo.kml.canonical import empty_document, iter_placemarks, new_uid
from apps.geo.kml.kmz import read_kmz
from apps.geo.kml.parse import parse_kml_bytes
from apps.geo.models import GeoPlan, GeoPlanVersion
from apps.operations.flight_requests import (
    create_requests_from_plan,
    link_to_permission,
    section_kmz,
    sigo_sheet,
)
from apps.operations.models import (
    FlightObjective,
    FlightPermission,
    FlightRequest,
    FlightRequestHistory,
    FlightRequestNote,
    FlightRequestWorkItem,
    WorkAreaType,
)
from apps.registry.models import Aerodrome, CostCenter

LAT, LON = -31.89439167, -70.70220833
SECOND_LAT, SECOND_LON = -31.89285000, -70.70973333


def _point(name, lat, lon):
    return {
        "kind": "placemark",
        "uid": new_uid("placemark"),
        "name": name,
        "description": "",
        "visibility": True,
        "style_url": None,
        "geometry": {"type": "Point", "coordinates": [lon, lat, 0]},
        "extended_data": None,
        "extras": [],
    }


def _circle(lat, lon, radius_m=30, vertices=36):
    ring = []
    for step in range(vertices):
        angle = 2 * math.pi * step / vertices
        dlat = (radius_m * math.cos(angle)) / 111_320
        dlon = (radius_m * math.sin(angle)) / (111_320 * math.cos(math.radians(lat)))
        ring.append([lon + dlon, lat + dlat, 0])
    ring.append(list(ring[0]))
    placemark = _point("", lat, lon)
    placemark["geometry"] = {"type": "Polygon", "coordinates": [ring]}
    return placemark


def _mlp_document():
    """La forma del KMZ real: puntos con nombre y círculos en otra carpeta."""
    document = empty_document()
    document["children"] = [
        {
            "kind": "folder",
            "uid": new_uid("folder"),
            "name": "Puntos",
            "description": "",
            "visibility": True,
            "children": [
                _point("Quebrada km 13.760", LAT, LON),
                _point("Quebrada km 14.508", SECOND_LAT, SECOND_LON),
            ],
        },
        {
            "kind": "folder",
            "uid": new_uid("folder"),
            "name": "Radios de 30 m",
            "description": "",
            "visibility": True,
            "children": [_circle(LAT, LON), _circle(SECOND_LAT, SECOND_LON)],
        },
    ]
    return document


@pytest.fixture
def user(db):
    return User.objects.create_user("ops", "ops@test.com", "password")


@pytest.fixture
def cost_center(db):
    return CostCenter.objects.create(code="CC738", name="MLP")


@pytest.fixture
def catalogs(db):
    call_command("seed_aerodromes")
    call_command("seed_sigo_catalogs")


@pytest.fixture
def plan(cost_center, user):
    plan = GeoPlan.objects.create(
        title="Quebradas STR MLP", cost_center=cost_center, created_by=user
    )
    version = GeoPlanVersion.objects.create(
        plan=plan,
        version_number=1,
        content=_mlp_document(),
        content_checksum="x" * 64,
        source="import",
        created_by=user,
    )
    plan.current_version = version
    plan.save(update_fields=["current_version", "updated_at"])
    return plan


class TestSplittingAPlanIntoRequests:
    @pytest.mark.django_db
    def test_one_request_per_circle(self, plan, user, catalogs):
        """La regla que gobierna todo: SIGO acepta una circunferencia por
        solicitud, así que un plan de N círculos son N solicitudes."""
        requests, sections = create_requests_from_plan(plan, created_by=user)

        assert len(requests) == 2
        assert [r.title for r in requests] == [
            "Quebrada km 13.760",
            "Quebrada km 14.508",
        ]
        assert all(section.warnings == [] for section in sections)

    @pytest.mark.django_db
    def test_each_request_carries_its_center_radius_and_amc(self, plan, user, catalogs):
        requests, _sections = create_requests_from_plan(plan, created_by=user)

        request = requests[0]
        assert float(request.center_lat) == pytest.approx(LAT, abs=1e-6)
        assert request.radius_m == 30
        assert request.amc.code == "SCER"
        assert 120 < float(request.amc_distance_km) < 130

    @pytest.mark.django_db
    def test_the_distance_is_frozen_not_recomputed(self, plan, user, catalogs):
        """Es el número que se escribió en el formulario del Estado. Si mañana
        alguien corrige la coordenada del aeródromo en su ficha, la solicitud
        ya presentada tiene que seguir diciendo lo que dijo -- misma lección
        que `LV-118` dejó en las alertas."""
        requests, _sections = create_requests_from_plan(plan, created_by=user)
        original = requests[0].amc_distance_km

        aerodrome = Aerodrome.objects.get(code="SCER")
        aerodrome.latitude = -20.0
        aerodrome.save(update_fields=["latitude", "updated_at"])

        requests[0].refresh_from_db()
        assert requests[0].amc_distance_km == original

    @pytest.mark.django_db
    def test_a_section_with_warnings_is_still_created(self, plan, user, catalogs):
        """Esconderla obligaría a volver al KMZ para descubrir que falta."""
        document = _mlp_document()
        document["children"][0]["children"].append(_point("Sin círculo", -31.0, -70.0))
        plan.current_version.content = document

        requests, sections = create_requests_from_plan(
            plan, created_by=user, document=document
        )

        assert len(requests) == 3
        assert requests[2].radius_m is None
        assert sections[2].warnings == ["no_circle"]

    @pytest.mark.django_db
    def test_it_works_without_any_locatable_aerodrome(self, plan, user):
        """Sin catálogo sembrado no hay AMC que proponer, y eso no puede
        impedir preparar la solicitud: la casilla se llena a mano."""
        requests, _sections = create_requests_from_plan(plan, created_by=user)

        assert requests[0].amc is None
        assert requests[0].amc_distance_km is None


class TestTheSigoSheet:
    @pytest.mark.django_db
    def test_the_center_comes_split_into_the_six_boxes(self, plan, user, catalogs):
        """SIGO pide grados, minutos y segundos por separado. Entregar
        "-31.894392" obligaría a partirlo a mano, que es el trabajo que esta
        pantalla existe para quitar."""
        requests, _sections = create_requests_from_plan(plan, created_by=user)

        sheet = sigo_sheet(requests[0])

        assert (sheet["lat_degrees"], sheet["lat_minutes"]) == (31, 53)
        assert sheet["lat_seconds"] == "39.81"
        assert sheet["lat_hemisphere"] == "S"
        assert sheet["lon_hemisphere"] == "W"
        assert sheet["lat_readable"] == "31° 53' 39.81\" S"

    @pytest.mark.django_db
    def test_work_pairs_come_through(self, plan, user, catalogs):
        requests, _sections = create_requests_from_plan(plan, created_by=user)
        FlightRequestWorkItem.objects.create(
            request=requests[0],
            work_area=WorkAreaType.objects.get(code="fotografia-filmacion-aerea"),
            objective=FlightObjective.objects.get(code="fotogrametria"),
        )

        sheet = sigo_sheet(requests[0])

        assert sheet["work_pairs"] == [
            ("Fotografía y filmación aérea (Capítulo J - DAN 137)", "Fotogrametría")
        ]

    @pytest.mark.django_db
    def test_the_attached_kmz_is_one_circle_and_one_point(self, plan, user, catalogs):
        """Lo que SIGO exige, verificado releyendo el archivo con nuestro
        propio lector en vez de confiar en que se escribió bien."""
        requests, _sections = create_requests_from_plan(plan, created_by=user)

        kmz = section_kmz(requests[0])
        kml_bytes, resources = read_kmz(kmz)
        placemarks = list(iter_placemarks(parse_kml_bytes(kml_bytes)))

        assert resources == []
        assert sorted(p["geometry"]["type"] for p in placemarks) == [
            "Point",
            "Polygon",
        ]
        assert len(kmz) < 20 * 1024 * 1024  # el tope que declara el formulario


class TestTheFlowAndItsTrace:
    @pytest.mark.django_db
    def test_it_starts_prepared_and_is_editable(self, plan, user, catalogs):
        requests, _sections = create_requests_from_plan(plan, created_by=user)

        assert requests[0].status == FlightRequest.STATUS_PREPARED
        assert requests[0].is_editable is True

    @pytest.mark.django_db
    def test_filing_it_stops_being_editable(self, plan, user, catalogs):
        """Una vez presentada, el archivo que SIGO tiene ya no coincidiría con
        lo que se editara acá."""
        requests, _sections = create_requests_from_plan(plan, created_by=user)
        request = requests[0]

        request.status = FlightRequest.STATUS_FILED
        request.save(update_fields=["status", "updated_at"])

        assert request.is_editable is False

    @pytest.mark.django_db
    def test_every_transition_leaves_a_history_row(self, plan, user, catalogs):
        """Quinto usuario de la señal compartida: agregar el seguimiento costó
        una línea, que es la razón por la que `LV-72` la extrajo."""
        requests, _sections = create_requests_from_plan(plan, created_by=user)
        request = requests[0]

        request.status = FlightRequest.STATUS_FILED
        request._changed_by = "demo"
        request.save(update_fields=["status", "updated_at"])

        row = FlightRequestHistory.objects.get(request=request)
        assert (row.previous_status, row.new_status) == ("prepared", "filed")
        assert row.changed_by == "demo"

    @pytest.mark.django_db
    def test_the_stepper_has_the_four_real_steps(self, plan, user, catalogs):
        """Se afirman los **códigos**, no las etiquetas: son traducibles, y un
        test que fija la redacción pasa o falla según el idioma activo — la
        misma fragilidad que este repo ya pagó en `LV-95` y que los avisos del
        motor de secciones evitan por lo mismo."""
        requests, _sections = create_requests_from_plan(plan, created_by=user)

        steps = requests[0].status_steps()

        assert [s["code"] for s in steps] == ["prepared", "filed", "linked", "closed"]
        assert [s["state"] for s in steps] == [
            "current",
            "pending",
            "pending",
            "pending",
        ]

    @pytest.mark.django_db
    def test_days_waiting_only_counts_while_it_is_filed(self, plan, user, catalogs):
        """Preguntar cuánto espera algo que ya llegó no significa nada."""
        requests, _sections = create_requests_from_plan(plan, created_by=user)
        request = requests[0]
        assert request.days_waiting() is None

        request.status = FlightRequest.STATUS_FILED
        request.filed_on = timezone.localdate() - timezone.timedelta(days=9)
        request.save(update_fields=["status", "filed_on", "updated_at"])
        assert request.days_waiting() == 9

        request.status = FlightRequest.STATUS_LINKED
        request.save(update_fields=["status", "updated_at"])
        assert request.days_waiting() is None

    @pytest.mark.django_db
    def test_notes_are_kept_without_any_diff(self, plan, user, catalogs):
        """El límite que puso el usuario: nota de los cambios, sin comparación
        entre modificaciones."""
        requests, _sections = create_requests_from_plan(plan, created_by=user)

        FlightRequestNote.objects.create(
            request=requests[0], text="Se corrige la comuna", author=user
        )

        assert requests[0].change_notes.count() == 1


class TestLinkingToThePermit:
    @pytest.fixture
    def permission(self, cost_center):
        return FlightPermission.objects.create(
            cost_center=cost_center,
            purpose="photogrammetry",
            valid_from=timezone.localdate(),
            valid_until=timezone.localdate() + timezone.timedelta(days=30),
            location="Quebradas STR MLP",
            area_type="unpopulated",
        )

    @pytest.mark.django_db
    def test_it_fills_the_permits_structured_location(
        self, plan, user, catalogs, permission
    ):
        """La solicitud **rellena** OPS-4 en vez de duplicarlo."""
        requests, _sections = create_requests_from_plan(plan, created_by=user)
        request = requests[0]
        request.commune = "Salamanca"
        request.altitude_m = 120
        request.save(update_fields=["commune", "altitude_m", "updated_at"])

        filled = link_to_permission(request, permission, changed_by="demo")

        permission.refresh_from_db()
        assert float(permission.latitude) == pytest.approx(LAT, abs=1e-6)
        assert permission.commune == "Salamanca"
        assert permission.max_altitude_ft == 394  # 120 m
        assert float(permission.radius_km) == 0.03
        assert set(filled) >= {"latitude", "longitude", "commune"}

    @pytest.mark.django_db
    def test_it_never_overwrites_what_the_permit_already_says(
        self, plan, user, catalogs, permission
    ):
        """Si el permiso ya trae una coordenada, puede venir del papel DGAC —
        que es de más autoridad que lo que se preparó antes de presentar."""
        permission.latitude, permission.longitude = -20.0, -69.0
        permission.commune = "Calama"
        permission.save(update_fields=["latitude", "longitude", "commune"])
        requests, _sections = create_requests_from_plan(plan, created_by=user)
        requests[0].commune = "Salamanca"
        requests[0].save(update_fields=["commune", "updated_at"])

        link_to_permission(requests[0], permission)

        permission.refresh_from_db()
        assert float(permission.latitude) == -20.0
        assert permission.commune == "Calama"

    @pytest.mark.django_db
    def test_linking_advances_the_status_and_records_it(
        self, plan, user, catalogs, permission
    ):
        requests, _sections = create_requests_from_plan(plan, created_by=user)

        link_to_permission(requests[0], permission, changed_by="demo", user=user)

        requests[0].refresh_from_db()
        assert requests[0].status == FlightRequest.STATUS_LINKED
        assert requests[0].flight_permission_id == permission.pk
        assert FlightRequestHistory.objects.filter(
            request=requests[0], new_status="linked"
        ).exists()


class TestValidation:
    @pytest.mark.django_db
    def test_an_aerodrome_without_its_distance_is_half_a_box(
        self, cost_center, catalogs
    ):
        request = FlightRequest(
            title="X",
            cost_center=cost_center,
            center_lat="-31.894392",
            center_lon="-70.702208",
            amc=Aerodrome.objects.get(code="SCEL"),
        )

        with pytest.raises(ValidationError) as error:
            request.full_clean()

        assert "amc_distance_km" in error.value.error_dict

    @pytest.mark.django_db
    def test_the_end_time_must_be_after_the_start(self, cost_center):
        request = FlightRequest(
            title="X",
            cost_center=cost_center,
            center_lat="-31.894392",
            center_lon="-70.702208",
            hour_from=time(14, 0),
            hour_to=time(9, 0),
        )

        with pytest.raises(ValidationError) as error:
            request.full_clean()

        assert "hour_to" in error.value.error_dict
