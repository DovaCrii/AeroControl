"""LV-129: el panel deja de dar cinco respuestas a la misma pregunta.

Pedido del usuario el 2026-08-21, mirando su propio panel: *"poder filtrar como
las de alertas o directamente no sé si juntarlas y ahorrar espacio"*. Al medirlo
apareció que el problema no era el espacio sino la **ambigüedad**: seis lugares
hablaban de vigencias con cinco números que no concordaban —3 alertas, 3
vencidos, 2 en 30 días, "5 faltantes o vencidos" en seguros, "8" en
credenciales— y cada uno era correcto por separado.

Tres causas, y las tres se arreglan acá:

1. "Faltantes o vencidos" sumaba dos cosas que se arreglan distinto, y los
   faltantes **no generan alerta ni fila** (`LV-29`: un nulo es "nunca se
   ingresó"), así que ese número no tenía con quién conversar.
2. Las dos tarjetas de vencimientos son las dos mitades de la misma lista.
3. "Alertas pendientes" **ignoraba el filtro por centro de costo**.
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.compliance.models import Alert, AlertRule
from apps.registry.models import Aircraft, CostCenter, Operator

TODAY = timezone.localdate()


@pytest.fixture
def cost_center(db):
    return CostCenter.objects.create(code="CC738", name="MLP")


def _aircraft(cost_center, registration, expiry):
    return Aircraft.objects.create(
        registration=registration,
        serial_number=f"SN-{registration}",
        cost_center=cost_center,
        insurance_expiry=expiry,
        insurance_status="active" if expiry and expiry >= TODAY else "missing",
    )


def _client():
    User.objects.create_superuser("admin", "a@test.com", "password")
    client = Client()
    assert client.login(username="admin", password="password")
    return client


def _panel(client, **params):
    return client.get(reverse("dashboard"), params)


def _card(response, key):
    """La tarjeta por su clave estable, nunca por su etiqueta: la etiqueta
    es traducible y compararla contra el ingles falla bajo el locale espanol.
    """
    return next(item for item in response.context["readiness"] if item["key"] == key)


class TestLapsedAndMissingAreDifferentWork:
    """Renovar una póliza vencida y cargar una fecha que nadie ingresó son dos
    trabajos distintos. Sumados en una cifra, además, esa cifra no cuadraba con
    ninguna otra del panel."""

    @pytest.mark.django_db
    def test_they_are_counted_apart(self, cost_center):
        _aircraft(cost_center, "RPA-5534", TODAY - timedelta(days=12))
        _aircraft(cost_center, "RPA-2198", TODAY - timedelta(days=92))
        _aircraft(cost_center, "RPA-7126", None)

        response = _panel(_client())
        insurance = _card(response, "insurance")

        assert insurance["lapsed"] == 2
        assert insurance["missing"] == 1

    @pytest.mark.django_db
    def test_the_lapsed_count_matches_the_expiries_card(self, cost_center):
        """La afirmación que da sentido a toda la fila: **el mismo número**.

        Antes la tarjeta de seguros decía 5 y la de vencidos 3 sin que nada
        explicara la diferencia. Ahora "vencidos" quiere decir lo mismo en las
        dos, y lo que no cuadra es visible como "sin fecha".
        """
        _aircraft(cost_center, "RPA-5534", TODAY - timedelta(days=12))
        _aircraft(cost_center, "RPA-2198", TODAY - timedelta(days=92))
        _aircraft(cost_center, "RPA-7126", None)

        response = _panel(_client())
        insurance = _card(response, "insurance")

        assert insurance["lapsed"] == response.context["overdue_count"]

    @pytest.mark.django_db
    def test_credentials_split_the_same_way(self, cost_center):
        Operator.objects.create(
            employee_id="P1",
            full_name="Vencida",
            cost_center=cost_center,
            credential_expiry=TODAY - timedelta(days=5),
        )
        Operator.objects.create(
            employee_id="P2", full_name="Sin fecha", cost_center=cost_center
        )

        credentials = _card(_panel(_client()), "credentials")

        assert credentials["lapsed"] == 1
        assert credentials["missing"] == 1

    @pytest.mark.django_db
    def test_the_wording_reaches_the_page(self, cost_center):
        """Separarlas en el contexto y seguir imprimiendo la suma no arreglaría
        nada: lo que la persona lee es la plantilla."""
        _aircraft(cost_center, "RPA-5534", TODAY - timedelta(days=12))
        _aircraft(cost_center, "RPA-7126", None)

        content = _panel(_client()).content.decode()

        assert "1 vencido" in content
        assert "1 sin fecha cargada" in content
        assert "faltantes o vencidos" not in content


class TestOneExpiriesCardInsteadOfTwo:
    @pytest.mark.django_db
    def test_the_total_is_the_two_halves(self, cost_center):
        _aircraft(cost_center, "RPA-5534", TODAY - timedelta(days=12))
        _aircraft(cost_center, "RPA-4436", TODAY + timedelta(days=16))

        content = _panel(_client()).content.decode()

        # Una sola tarjeta con el total y el desglose debajo.
        assert "1 vencido" in content and "1 en 30 días" in content
        # Y ya no está la que sólo decía "Already expired".
        assert "Vencidos</small>" not in content

    @pytest.mark.django_db
    def test_it_is_absent_when_there_is_nothing(self, cost_center):
        """Una tarjeta en cero que aparece todos los días enseña a no mirar la
        fila -- la misma razón de `LV-122`."""
        _aircraft(cost_center, "RPA-4401", TODAY + timedelta(days=200))

        response = _panel(_client())

        assert response.context["overdue_count"] == 0
        assert response.context["expiring_count"] == 0
        assert "#upcoming-expirations" not in response.content.decode()


class TestTheSectionPointsAtWhereTheWorkHappens:
    @pytest.mark.django_db
    def test_it_links_to_the_alert_tray(self, cost_center):
        """No se duplica el filtro: se enlaza la pantalla que ya filtra,
        resuelve con motivo y guarda historial."""
        _aircraft(cost_center, "RPA-5534", TODAY - timedelta(days=12))

        content = _panel(_client()).content.decode()

        assert reverse("alert-list") in content
        assert "Trabajar en la bandeja" in content

    @pytest.mark.django_db
    def test_the_panel_does_not_grow_a_second_filter(self, cost_center):
        """El contrapeso de la decisión: si alguien agrega el selector acá, este
        test lo obliga a justificarlo."""
        _aircraft(cost_center, "RPA-5534", TODAY - timedelta(days=12))

        content = _panel(_client()).content.decode()

        assert 'name="is_resolved"' not in content


class TestPendingAlertsObeysTheCostCentreFilter:
    """El defecto concreto: elegir una faena cambiaba todas las tarjetas menos
    ésta, porque la consulta contaba las alertas de toda la operación."""

    @pytest.fixture
    def two_cost_centres(self, db):
        mine = CostCenter.objects.create(code="CC738", name="MLP")
        other = CostCenter.objects.create(code="CC999", name="Otra")
        rule = AlertRule.objects.create(
            name="Seguros JAC por vencer",
            entity_type="registry.aircraft",
            field_to_watch="insurance_expiry",
            days_before_expiry=30,
        )
        for cost_center, registration in ((mine, "RPA-MIA"), (other, "RPA-AJENA")):
            aircraft = _aircraft(cost_center, registration, TODAY - timedelta(days=10))
            Alert.objects.create(
                alert_rule=rule,
                content_type=ContentType.objects.get_for_model(Aircraft),
                object_id=aircraft.pk,
                message="Vigencia vencida",
                watched_value=(TODAY - timedelta(days=10)).isoformat(),
            )
        return mine, other

    @pytest.mark.django_db
    def test_filtering_narrows_the_count(self, two_cost_centres):
        mine, _other = two_cost_centres
        client = _client()

        assert _panel(client).context["alert_count"] == 2
        assert _panel(client, cost_center=mine.pk).context["alert_count"] == 1

    @pytest.mark.django_db
    def test_without_a_filter_nothing_is_hidden(self, two_cost_centres):
        """El contrapeso: acotar de más sería tan defecto como no acotar. Sin
        filtro se cuentan todas, incluidas las que no se pueden atribuir."""
        assert _panel(_client()).context["alert_count"] == 2

    @pytest.mark.django_db
    def test_an_alert_on_an_unattributable_record_drops_out_when_filtering(
        self, cost_center
    ):
        """Un documento de la empresa no cuelga de ninguna faena. Con filtro
        puesto no es de esa faena, que es la lectura honesta -- y sin filtro
        vuelve a contarse.

        **LV-204: el sujeto pasa a ser el tenant, que es lo que este test quiso
        decir siempre.** Colgaba del `CostCenter` y pasaba porque la tabla de
        rutas no tenía entrada para ese modelo — o sea, por la razón equivocada:
        un documento colgado de un centro de costo **sí** es de esa faena, de esa
        misma. Los documentos de empresa cuelgan del tenant, y así lo declara
        `DOCUMENTABLE_MODELS` con esas palabras. Al agregar la ruta que faltaba,
        el fixture quedó afirmando lo contrario de su propio docstring.
        """
        from apps.compliance.models import Document, DocumentType
        from apps.core.models import OperationalTenant

        doc_type = DocumentType.objects.create(code="aoc", name="AOC")
        aircraft = _aircraft(cost_center, "RPA-MIA", TODAY - timedelta(days=10))
        document = Document.objects.create(
            content_type=ContentType.objects.get_for_model(OperationalTenant),
            object_id=OperationalTenant.objects.first().pk,
            doc_type=doc_type,
            title="Procedimiento",
            file_path="x.pdf",
            issue_date=TODAY,
        )
        rule = AlertRule.objects.create(
            name="Documentos por vencer",
            entity_type="compliance.document",
            field_to_watch="expiry_date",
        )
        Alert.objects.create(
            alert_rule=rule,
            content_type=ContentType.objects.get_for_model(Document),
            object_id=document.pk,
            message="Vence",
        )
        assert aircraft is not None
        client = _client()

        assert _panel(client).context["alert_count"] == 1
        assert _panel(client, cost_center=cost_center.pk).context["alert_count"] == 0
