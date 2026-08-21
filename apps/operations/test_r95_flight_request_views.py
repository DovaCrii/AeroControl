"""R9.5: las pantallas de la solicitud de vuelo SIGO.

El camino que recorre una persona: ficha del plan → vista previa de secciones →
crear las solicitudes → ficha con la hoja copiable → descargar el KMZ →
presentar → vincular al permiso.
"""

import math
import re

import pytest
from django.contrib.auth.models import Permission, User
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from apps.geo.kml.canonical import empty_document, new_uid
from apps.geo.models import GeoPlan, GeoPlanVersion
from apps.operations.flight_requests import create_requests_from_plan
from apps.operations.models import (
    FlightObjective,
    FlightPermission,
    FlightRequest,
    FlightRequestNote,
    FlightRequestWorkItem,
    WorkAreaType,
)
from apps.registry.models import CostCenter

LAT, LON = -31.89439167, -70.70220833


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


def _circle(lat, lon, radius_m=30):
    ring = []
    for step in range(36):
        angle = 2 * math.pi * step / 36
        dlat = (radius_m * math.cos(angle)) / 111_320
        dlon = (radius_m * math.sin(angle)) / (111_320 * math.cos(math.radians(lat)))
        ring.append([lon + dlon, lat + dlat, 0])
    ring.append(list(ring[0]))
    placemark = _point("", lat, lon)
    placemark["geometry"] = {"type": "Polygon", "coordinates": [ring]}
    return placemark


def _document(with_orphan=False):
    document = empty_document()
    document["children"] = [
        _point("Quebrada km 13.760", LAT, LON),
        _circle(LAT, LON),
    ]
    if with_orphan:
        document["children"].append(_point("Sin círculo", -31.0, -70.0))
    return document


@pytest.fixture
def staff(db):
    """Un usuario con los permisos del flujo, no un superusuario.

    Con `is_superuser` toda comprobación de permisos pasa sola y estos tests no
    dirían nada sobre quién puede hacer qué.
    """
    user = User.objects.create_user("ops", "ops@test.com", "password")
    user.user_permissions.add(
        *Permission.objects.filter(
            codename__in=[
                "view_flightrequest",
                "add_flightrequest",
                "change_flightrequest",
                "view_geoplan",
                "view_flightpermission",
            ]
        )
    )
    return user


@pytest.fixture
def client_in(client, staff):
    assert client.login(username="ops", password="password")
    return client


@pytest.fixture
def cost_center(db):
    return CostCenter.objects.create(code="CC738", name="MLP")


@pytest.fixture
def catalogs(db):
    call_command("seed_aerodromes")
    call_command("seed_sigo_catalogs")


@pytest.fixture
def plan(cost_center, staff):
    plan = GeoPlan.objects.create(
        title="Quebradas STR MLP", cost_center=cost_center, created_by=staff
    )
    version = GeoPlanVersion.objects.create(
        plan=plan,
        version_number=1,
        content=_document(),
        content_checksum="x" * 64,
        source="import",
        created_by=staff,
    )
    plan.current_version = version
    plan.save(update_fields=["current_version", "updated_at"])
    return plan


@pytest.fixture
def flight_request(plan, staff, catalogs):
    requests, _sections = create_requests_from_plan(plan, created_by=staff)
    return requests[0]


class TestSplittingFromThePlan:
    @pytest.mark.django_db
    def test_the_preview_lists_the_sections_before_creating_anything(
        self, client_in, plan, catalogs
    ):
        """La vista previa no es cortesía: el KMZ real trajo seis secciones con
        problema de dato, y crear sin mirarlas enterraría ese hallazgo."""
        response = client_in.get(reverse("geo-plan-split", args=[plan.pk]))

        assert response.status_code == 200
        assert "Quebrada km 13.760" in response.content.decode()
        assert FlightRequest.objects.count() == 0

    @pytest.mark.django_db
    def test_the_preview_shows_the_warning_in_words_not_codes(
        self, client_in, plan, staff, catalogs
    ):
        """El motor devuelve códigos y la pantalla los redacta: es el reparto
        que permite traducir sin tocar el motor."""
        plan.current_version.content = _document(with_orphan=True)
        version = GeoPlanVersion.objects.create(
            plan=plan,
            version_number=2,
            content=_document(with_orphan=True),
            content_checksum="y" * 64,
            source="import",
            created_by=staff,
        )
        plan.current_version = version
        plan.save(update_fields=["current_version", "updated_at"])

        content = client_in.get(
            reverse("geo-plan-split", args=[plan.pk])
        ).content.decode()

        assert "no_circle" not in content
        assert "No circle" in content or "circunferencia" in content.lower()

    @pytest.mark.django_db
    def test_posting_creates_one_request_per_circle(self, client_in, plan, catalogs):
        response = client_in.post(reverse("geo-plan-split", args=[plan.pk]))

        assert response.status_code == 302
        assert FlightRequest.objects.count() == 1
        assert FlightRequest.objects.get().title == "Quebrada km 13.760"

    @pytest.mark.django_db
    def test_a_plan_with_no_content_is_not_splittable(
        self, client_in, cost_center, staff
    ):
        """Sin versión vigente no hay nada que separar: 404, no un reventón."""
        empty = GeoPlan.objects.create(
            title="Vacío", cost_center=cost_center, created_by=staff
        )

        response = client_in.get(reverse("geo-plan-split", args=[empty.pk]))

        assert response.status_code == 404

    @pytest.mark.django_db
    def test_it_warns_when_the_plan_was_already_split(
        self, client_in, plan, flight_request
    ):
        """Repetir puede ser legítimo (se corrigió el KMZ). Lo que no puede
        pasar es duplicar sin que nadie lo supiera."""
        content = client_in.get(
            reverse("geo-plan-split", args=[plan.pk])
        ).content.decode()

        assert "already has" in content or "ya tiene" in content.lower()


class TestTheDetailSheet:
    @pytest.mark.django_db
    def test_the_six_centre_boxes_are_on_the_page(self, client_in, flight_request):
        """Lo que hace útil la pantalla: los valores en el formato de la
        casilla, no una coordenada decimal que haya que partir a mano."""
        content = client_in.get(
            reverse("flight-request-detail", args=[flight_request.pk])
        ).content.decode()

        assert "39.81" in content  # segundos de la latitud
        assert "7.95" in content  # segundos de la longitud
        assert "31° 53' 39.81&quot; S" in content or "39.81" in content

    @pytest.mark.django_db
    def test_the_amc_carries_its_reminder(self, client_in, flight_request):
        """El recordatorio va pegado al dato: es lo que impide que un cálculo
        se lea como un hecho verificado (`LV-93`)."""
        content = client_in.get(
            reverse("flight-request-detail", args=[flight_request.pk])
        ).content.decode()

        assert "SCER" in content
        assert "AIP" in content

    @pytest.mark.django_db
    def test_the_stepper_is_on_the_page(self, client_in, flight_request):
        content = client_in.get(
            reverse("flight-request-detail", args=[flight_request.pk])
        ).content.decode()

        assert "status-steps" in content


class TestTheKmzDownload:
    @pytest.mark.django_db
    def test_it_serves_a_kmz_named_after_the_section(self, client_in, flight_request):
        response = client_in.get(
            reverse("flight-request-kmz", args=[flight_request.pk])
        )

        assert response.status_code == 200
        assert response["Content-Type"] == "application/vnd.google-earth.kmz"
        assert "quebrada-km-13760" in response["Content-Disposition"]

    @pytest.mark.django_db
    def test_a_request_without_geometry_says_so_instead_of_crashing(
        self, client_in, cost_center
    ):
        bare = FlightRequest.objects.create(
            title="Sin geometría",
            cost_center=cost_center,
            center_lat="-31.894392",
            center_lon="-70.702208",
        )

        response = client_in.get(reverse("flight-request-kmz", args=[bare.pk]))

        assert response.status_code == 302


class TestWorkPairsAndNotes:
    @pytest.mark.django_db
    def test_adding_a_pair(self, client_in, flight_request, catalogs):
        response = client_in.post(
            reverse("flight-request-add-work-item", args=[flight_request.pk]),
            {
                "work_area": WorkAreaType.objects.get(
                    code="fotografia-filmacion-aerea"
                ).pk,
                "objective": FlightObjective.objects.get(code="fotogrametria").pk,
            },
        )

        assert response.status_code == 302
        assert flight_request.work_items.count() == 1

    @pytest.mark.django_db
    def test_adding_the_same_pair_twice_is_a_message_not_a_500(
        self, client_in, flight_request, catalogs
    ):
        """Repetir el par es un clic de más, no un error del usuario -- y sin
        esto reventaría contra la restricción de unicidad."""
        payload = {
            "work_area": WorkAreaType.objects.get(code="otros").pk,
            "objective": FlightObjective.objects.get(code="batimetria").pk,
        }
        url = reverse("flight-request-add-work-item", args=[flight_request.pk])
        client_in.post(url, payload)

        response = client_in.post(url, payload)

        assert response.status_code == 302
        assert flight_request.work_items.count() == 1

    @pytest.mark.django_db
    def test_removing_a_pair(self, client_in, flight_request, catalogs):
        item = FlightRequestWorkItem.objects.create(
            request=flight_request,
            work_area=WorkAreaType.objects.get(code="otros"),
            objective=FlightObjective.objects.get(code="batimetria"),
        )

        client_in.post(
            reverse(
                "flight-request-remove-work-item", args=[flight_request.pk, item.pk]
            )
        )

        assert flight_request.work_items.count() == 0

    @pytest.mark.django_db
    def test_adding_a_note(self, client_in, flight_request, staff):
        client_in.post(
            reverse("flight-request-add-note", args=[flight_request.pk]),
            {"text": "Se corrige la comuna contra la tabla"},
        )

        note = FlightRequestNote.objects.get(request=flight_request)
        assert note.author == staff
        assert "comuna" in note.text

    @pytest.mark.django_db
    def test_an_empty_note_is_refused(self, client_in, flight_request):
        client_in.post(
            reverse("flight-request-add-note", args=[flight_request.pk]),
            {"text": "   "},
        )

        assert FlightRequestNote.objects.count() == 0


class TestTheFlowThroughTheScreens:
    @pytest.mark.django_db
    def test_filing_stamps_the_date_that_makes_the_wait_measurable(
        self, client_in, flight_request
    ):
        """Presentar y la fecha en que ocurrió son el mismo hecho, así que la
        fecha no se pide en un formulario aparte."""
        client_in.post(reverse("flight-request-file", args=[flight_request.pk]))

        flight_request.refresh_from_db()
        assert flight_request.status == FlightRequest.STATUS_FILED
        assert flight_request.filed_on == timezone.localdate()
        assert flight_request.days_waiting() == 0

    @pytest.mark.django_db
    def test_linking_from_the_screen_fills_the_permit(
        self, client_in, flight_request, cost_center
    ):
        permission = FlightPermission.objects.create(
            cost_center=cost_center,
            purpose="photogrammetry",
            valid_from=timezone.localdate(),
            valid_until=timezone.localdate() + timezone.timedelta(days=30),
            location="MLP",
            area_type="unpopulated",
        )
        client_in.post(reverse("flight-request-file", args=[flight_request.pk]))

        client_in.post(
            reverse("flight-request-link", args=[flight_request.pk]),
            {"permission": str(permission.pk)},
        )

        flight_request.refresh_from_db()
        permission.refresh_from_db()
        assert flight_request.status == FlightRequest.STATUS_LINKED
        assert permission.latitude is not None

    @pytest.mark.django_db
    def test_a_permit_from_another_cost_center_is_refused(
        self, client_in, flight_request
    ):
        """Ofrecer —o aceptar— un permiso de otra faena sería ofrecer un
        error."""
        other = CostCenter.objects.create(code="CC999", name="Otra")
        foreign = FlightPermission.objects.create(
            cost_center=other,
            purpose="photogrammetry",
            valid_from=timezone.localdate(),
            valid_until=timezone.localdate() + timezone.timedelta(days=30),
            location="Otra",
            area_type="unpopulated",
        )
        client_in.post(reverse("flight-request-file", args=[flight_request.pk]))

        client_in.post(
            reverse("flight-request-link", args=[flight_request.pk]),
            {"permission": str(foreign.pk)},
        )

        flight_request.refresh_from_db()
        assert flight_request.flight_permission is None
        assert flight_request.status == FlightRequest.STATUS_FILED


class TestTheListAndTheMenu:
    @pytest.mark.django_db
    def test_the_list_shows_the_request_and_its_wait(self, client_in, flight_request):
        flight_request.status = FlightRequest.STATUS_FILED
        flight_request.filed_on = timezone.localdate() - timezone.timedelta(days=6)
        flight_request.save(update_fields=["status", "filed_on", "updated_at"])

        content = client_in.get(reverse("flight-request-list")).content.decode()

        assert "Quebrada km 13.760" in content
        assert "6" in content

    @pytest.mark.django_db
    def test_filtering_by_status(self, client_in, flight_request):
        content = client_in.get(
            reverse("flight-request-list"), {"status": "filed"}
        ).content.decode()

        assert "Quebrada km 13.760" not in content

    @pytest.mark.django_db
    def test_the_menu_offers_it_between_permits_and_plans(
        self, client_in, flight_request
    ):
        """Se mira **el orden dentro del menú**, no la primera aparición del
        enlace en la página: en la propia lista de solicitudes su URL sale antes
        en el formulario de filtros, y afirmar sobre el documento entero medía
        eso en vez del menú."""
        content = client_in.get(reverse("flight-request-list")).content.decode()

        nav_hrefs = re.findall(
            r'<a href="([^"]+)" class="nav-item nav-operations', content
        )

        assert reverse("flight-request-list") in nav_hrefs
        assert (
            nav_hrefs.index(reverse("permission-list"))
            < nav_hrefs.index(reverse("flight-request-list"))
            < nav_hrefs.index(reverse("geo-plan-list"))
        )


class TestPermissions:
    @pytest.mark.django_db
    def test_a_viewer_cannot_split_a_plan(self, client, plan, db, catalogs):
        viewer = User.objects.create_user("viewer", "v@test.com", "password")
        viewer.user_permissions.add(
            Permission.objects.get(codename="view_flightrequest"),
            Permission.objects.get(codename="view_geoplan"),
        )
        assert client.login(username="viewer", password="password")

        response = client.post(reverse("geo-plan-split", args=[plan.pk]))

        assert response.status_code == 403
        assert FlightRequest.objects.count() == 0

    @pytest.mark.django_db
    def test_anonymous_is_sent_to_login(self, client, flight_request):
        response = client.get(
            reverse("flight-request-detail", args=[flight_request.pk])
        )

        assert response.status_code == 302
        assert "/login" in response["Location"]
