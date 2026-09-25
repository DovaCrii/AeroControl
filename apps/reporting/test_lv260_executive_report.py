"""LV-260: el informe más corto — hoja ejecutiva + detalle.

Pedido del usuario el 2026-09-25: el informe *"aún no convence"*; al preguntarle
qué fallaba eligió **«demasiado largo»** y la dirección **«hoja ejecutiva +
detalle»**. Lo que se fija acá:

- la hoja ejecutiva sale **sólo del payload** y dice la conclusión primero;
- el color de cada indicador depende de su valor (en agosto «0 permisos
  vigentes» salía en verde);
- la hoja de permisos no repite los contadores del resumen;
- el plan compacto comparte hoja con la cobertura cuando cabe, **medido**, y si
  no, va a su hoja.
"""

from datetime import timedelta

import pytest
from django.urls import reverse

from apps.reporting.pagination import plan_fits_with_coverage
from apps.reporting.summary import NEXT_TO_EXPIRE, executive_summary
from apps.reporting.views import MonthlyReportView


def _leaf(value):
    return {"value": value, "source": "operations", "cutoff": "2026-09-25"}


def _payload(centres=3, without=1, permits=7, **kpis):
    rows = [
        {
            "code": f"CC{n}",
            "name": f"Faena {n}",
            "permits_in_force": 0 if n < without else 1,
        }
        for n in range(centres)
    ]
    permit_rows = [
        {
            "folio": f"JEJ-{n:03d}",
            "cost_centre": "CC9",
            "valid_until": f"2026-10-{n + 1:02d}",
            "days_remaining": 40 - n * 5,
            "band": "warning",
            "in_force": True,
            "operators": ["A"],
            "aircraft": [],
        }
        for n in range(permits)
    ]
    values = {
        "permits_in_force": permits,
        "permits_expiring_30d": 0,
        "permits_expiring_60d": permits,
        "permits_awaiting": 0,
        "permits_lapsed": 0,
        "incidents": 0,
        "incidents_open": 0,
    }
    values.update(kpis)
    return {
        "cost_centres": rows,
        "permits": permit_rows,
        "kpis": {key: _leaf(value) for key, value in values.items()},
    }


class TestTheConclusionComesFromThePayload:
    def test_it_names_the_cost_centres_that_cannot_fly(self):
        summary = executive_summary(_payload(centres=4, without=2))

        assert summary["without_permit"] == ["CC0", "CC1"]
        assert summary["enabled"] == 2
        assert summary["cost_centres_total"] == 4

    def test_the_first_to_expire_is_the_soonest_and_not_the_first_listed(self):
        summary = executive_summary(_payload(permits=4))

        assert summary["first_to_expire"]["days_remaining"] == min(
            row["days_remaining"] for row in _payload(permits=4)["permits"]
        )

    def test_the_list_is_cut_and_says_how_many_are_left(self):
        summary = executive_summary(_payload(permits=NEXT_TO_EXPIRE + 3))

        assert len(summary["next_to_expire"]) == NEXT_TO_EXPIRE
        assert summary["more_to_expire"] == 3

    def test_a_bar_is_never_empty(self):
        """Una barra vacía se lee como «no hay dato»; un permiso que vence hoy sí
        lo tiene."""
        payload = _payload(permits=1)
        payload["permits"][0]["days_remaining"] = 0

        assert executive_summary(payload)["next_to_expire"][0]["bar_pct"] > 0

    def test_a_payload_frozen_before_this_change_still_draws(self):
        """Un informe congelado antes de `R4` no trae `permits` ni todas las hojas
        de `kpis`: la hoja se tiene que dibujar igual, no reventar."""
        summary = executive_summary({"kpis": {}, "cost_centres": []})

        assert summary["next_to_expire"] == []
        assert summary["first_to_expire"] is None


class TestTheColourFollowsTheValue:
    def test_no_permit_in_force_is_critical_and_never_green(self):
        """El defecto de agosto: «0 permisos vigentes» en verde."""
        tones = executive_summary(_payload(permits=0, permits_in_force=0))["kpis"]

        assert tones["in_force"] == "critical"

    def test_expiring_within_30_days_is_critical(self):
        tones = executive_summary(
            _payload(permits_expiring_30d=1, permits_expiring_60d=3)
        )["kpis"]

        assert tones["expiring"] == "critical"

    def test_nothing_expiring_is_good(self):
        tones = executive_summary(
            _payload(permits_expiring_30d=0, permits_expiring_60d=0)
        )["kpis"]

        assert tones["expiring"] == "good"

    def test_every_cost_centre_enabled_is_good(self):
        assert executive_summary(_payload(without=0))["kpis"]["enabled"] == "good"
        assert executive_summary(_payload(without=1))["kpis"]["enabled"] == "critical"


class TestThePlanSharesTheSheetWhenItFits:
    """Las constantes salen de medir el informe con la forma de producción
    (ver `pagination.py`): con 12 faenas el plan terminaba bajo el pie."""

    def test_nine_cost_centres_fit(self):
        assert plan_fits_with_coverage(9, 4)

    def test_twelve_do_not(self):
        assert not plan_fits_with_coverage(12, 4)

    def test_a_longer_matrix_needs_room_too(self):
        assert plan_fits_with_coverage(9, 4)
        assert not plan_fits_with_coverage(9, 12)

    def test_when_it_does_not_fit_the_plan_gets_its_sheet(self):
        payload = _payload(centres=12)

        sheets = MonthlyReportView._sheets(payload)

        assert sheets["plan_joins_coverage"] is False
        assert sheets["plan_page"] == sheets["coverage_page"] + 1
        assert sheets["coverage_section"] == "coverage"

    def test_when_it_fits_there_is_one_sheet_less(self):
        short = MonthlyReportView._sheets(_payload(centres=5))
        long = MonthlyReportView._sheets(_payload(centres=12))

        assert short["plan_joins_coverage"] is True
        assert short["plan_page"] is None
        assert short["coverage_section"] == "coverage_plan"
        assert short["total_pages"] == long["total_pages"] - 1


@pytest.mark.django_db
class TestThePaper:
    @pytest.fixture
    def body(self, client, admin_user):
        from django.utils import timezone

        from apps.operations.models import FlightPermission
        from apps.registry.models import CostCenter

        today = timezone.localdate()
        centre = CostCenter.objects.create(
            code="CC260", name="Faena", operates_flights=True
        )
        CostCenter.objects.create(
            code="CC261", name="Sin permiso", operates_flights=True
        )
        FlightPermission.objects.create(
            cost_center=centre,
            purpose="photogrammetry",
            status=FlightPermission.STATUS_APPROVED,
            location="Sector",
            area_type="unpopulated",
            valid_from=today - timedelta(days=10),
            valid_until=today + timedelta(days=12),
        )
        client.force_login(admin_user)
        return client.get(
            reverse("monthly-report"), {"period": f"{today:%Y-%m}"}
        ).content.decode()

    def test_the_summary_opens_with_the_conclusion(self, body):
        summary = body.split("Resumen ejecutivo", 1)[1].split("Indicadores al", 1)[0]

        assert 'class="rpt-verdict"' in summary
        assert "1 de 2 Centros de Costo sin permiso vigente" in summary
        assert "CC261" in summary

    def test_the_permits_sheet_does_not_repeat_the_counters(self, body):
        permits = body.split("Permisos de vuelo vigentes ante la DGAC", 1)[1].split(
            "Detalle permiso a permiso", 1
        )[0]

        assert "rpt-kpis" not in permits

    def test_the_plan_is_drawn_once(self, body):
        """Debajo de la cobertura o en su hoja, nunca en las dos."""
        assert body.count("Plan de normalización de operaciones aéreas") == 1

    def test_the_old_padron_card_is_gone(self, body):
        """Repetía la dotación de la hoja ejecutiva."""
        assert "Cobertura del padrón" not in body
        assert "Dotación al corte" in body
