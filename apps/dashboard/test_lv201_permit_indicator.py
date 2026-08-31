"""LV-201: el panel y el informe dicen cuántos permisos hay vigentes.

Pedido del usuario mirando el panel: *"es importante mencionar tanto en los
reportes como en el dashboard la cantidad de permisos vigentes, atrasados, o el
indicador en general"*. La fila mostraba flota, seguros y credenciales — y
ninguna cifra del objeto que esta aplicación existe para tramitar.

No es una tarjeta nueva inventada: `LV-89` **retiró** un gráfico "Permissions by
status" porque restataba números sin decir qué hacer, y los permisos vuelven con
la forma que esa fila fijó — una fracción con su faltante nombrado.

**Las dos palabras del pedido, "reportes" y "dashboard", son el diseño**: el
cálculo vive una sola vez, en `kpis.permit_counts`, y lo leen las dos pantallas.
El test que sostiene eso es `test_the_report_and_the_panel_cannot_disagree`;
`LV-188` acabó de mostrar lo que cuesta que dos mitades del mismo cálculo se
separen.
"""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.compliance.kpis import permit_counts
from apps.compliance.reports import build_compliance_report
from apps.operations.models import FlightPermission
from apps.registry.models import CostCenter

TODAY = timezone.localdate()


@pytest.fixture
def center(db):
    return CostCenter.objects.create(code="CC738", name="MLP")


def _permit(center, folio, status, until_days, from_days=-1):
    return FlightPermission.objects.create(
        internal_folio=folio,
        cost_center=center,
        purpose="patrol",
        valid_from=TODAY + timedelta(days=from_days),
        valid_until=TODAY + timedelta(days=until_days),
        location="Quebrada km 13",
        area_type="unpopulated",
        status=status,
    )


@pytest.fixture
def a_bit_of_everything(center):
    """Un permiso de cada situación que la fila distingue."""
    _permit(center, "JEJ-001", FlightPermission.STATUS_APPROVED, 60)  # vigente
    _permit(center, "JEJ-002", FlightPermission.STATUS_APPROVED, 10)  # vigente, pronto
    _permit(center, "JEJ-003", FlightPermission.STATUS_APPROVED, -5)  # vigencia pasada
    _permit(center, "JEJ-004", FlightPermission.STATUS_REQUESTED, 60)  # esperando
    _permit(center, "JEJ-005", FlightPermission.STATUS_EXPIRED, -90)  # caducado
    _permit(center, "JEJ-006", FlightPermission.STATUS_DENIED, -90)  # rechazado
    return center


@pytest.mark.django_db
class TestWhatItCounts:
    def test_in_force_is_approved_and_still_valid(self, a_bit_of_everything):
        assert permit_counts(TODAY)["in_force"] == 2

    def test_the_denominator_leaves_out_what_already_ended(self, a_bit_of_everything):
        """Caducado y rechazado quedan fuera: con la historia acumulada, contarlos
        haría caer el porcentaje para siempre. Es la razón por la que
        `fleet_availability` excluye `retired`, escrita en su comentario — un
        permiso que caducó no es un permiso incumplido, terminó."""
        assert permit_counts(TODAY)["total"] == 4  # 3 aprobados + 1 solicitado

    def test_the_two_shortfalls_are_separate(self, a_bit_of_everything):
        """`LV-129`: una cifra para dos trabajos que se arreglan distinto es la
        que no cuadra con nada. Esperar a la DGAC no es lo mismo que un permiso
        aprobado que caducó y nadie cerró."""
        counts = permit_counts(TODAY)

        assert counts["awaiting"] == 1
        assert counts["lapsed"] == 1

    def test_expiring_soon_only_counts_the_ones_in_force(self, a_bit_of_everything):
        assert permit_counts(TODAY)["soon"] == 1

    def test_it_respects_the_cost_center_filter(self, a_bit_of_everything):
        """Un permiso pertenece a una faena, y la pregunta "cuántos tengo
        vigentes" se hace por faena — como el resto de la fila (`LV-129`)."""
        other = CostCenter.objects.create(code="CC861", name="Talabre")
        _permit(other, "JEJ-007", FlightPermission.STATUS_APPROVED, 60)

        assert permit_counts(TODAY, other)["in_force"] == 1
        assert permit_counts(TODAY)["in_force"] == 3

    def test_no_permits_is_no_percentage_not_zero(self, center):
        """Un 0% sin un solo permiso se lee como fracaso total; `None` deja que la
        pantalla no dibuje el porcentaje, igual que hace la flota vacía."""
        assert permit_counts(TODAY)["pct"] is None


@pytest.mark.django_db
class TestBothScreensShowIt:
    def _panel(self, client, django_user_model):
        django_user_model.objects.create_superuser("admin", "a@test.com", "password")
        assert client.login(username="admin", password="password")
        return client.get(reverse("dashboard"))

    def test_the_panel_row_is_there(
        self, a_bit_of_everything, client, django_user_model
    ):
        response = self._panel(client, django_user_model)

        row = next(
            item for item in response.context["readiness"] if item["key"] == "permits"
        )
        assert row["count"] == 2
        assert row["total"] == 4
        assert row["url"] == reverse("permission-list")

    def test_awaiting_is_drawn_next_to_lapsed_and_not_instead(
        self, a_bit_of_everything, client, django_user_model
    ):
        """La plantilla ofrecía `lapsed`/`missing` **o** `shortfall`, exclusivos.
        Con un permiso en cada situación, las dos cifras tienen que verse."""
        content = self._panel(client, django_user_model).content.decode()

        assert "esperando aprobación" in content
        assert "vencido" in content

    def test_the_report_and_the_panel_cannot_disagree(
        self, a_bit_of_everything, client, django_user_model
    ):
        """**El test que sostiene el diseño.** El pedido nombraba las dos
        pantallas; si cada una calculara lo suyo, el informe que se imprime y el
        panel que se mira dirían números distintos, y el impreso es el que se
        discute en una reunión."""
        response = self._panel(client, django_user_model)
        row = next(
            item for item in response.context["readiness"] if item["key"] == "permits"
        )

        report = build_compliance_report()

        assert report["permits"]["in_force"] == row["count"]
        assert report["permits"]["total"] == row["total"]
        assert report["permits"]["lapsed"] == row["lapsed"]
        assert report["permits"]["awaiting"] == row["awaiting"]

    def test_the_report_page_prints_it(
        self, a_bit_of_everything, client, django_user_model
    ):
        django_user_model.objects.create_superuser("admin", "a@test.com", "password")
        assert client.login(username="admin", password="password")

        content = client.get(reverse("compliance-report")).content.decode()

        assert "Permisos vigentes" in content
        # La tarjeta de vigencia pasada sólo aparece cuando hay algo que mostrar.
        assert "Permisos con la vigencia pasada" in content

    def test_the_past_validity_card_is_absent_when_there_is_none(
        self, center, client, django_user_model
    ):
        """Una tarjeta en cero que aparece todos los días enseña a no mirar la
        fila — la regla que `LV-120` fijó para la de vencidos."""
        _permit(center, "JEJ-001", FlightPermission.STATUS_APPROVED, 60)
        django_user_model.objects.create_superuser("admin", "a@test.com", "password")
        assert client.login(username="admin", password="password")

        content = client.get(reverse("compliance-report")).content.decode()

        assert "Permisos con la vigencia pasada" not in content
