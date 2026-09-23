"""LV-242: el panel decía cuántos faltan y no dejaba llegar a ellos.

Sale de la revisión de brechas del 2026-09-21 y es la continuación de `LV-241`:
contabilizar y marcar ya estaba, faltaba **poder seguirlo**. Un número que informa
de un trabajo pendiente y no lleva a ese trabajo obliga a buscarlo a mano, que es
justo lo que la pantalla existe para evitar.

Cuatro caminos que no llevaban a ninguna parte:

1. *"Seguros al día 13/14 · 1 vencido"* llevaba al padrón **completo**: el filtro
   por vigencia no existía en `AircraftList` ni en `OperatorList`, que sólo
   declaraban `search_fields`. Había que buscar esa aeronave entre dieciséis, y esa
   persona entre cuarenta y cinco.
2. «Abrir» en la bandeja de trabajo llevaba a `alert-list` —la misma URL para las
   veinte filas— así que había que volver a buscar en una lista paginada la alerta
   que uno acababa de elegir. El docstring del módulo prometía lo contrario.
3. La lista de vencimientos **se cortaba en diez sin decirlo**, y su único enlace
   va a la bandeja de alertas, que no contiene lo que todavía no generó alerta.
4. La tabla por faena **calculaba** la fecha del próximo vencimiento y la tiraba,
   que es el dato que dice cuál renovar primero.

⚠️ **Lo que hace delicado el (1) no es el filtro sino el criterio.** Si la lista
filtrara por su cuenta, una aeronave con póliza vencida pero dada de baja saldría
ahí y no en la tarjeta: el usuario contaría cinco donde el panel dijo cuatro. Por
eso las exclusiones viven en `registry.selectors` y las leen los dos.
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.registry.models import Aircraft, CostCenter, Operator

TODAY = timezone.localdate()


@pytest.fixture
def auth_client(db):
    User.objects.create_superuser("lv242", "a@test.com", "pw")
    client = Client()
    assert client.login(username="lv242", password="pw")
    return client


def _aircraft(registration, **kwargs):
    kwargs.setdefault("status", "active")
    return Aircraft.objects.create(
        registration=registration,
        type="RPA",
        model="M3",
        manufacturer="DJI",
        **kwargs,
    )


def _rows(response):
    return {a.registration for a in response.context["object_list"]}


def _names(response):
    return {o.full_name for o in response.context["object_list"]}


class TestTheFleetListCanBeNarrowedToWhatIsMissing:
    @pytest.mark.django_db
    def test_attention_returns_exactly_what_the_card_counted(self, auth_client):
        """`attention` es el complemento del numerador de la tarjeta: todo lo que no
        cuenta como "al día", sea por fecha, por falta de fecha o porque la póliza
        no está activa."""
        _aircraft(
            "RPA-0001",
            insurance_status=Aircraft.INSURANCE_STATUS_ACTIVE,
            insurance_expiry=TODAY + timedelta(days=90),
        )
        _aircraft(
            "RPA-0002",
            insurance_status=Aircraft.INSURANCE_STATUS_ACTIVE,
            insurance_expiry=TODAY - timedelta(days=3),
        )
        _aircraft("RPA-0003", insurance_expiry=None)

        response = auth_client.get(reverse("aircraft-list"), {"insurance": "attention"})

        assert _rows(response) == {"RPA-0002", "RPA-0003"}

    @pytest.mark.django_db
    def test_lapsed_and_missing_can_be_asked_for_separately(self, auth_client):
        """`LV-129` separó los dos porque se arreglan distinto —renovar una póliza
        o cargar una fecha que nadie ingresó— y el filtro conserva esa distinción."""
        _aircraft(
            "RPA-0002",
            insurance_status=Aircraft.INSURANCE_STATUS_ACTIVE,
            insurance_expiry=TODAY - timedelta(days=3),
        )
        _aircraft("RPA-0003", insurance_expiry=None)

        lapsed = auth_client.get(reverse("aircraft-list"), {"insurance": "lapsed"})
        missing = auth_client.get(reverse("aircraft-list"), {"insurance": "missing"})

        assert _rows(lapsed) == {"RPA-0002"}
        assert _rows(missing) == {"RPA-0003"}

    @pytest.mark.django_db
    def test_an_unknown_filter_is_a_no_op_and_not_an_error(self, auth_client):
        """La convención del repo para los parámetros de listado: un filtro mal
        escrito no recorta ni revienta. Una URL guardada o un bot probando query
        strings no puede tirar una pantalla."""
        _aircraft("RPA-0001")

        response = auth_client.get(reverse("aircraft-list"), {"insurance": "banana"})

        assert response.status_code == 200
        assert _rows(response) == {"RPA-0001"}

    @pytest.mark.django_db
    def test_the_roster_narrows_the_same_way(self, auth_client):
        Operator.objects.create(
            employee_id="E1",
            full_name="Al día",
            credential_expiry=TODAY + timedelta(days=90),
        )
        Operator.objects.create(
            employee_id="E2",
            full_name="Vencida",
            credential_expiry=TODAY - timedelta(days=3),
        )
        Operator.objects.create(employee_id="E3", full_name="Sin fecha")

        response = auth_client.get(
            reverse("operator-list"), {"credential": "attention"}
        )

        assert _names(response) == {"Vencida", "Sin fecha"}


class TestTheCardAndTheListCannotDisagree:
    """⚠️ La mitad que de verdad importa del (1)."""

    @pytest.mark.django_db
    def test_the_card_links_to_the_filter_when_something_is_missing(self, auth_client):
        from apps.dashboard.views import panel_readiness

        _aircraft("RPA-0002", insurance_expiry=TODAY - timedelta(days=3))

        row = next(
            item
            for item in panel_readiness(TODAY)["readiness"]
            if item["key"] == "insurance"
        )

        assert row["url"].endswith("?insurance=attention")

    @pytest.mark.django_db
    def test_with_nothing_missing_it_links_to_the_plain_list(self, auth_client):
        """Un filtro que no recorta nada es un filtro que confunde: deja al lector
        preguntándose qué está viendo de menos."""
        from apps.dashboard.views import panel_readiness

        _aircraft(
            "RPA-0001",
            insurance_status=Aircraft.INSURANCE_STATUS_ACTIVE,
            insurance_expiry=TODAY + timedelta(days=90),
        )

        row = next(
            item
            for item in panel_readiness(TODAY)["readiness"]
            if item["key"] == "insurance"
        )

        assert "?" not in row["url"]

    @pytest.mark.django_db
    def test_a_retired_aircraft_is_in_neither(self, auth_client):
        """El caso que haría discrepar los dos números si el criterio estuviera
        escrito dos veces: una póliza vencida en una aeronave dada de baja no es una
        brecha de cobertura, así que no la cuenta la tarjeta **ni** la muestra la
        lista filtrada."""
        from apps.dashboard.views import panel_readiness

        _aircraft(
            "RPA-0001",
            insurance_status=Aircraft.INSURANCE_STATUS_ACTIVE,
            insurance_expiry=TODAY + timedelta(days=90),
        )
        _aircraft(
            "RPA-9999", status="retired", insurance_expiry=TODAY - timedelta(days=200)
        )

        row = next(
            item
            for item in panel_readiness(TODAY)["readiness"]
            if item["key"] == "insurance"
        )
        response = auth_client.get(reverse("aircraft-list"), {"insurance": "attention"})

        assert row["total"] - row["count"] == 0
        assert "RPA-9999" not in _rows(response)

    @pytest.mark.django_db
    def test_an_aircraft_of_a_non_flying_site_is_in_neither(self, auth_client):
        """`LV-229`, el caso de `RPA-2019` en `CC110`: está en bodega y no opera."""
        from apps.dashboard.views import panel_readiness

        warehouse = CostCenter.objects.create(
            code="CC110", name="Casa matriz", operates_flights=False
        )
        _aircraft(
            "RPA-2019",
            cost_center=warehouse,
            insurance_expiry=TODAY - timedelta(days=30),
        )

        row = next(
            item
            for item in panel_readiness(TODAY)["readiness"]
            if item["key"] == "insurance"
        )
        response = auth_client.get(reverse("aircraft-list"), {"insurance": "attention"})

        assert row["total"] == 0
        assert "RPA-2019" not in _rows(response)


class TestTheTrayOpensTheAlert:
    @pytest.mark.django_db
    def test_an_alert_row_links_to_its_own_alert(self, db):
        """Las veinte filas apuntaban a la misma URL. Las otras tres fuentes de la
        bandeja ya usaban `get_absolute_url()`, así que la promesa del módulo se
        cumplía en tres cuartas partes."""
        from django.contrib.contenttypes.models import ContentType

        from apps.compliance.models import Alert, AlertRule
        from apps.core.tray import pending_for

        operator = Operator.objects.create(
            employee_id="E1",
            full_name="Ana",
            credential_expiry=TODAY - timedelta(days=5),
        )
        rule = AlertRule.objects.create(
            name="Credencial",
            entity_type="registry.operator",
            field_to_watch="credential_expiry",
            days_before_expiry=30,
        )
        alert = Alert.objects.create(
            alert_rule=rule,
            content_type=ContentType.objects.get_for_model(Operator),
            object_id=operator.pk,
            watched_value=operator.credential_expiry.isoformat(),
        )

        user = User.objects.create_superuser("tray", "t@test.com", "pw")
        rows = [row for row in pending_for(user) if row["source"] == "alert"]

        assert rows
        assert rows[0]["url"] == reverse("alert-resolve", args=[alert.pk])

    @pytest.mark.django_db
    def test_that_destination_answers_a_plain_get(self, auth_client):
        """Se enlaza al formulario de resolver porque **la alerta no tiene ficha**, y
        además es lo que uno viene a hacer. Tiene que responder como página completa
        y no sólo como modal, o el enlace lleva a un fragmento suelto."""
        from django.contrib.contenttypes.models import ContentType

        from apps.compliance.models import Alert, AlertRule

        operator = Operator.objects.create(
            employee_id="E1",
            full_name="Ana",
            credential_expiry=TODAY - timedelta(days=5),
        )
        rule = AlertRule.objects.create(
            name="Credencial",
            entity_type="registry.operator",
            field_to_watch="credential_expiry",
            days_before_expiry=30,
        )
        alert = Alert.objects.create(
            alert_rule=rule,
            content_type=ContentType.objects.get_for_model(Operator),
            object_id=operator.pk,
            watched_value=operator.credential_expiry.isoformat(),
        )

        response = auth_client.get(reverse("alert-resolve", args=[alert.pk]))

        assert response.status_code == 200


class TestTheListSaysWhatItIsHiding:
    @pytest.mark.django_db
    def test_the_panel_reports_the_total_behind_the_cut(self, auth_client):
        """La tarjeta podía decir 34 y la lista mostrar diez, sin nada que avisara
        de las otras veinticuatro."""
        for index in range(14):
            _aircraft(
                f"RPA-1{index:03d}", insurance_expiry=TODAY + timedelta(days=index + 1)
            )

        response = auth_client.get(reverse("dashboard"))

        assert len(response.context["expirations"]) == 10
        assert response.context["expirations_total"] == 14
        assert "4" in response.content.decode()

    @pytest.mark.django_db
    def test_nothing_is_said_when_nothing_is_hidden(self, auth_client):
        _aircraft("RPA-0001", insurance_expiry=TODAY + timedelta(days=5))

        response = auth_client.get(reverse("dashboard"))

        assert response.context["expirations_total"] == 1
        assert "más sin mostrar" not in response.content.decode()


class TestTheTableShowsTheDateItAlreadyHad:
    @pytest.mark.django_db
    def test_the_next_expiry_reaches_the_drawn_row(self, auth_client):
        """`kpis` la calcula desde `R4` y el informe la dibuja hace meses; el panel
        la descartaba. Es el dato que dice cuál renovar primero."""
        from apps.operations.models import FlightPermission

        centre = CostCenter.objects.create(
            code="CC738", name="Faena", operates_flights=True
        )
        FlightPermission.objects.create(
            cost_center=centre,
            purpose="photogrammetry",
            status=FlightPermission.STATUS_APPROVED,
            location="Sector",
            area_type="unpopulated",
            valid_from=TODAY - timedelta(days=10),
            valid_until=TODAY + timedelta(days=12),
        )

        content = auth_client.get(reverse("dashboard")).content.decode()

        assert (TODAY + timedelta(days=12)).isoformat() in content
        assert "quedan 12 días" in content
