"""LV-251: qué cambió entre dos informes.

El pedido del 2026-09-08 que quedó pendiente: *"lo que se modifica y los cambios más
claro"*. La vista del informe prometía "comparar" y no había ninguna.

⚠️ **Compara payloads congelados, nunca recalcula.** Un informe es lo que dijo
cuando se emitió; recalcular para comparar mediría la base de hoy contra la de hoy.
"""

from datetime import date

import pytest
from django.contrib.auth.models import Permission, User
from django.urls import reverse

from apps.reporting.compare import (
    KPI_LABELS,
    baselines_for,
    compare_kpis,
    compare_narrative,
    compare_permits,
)
from apps.reporting.models import ReportRun


def _payload(**kpis):
    return {
        "kpis": {key: {"value": value} for key, value in kpis.items()},
        "permits": [],
    }


class TestTheIndicators:
    def test_a_change_carries_its_difference(self):
        rows = {
            row["key"]: row
            for row in compare_kpis(
                _payload(permits_in_force=11), _payload(permits_in_force=13)
            )
        }

        assert rows["permits_in_force"]["delta"] == 2
        assert rows["permits_in_force"]["changed"] is True

    def test_an_unchanged_indicator_is_still_listed(self):
        """Saber que una cifra **no** se movió también es información."""
        rows = compare_kpis(_payload(fleet_total=16), _payload(fleet_total=16))

        fleet = next(row for row in rows if row["key"] == "fleet_total")
        assert fleet["changed"] is False
        assert len(rows) == len(KPI_LABELS)

    def test_an_indicator_the_old_report_did_not_have_is_not_a_zero(self):
        """Un informe congelado antes de que un indicador existiera **no dice** que
        valía cero. Mostrar un cero inventaría un dato en una comparación que va a
        leer quien firma."""
        rows = compare_kpis(_payload(), _payload(incidents=2))

        incidents = next(row for row in rows if row["key"] == "incidents")
        assert incidents["before"] is None
        assert incidents["delta"] is None

    @pytest.mark.django_db
    def test_every_kpi_has_a_label(self):
        """⚠️ Los rótulos están declarados, no descubiertos del payload. Un
        indicador nuevo que entre al builder sin su rótulo aparecería con su nombre
        técnico en una pantalla en español: este test cruza las dos listas."""
        from apps.reporting.builder import build

        payload, _missing = build(date(2026, 8, 1), cutoff=date(2026, 8, 31))

        assert set(payload["kpis"]) == {key for key, _label in KPI_LABELS}


class TestThePermits:
    def test_permits_are_matched_by_folio_not_by_position(self):
        """La tabla se ordena por vencimiento: un permiso que sólo cambió de fecha
        se movería de fila sin haber entrado ni salido."""
        before = {
            "permits": [
                {"folio": "JEJ-001", "in_force": True},
                {"folio": "JEJ-002", "in_force": True},
            ]
        }
        after = {
            "permits": [
                {"folio": "JEJ-002", "in_force": True},
                {"folio": "JEJ-003", "in_force": True},
                {"folio": "JEJ-004", "in_force": False},
            ]
        }

        result = compare_permits(before, after)

        assert result["in_force"] == {"added": ["JEJ-003"], "removed": ["JEJ-001"]}
        assert result["awaiting"] == {"added": ["JEJ-004"], "removed": []}


@pytest.mark.django_db
class TestTheNarrative:
    def test_only_the_blocks_that_changed_are_listed(self):
        before = ReportRun(
            period_note="Vigencias no uniformes.", findings=[], actions=[]
        )
        after = ReportRun(
            period_note="Vigencias no uniformes.",
            findings=[{"title": "Faenas sin permiso", "text": "Siete de quince."}],
            actions=[],
        )

        blocks = compare_narrative(before, after)

        assert [block["key"] for block in blocks] == ["findings"]
        assert blocks[0]["after"] == ["Faenas sin permiso — Siete de quince."]


@pytest.mark.django_db
class TestWhichReportItIsComparedWith:
    def test_a_revision_compares_with_the_one_it_corrected(self):
        """La **inmediatamente** anterior, no la cero: es la que esta corrigió."""
        first, _ = ReportRun.freeze(date(2026, 8, 1), "lv251")
        second, _ = ReportRun.freeze(date(2026, 8, 1), "lv251", force=True)
        third, _ = ReportRun.freeze(date(2026, 8, 1), "lv251", force=True)

        assert baselines_for(third)["revision"] == second
        assert baselines_for(first)["revision"] is None

    def test_the_previous_month_is_its_latest_revision(self):
        """La vigente, no una reemplazada: comparar contra un documento que ya no
        vale mediría contra otra cosa."""
        ReportRun.freeze(date(2026, 7, 1), "lv251")
        july_latest, _ = ReportRun.freeze(date(2026, 7, 1), "lv251", force=True)
        august, _ = ReportRun.freeze(date(2026, 8, 1), "lv251")

        assert baselines_for(august)["month"] == july_latest


@pytest.mark.django_db
class TestTheScreen:
    def _user(self, *codenames):
        user = User.objects.create_user("lv251", password="pw")
        for codename in codenames:
            user.user_permissions.add(
                Permission.objects.get(
                    content_type__app_label="reporting", codename=codename
                )
            )
        return user

    def test_without_the_read_permission_it_is_forbidden(self, client):
        run, _ = ReportRun.freeze(date(2026, 8, 1), "lv251")
        client.force_login(self._user())

        response = client.get(reverse("monthly-report-compare", args=[run.pk]))

        assert response.status_code == 403

    def test_reading_is_enough_to_compare(self, client):
        """Comparar no escribe nada: quien puede ver el informe puede ver en qué
        cambió."""
        ReportRun.freeze(date(2026, 7, 1), "lv251")
        august, _ = ReportRun.freeze(date(2026, 8, 1), "lv251")
        client.force_login(self._user("view_reportrun"))

        response = client.get(reverse("monthly-report-compare", args=[august.pk]))

        assert response.status_code == 200
        assert response.context["against"] == "month"
        assert "Indicadores" in response.content.decode()

    def test_with_nothing_to_compare_it_says_so(self, client, admin_user):
        run, _ = ReportRun.freeze(date(2026, 8, 1), "lv251")
        client.force_login(admin_user)

        response = client.get(reverse("monthly-report-compare", args=[run.pk]))

        assert response.context["baseline"] is None
        assert "Todavía no hay con qué comparar" in response.content.decode()
