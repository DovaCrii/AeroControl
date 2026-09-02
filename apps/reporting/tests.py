"""R0/R2 del informe mensual RPA: el informe congelado y su payload.

Referencias: `SPEC_REPORTE_MENSUAL_RPA.md` (el contrato), `MAPPING.md` (campo →
modelo real) y el informe de agosto ya emitido, que es la referencia de qué hay
que producir.

**Lo que estos tests protegen sobre todo es la regla que manda en el SPEC: el
informe nunca inventa un dato.** Un cero es una afirmación ("hay cero") y `None`
es la ausencia de una ("no se sabe"); confundirlas haría que el informe declarara
cumplimiento donde sólo hay un hueco de carga, y eso va firmado ante la DGAC.
"""

from datetime import date, timedelta

import pytest
from django.db.utils import IntegrityError
from django.utils import timezone

from apps.operations.models import FlightPermission
from apps.registry.models import Aircraft, CostCenter, Operator
from apps.reporting.builder import build, find_missing, leaf, month_bounds
from apps.reporting.models import ReportRun


class TestTheMonthIsBounded:
    def test_a_normal_month(self):
        assert month_bounds(date(2026, 8, 1)) == (date(2026, 8, 1), date(2026, 8, 31))

    def test_it_takes_any_day_of_the_month(self):
        """El período es el mes, no el día que se pase."""
        assert month_bounds(date(2026, 8, 17)) == (date(2026, 8, 1), date(2026, 8, 31))

    def test_february_in_a_leap_year(self):
        assert month_bounds(date(2028, 2, 3))[1] == date(2028, 2, 29)

    def test_february_in_a_common_year(self):
        assert month_bounds(date(2027, 2, 3))[1] == date(2027, 2, 28)

    def test_december_crosses_the_year(self):
        """Sumar un mes a diciembre es el caso que rompe la cuenta ingenua."""
        assert month_bounds(date(2026, 12, 9)) == (
            date(2026, 12, 1),
            date(2026, 12, 31),
        )


class TestMissingIsNotZero:
    def test_a_none_leaf_is_reported_as_missing(self):
        payload = {"kpis": {"a": leaf(None, "registry", date(2026, 8, 31))}}

        assert find_missing(payload) == ["kpis.a"]

    def test_a_zero_leaf_is_not_missing(self):
        """**La distinción de la que depende todo el informe.**

        Cero significa "se miró y no hay ninguno"; ausente significa "no se
        sabe". Un informe que las mezcle puede declarar cumplimiento sobre un
        hueco de carga — y va firmado ante la autoridad.
        """
        payload = {"kpis": {"a": leaf(0, "registry", date(2026, 8, 31))}}

        assert find_missing(payload) == []

    def test_it_finds_leaves_inside_lists(self):
        payload = {
            "rows": [
                {"x": leaf(1, "s", date(2026, 8, 31))},
                {"x": leaf(None, "s", date(2026, 8, 31))},
            ]
        }

        assert find_missing(payload) == ["rows[1].x"]

    def test_every_leaf_carries_its_source_and_cutoff(self):
        """El informe cita "Fuente: AeroControl, corte al 31-08-2026" al pie.

        Esa frase tiene que poder reconstruirse del dato, no escribirse a mano.
        """
        one = leaf(3, "operations", date(2026, 8, 31))

        assert one == {"value": 3, "source": "operations", "cutoff": "2026-08-31"}


@pytest.fixture
def operating_site(db):
    return CostCenter.objects.create(code="CC738", name="MLP", operates_flights=True)


@pytest.fixture
def warehouse(db):
    return CostCenter.objects.create(
        code="CC110", name="Casa matriz", operates_flights=False
    )


class TestThePayloadReadsTheDomain:
    @pytest.mark.django_db
    def test_it_counts_a_permit_in_force_at_the_cutoff(self, operating_site):
        today = timezone.localdate()
        FlightPermission.objects.create(
            cost_center=operating_site,
            purpose="photogrammetry",
            status=FlightPermission.STATUS_APPROVED,
            permission_number="P-1",
            location="Site",
            area_type="unpopulated",
            valid_from=today - timedelta(days=30),
            valid_until=today + timedelta(days=30),
        )

        payload, _missing = build(today.replace(day=1), cutoff=today)

        assert payload["kpis"]["permits_in_force"]["value"] == 1

    @pytest.mark.django_db
    def test_a_cost_centre_without_permits_still_appears(self, operating_site):
        """La página 3 del informe emitido lista 7 faenas **sin** habilitación.

        Es el dato que el informe existe para mostrar, así que la fila tiene que
        estar aunque no tenga ningún permiso — `LV-206` construyó la consulta
        partiendo de las faenas justamente por esto.
        """
        today = timezone.localdate()

        payload, _missing = build(today.replace(day=1), cutoff=today)

        rows = {row["code"]: row for row in payload["cost_centres"]}
        assert "CC738" in rows
        assert rows["CC738"]["permits_in_force"] == 0

    @pytest.mark.django_db
    def test_a_non_flying_cost_centre_is_left_out(self, operating_site, warehouse):
        """`LV-205`/`LV-229`: `CC110` administra equipos y no vuela.

        Listarla como faena con operación la declararía incumplida por algo que
        no le toca.
        """
        today = timezone.localdate()

        payload, _missing = build(today.replace(day=1), cutoff=today)

        codes = {row["code"] for row in payload["cost_centres"]}
        assert codes == {"CC738"}
        assert payload["kpis"]["cost_centres_with_operation"]["value"] == 1

    @pytest.mark.django_db
    def test_the_fleet_and_roster_figures_come_from_the_panel(self, operating_site):
        """Los mismos números que el panel, no un recuento paralelo.

        Dos funciones contando lo mismo es cómo el panel y el informe empiezan a
        discrepar — la lección que `LV-148` dejó con la escala de urgencia.
        """
        today = timezone.localdate()
        Aircraft.objects.create(
            registration="RPA-7126",
            type="Multirotor",
            model="M3E",
            manufacturer="DJI",
            cost_center=operating_site,
        )
        Operator.objects.create(
            employee_id="P1", full_name="Pilot One", cost_center=operating_site
        )

        payload, _missing = build(today.replace(day=1), cutoff=today)

        assert payload["kpis"]["fleet_total"]["value"] == 1
        assert payload["kpis"]["operators_total"]["value"] == 1

    @pytest.mark.django_db
    def test_the_cutoff_defaults_to_the_end_of_the_month(self, operating_site):
        """Un informe mensual describe el mes cerrado, no el día en que se corre.

        Con "hoy" como corte, el mismo período daría cifras distintas según
        cuándo se generara — que es lo que congelar el dato viene a evitar.
        """
        payload, _missing = build(date(2026, 8, 1))

        assert payload["meta"]["cutoff"] == "2026-08-31"
        assert payload["kpis"]["permits_in_force"]["cutoff"] == "2026-08-31"

    @pytest.mark.django_db
    def test_the_code_matches_the_issued_report(self, operating_site):
        """El de agosto dice `JEJ-GTE-CT-INF-RPA-2026-08`."""
        payload, _missing = build(date(2026, 8, 1))

        assert payload["meta"]["code"] == "JEJ-GTE-CT-INF-RPA-2026-08"


class TestTheRunIsAControlledDocument:
    @pytest.mark.django_db
    def test_the_same_period_can_have_two_revisions(self):
        """**Corrige una contradicción del SPEC.**

        Su §1.1 pide que el período sea único y su §5.1 dice que `--force` crea
        una versión nueva sin sobrescribir: las dos no pueden ser ciertas. El
        informe es un documento controlado —la portada del de agosto dice
        "Revisión 0"—, así que la revisión es parte de su identidad.
        """
        ReportRun.objects.create(period=date(2026, 8, 1), generated_by="cron")
        ReportRun.objects.create(
            period=date(2026, 8, 1), revision=1, generated_by="demo"
        )

        assert ReportRun.objects.filter(period=date(2026, 8, 1)).count() == 2

    @pytest.mark.django_db
    def test_the_same_revision_of_a_period_cannot_repeat(self):
        ReportRun.objects.create(period=date(2026, 8, 1), generated_by="cron")

        with pytest.raises(IntegrityError):
            ReportRun.objects.create(period=date(2026, 8, 1), generated_by="otro")

    @pytest.mark.django_db
    def test_the_code_is_composed_not_stored(self):
        """Una columna con lo mismo sería una que puede discrepar de su fecha."""
        run = ReportRun.objects.create(period=date(2026, 8, 1), generated_by="cron")

        assert run.code == "JEJ-GTE-CT-INF-RPA-2026-08"
        assert str(run) == "JEJ-GTE-CT-INF-RPA-2026-08 rev. 0"

    @pytest.mark.django_db
    def test_an_approved_run_is_no_longer_editable(self):
        """Aprobado es el documento que se envió: reescribirlo dejaría a la DGAC
        con una copia que ya no existe de este lado."""
        run = ReportRun.objects.create(period=date(2026, 8, 1), generated_by="cron")
        assert run.is_editable

        run.status = ReportRun.STATUS_APPROVED

        assert not run.is_editable

    @pytest.mark.django_db
    def test_the_missing_fields_are_stored_not_recalculated(self):
        """`LV-118` en otro contexto: el informe dice qué faltaba **al emitirse**.

        Si se recalculara, un informe de agosto mejoraría solo al cargarse los
        datos en septiembre, y con él desaparecería la evidencia de la brecha que
        reportó.
        """
        run = ReportRun.objects.create(
            period=date(2026, 8, 1),
            generated_by="cron",
            missing_fields=["kpis.flights_in_month"],
        )

        run.refresh_from_db()
        assert run.missing_fields == ["kpis.flights_in_month"]
