"""R9.6: cerrar el círculo — la solicitud en el expediente y en el panel.

Dos huecos que quedaron abiertos al terminar las pantallas:

1. El expediente del permiso (`LV-107`) mostraba el plan que dibujó el área y
   el papel que la DGAC devolvió, pero **no lo que se pidió** — la diferencia
   entre "la DGAC autorizó esto" y "la DGAC autorizó lo que pedimos".
2. Una solicitud presentada y sin respuesta es trabajo detenido en manos de un
   tercero, y no se veía en ninguna parte: el motor de alertas vigila
   **vencimientos**, y acá no vence nada.
"""

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.operations.dossier import operational_dossier
from apps.operations.models import FlightPermission, FlightRequest
from apps.registry.models import Aircraft, CostCenter


@pytest.fixture
def cost_center(db):
    """Con una aeronave, porque el panel vacío no es el panel.

    Con el padrón en cero el tablero muestra la tarjeta de bienvenida y esconde
    todas las secciones operativas, así que un test sobre el panel montado
    sobre una base vacía afirmaría sobre una pantalla que ningún usuario ve.
    """
    cost_center = CostCenter.objects.create(code="CC738", name="MLP")
    Aircraft.objects.create(
        registration="RPA-7126",
        serial_number="1581F7FVC265Q00DM5QC",
        cost_center=cost_center,
    )
    return cost_center


@pytest.fixture
def permission(cost_center):
    return FlightPermission.objects.create(
        cost_center=cost_center,
        purpose="photogrammetry",
        valid_from=timezone.localdate(),
        valid_until=timezone.localdate() + timezone.timedelta(days=30),
        location="Quebradas STR MLP",
        area_type="unpopulated",
    )


def _request(cost_center, title="Quebrada km 13.760", **kwargs):
    return FlightRequest.objects.create(
        title=title,
        cost_center=cost_center,
        center_lat="-31.894392",
        center_lon="-70.702208",
        radius_m=30,
        **kwargs,
    )


@pytest.fixture
def admin_client_in(db):
    User.objects.create_superuser("admin", "a@test.com", "password")
    client = Client()
    assert client.login(username="admin", password="password")
    return client


class TestTheDossierClosesTheCircle:
    @pytest.mark.django_db
    def test_it_names_the_originating_request(self, permission, cost_center):
        _request(cost_center, flight_permission=permission)

        dossier = operational_dossier(permission)
        item = next(i for i in dossier["items"] if i.key == "flight_request")

        assert item.status == "ok"
        assert "Quebrada km 13.760" in item.detail

    @pytest.mark.django_db
    def test_a_permit_without_one_is_to_confirm_not_missing(self, permission):
        """Todos los permisos que existen hoy se tramitaron antes de que la app
        registrara la solicitud. Marcarlos incompletos los declararía
        defectuosos de forma retroactiva por una función que no existía."""
        dossier = operational_dossier(permission)
        item = next(i for i in dossier["items"] if i.key == "flight_request")

        assert item.status == "unknown"
        assert dossier["missing_count"] == 1  # sólo la autorización firmada

    @pytest.mark.django_db
    def test_several_requests_on_one_permit_are_all_named(
        self, permission, cost_center
    ):
        """Un permiso puede cubrir varias circunferencias: contar en vez de
        nombrar dejaría a la persona buscándolas."""
        _request(cost_center, "Quebrada km 13.760", flight_permission=permission)
        _request(cost_center, "Quebrada km 14.508", flight_permission=permission)

        item = next(
            i
            for i in operational_dossier(permission)["items"]
            if i.key == "flight_request"
        )

        assert "13.760" in item.detail and "14.508" in item.detail

    @pytest.mark.django_db
    def test_an_archived_request_does_not_count(self, permission, cost_center):
        _request(cost_center, flight_permission=permission, is_active=False)

        item = next(
            i
            for i in operational_dossier(permission)["items"]
            if i.key == "flight_request"
        )

        assert item.status == "unknown"

    @pytest.mark.django_db
    def test_it_shows_on_the_permit_page(
        self, admin_client_in, permission, cost_center
    ):
        _request(cost_center, flight_permission=permission)

        content = admin_client_in.get(
            reverse("permission-detail", args=[permission.pk])
        ).content.decode()

        assert "Quebrada km 13.760" in content


class TestThePanelShowsWhatIsWaiting:
    @pytest.mark.django_db
    def test_a_filed_request_appears_with_its_wait(self, admin_client_in, cost_center):
        _request(
            cost_center,
            status=FlightRequest.STATUS_FILED,
            filed_on=timezone.localdate() - timezone.timedelta(days=11),
        )

        response = admin_client_in.get(reverse("dashboard"))

        assert response.context["awaiting_count"] == 1
        assert response.context["longest_wait"] == 11
        assert "Quebrada km 13.760" in response.content.decode()

    @pytest.mark.django_db
    def test_a_prepared_request_is_not_waiting_on_anyone(
        self, admin_client_in, cost_center
    ):
        """Preparada es trabajo nuestro, no de la DGAC: contarlo como espera
        confundiría lo que falta hacer con lo que falta que contesten."""
        _request(cost_center)

        response = admin_client_in.get(reverse("dashboard"))

        assert response.context["awaiting_count"] == 0

    @pytest.mark.django_db
    def test_a_linked_request_stops_waiting(self, admin_client_in, cost_center):
        _request(cost_center, status=FlightRequest.STATUS_LINKED)

        assert admin_client_in.get(reverse("dashboard")).context["awaiting_count"] == 0

    @pytest.mark.django_db
    def test_the_oldest_comes_first(self, admin_client_in, cost_center):
        """Es el orden en que hay que perseguirlas, y el que sobrevive al corte
        de cinco filas del panel."""
        today = timezone.localdate()
        _request(
            cost_center,
            "Reciente",
            status=FlightRequest.STATUS_FILED,
            filed_on=today - timezone.timedelta(days=2),
        )
        _request(
            cost_center,
            "Antigua",
            status=FlightRequest.STATUS_FILED,
            filed_on=today - timezone.timedelta(days=40),
        )

        awaiting = admin_client_in.get(reverse("dashboard")).context[
            "awaiting_requests"
        ]

        assert [r.title for r in awaiting] == ["Antigua", "Reciente"]

    @pytest.mark.django_db
    def test_the_card_is_absent_when_nothing_is_waiting(
        self, admin_client_in, cost_center
    ):
        """Una tarjeta en cero que aparece todos los días enseña a no mirar la
        fila de tarjetas -- la misma razón que en `LV-122`."""
        response = admin_client_in.get(reverse("dashboard"))

        assert response.context["awaiting_count"] == 0
        assert "awaiting-sigo" not in response.content.decode()

    @pytest.mark.django_db
    def test_it_honours_the_cost_center_filter(self, admin_client_in, cost_center):
        """El panel entero se filtra por centro de costo; una sección que
        ignorara el filtro mostraría faena ajena junto a la propia."""
        other = CostCenter.objects.create(code="CC999", name="Otra")
        _request(
            cost_center,
            "De MLP",
            status=FlightRequest.STATUS_FILED,
            filed_on=timezone.localdate(),
        )
        _request(
            other,
            "De la otra",
            status=FlightRequest.STATUS_FILED,
            filed_on=timezone.localdate(),
        )

        response = admin_client_in.get(
            reverse("dashboard"), {"cost_center": cost_center.pk}
        )

        assert response.context["awaiting_count"] == 1
        assert [r.title for r in response.context["awaiting_requests"]] == ["De MLP"]

    @pytest.mark.django_db
    def test_a_filed_request_with_no_date_does_not_break_the_panel(
        self, admin_client_in, cost_center
    ):
        """`filed_on` puede faltar si alguien movió el estado desde el admin.
        La sección se dibuja igual, sin inventar una espera."""
        _request(cost_center, status=FlightRequest.STATUS_FILED)

        response = admin_client_in.get(reverse("dashboard"))

        assert response.status_code == 200
        assert response.context["awaiting_count"] == 1
        assert response.context["longest_wait"] is None
