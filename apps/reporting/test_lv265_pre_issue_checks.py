"""LV-265: lo que hay que mirar antes de emitir el informe.

Una revisión del PDF de producción (2026-10-05) encontró cuatro desacuerdos que
el informe no avisaba: un permiso vigente cuya faena no sale en la tabla de
cobertura, una faena nombrada en un hallazgo que no existe, la observación del
período sin redactar y el total de faenas que bajó de 12 a 10.
"""

from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext

from apps.reporting.checks import (
    permits_outside_coverage,
    pre_issue_warnings,
    previous_total_change,
    unknown_codes_in_text,
)


def _payload(centres=("CC1", "CC2"), permits=(), total=None):
    return {
        "cost_centres": [{"code": code} for code in centres],
        "permits": [
            {"cost_centre": code, "folio": folio, "in_force": in_force}
            for code, folio, in_force in permits
        ],
        "kpis": {
            "cost_centres_with_operation": {"value": total or len(centres)},
        },
    }


def _run(note="", findings=(), editable=True):
    return SimpleNamespace(
        period_note=note, findings=list(findings), is_editable=editable
    )


class TestAPermitWhoseCentreIsNotListed:
    def test_it_names_the_centre_and_the_folio(self):
        payload = _payload(permits=[("CC716", "JEJ-2026-003", True)])
        assert permits_outside_coverage(payload) == [
            {"code": "CC716", "folios": ["JEJ-2026-003"]}
        ]

    def test_a_listed_centre_is_fine(self):
        assert not permits_outside_coverage(_payload(permits=[("CC1", "JEJ-1", True)]))

    def test_a_permit_not_in_force_is_not_the_problem(self):
        assert not permits_outside_coverage(
            _payload(permits=[("CC716", "JEJ-9", False)])
        )


class TestAnUnknownCentreInTheText:
    def test_a_finding_that_names_an_unregistered_centre(self):
        run = _run(findings=[{"title": "CC741 sin permiso", "text": "x"}])
        assert unknown_codes_in_text(_payload(), run) == ["CC741"]

    def test_a_code_written_with_a_space_is_still_seen(self):
        """El hallazgo real de septiembre decía «CC 741», con espacio."""
        run = _run(findings=[{"title": "Licencia", "text": "CC 741 presenta"}])
        assert unknown_codes_in_text(_payload(), run) == ["CC741"]

    def test_the_period_note_counts_too(self):
        assert unknown_codes_in_text(_payload(), _run(note="Ver CC741")) == ["CC741"]

    def test_a_listed_centre_and_a_permit_centre_are_known(self):
        run = _run(note="CC1 y CC716")
        payload = _payload(permits=[("CC716", "J", True)])
        assert unknown_codes_in_text(payload, run) == []

    def test_no_run_means_no_text(self):
        assert unknown_codes_in_text(_payload(), None) == []


class TestWhatIsStillUnwritten:
    def test_a_draft_without_note_or_findings_says_so(self):
        assert len(pre_issue_warnings(_payload(), _run())) == 2

    def test_an_approved_report_is_not_nagged(self):
        assert pre_issue_warnings(_payload(), _run(editable=False)) == []

    def test_a_written_draft_is_quiet(self):
        run = _run(note="n", findings=[{"title": "t", "text": "x"}])
        assert pre_issue_warnings(_payload(), run) == []

    def test_the_live_preview_has_no_run_and_says_nothing_about_text(self):
        assert pre_issue_warnings(_payload(), None) == []


class TestTheTotalMoved:
    def _previous(self, total):
        return SimpleNamespace(payload=_payload(total=total))

    def test_a_drop_is_reported_with_both_figures(self):
        assert previous_total_change(_payload(total=10), self._previous(12)) == (12, 10)

    def test_the_same_total_is_silent(self):
        assert previous_total_change(_payload(total=10), self._previous(10)) is None

    def test_no_previous_report_is_silent(self):
        assert previous_total_change(_payload(total=10), None) is None

    def test_the_warning_carries_the_figures(self):
        text = pre_issue_warnings(_payload(total=10), None, self._previous(12))
        assert "12" in text[0] and "10" in text[0]


@pytest.mark.django_db
class TestOnTheScreen:
    def test_a_closed_centre_with_a_live_permit_is_flagged(self, client, admin_user):
        """El caso real: la faena se cerró, el permiso sigue vivo, y la tabla de
        cobertura no la lista aunque la hoja de permisos sí."""
        from apps.operations.models import FlightPermission
        from apps.registry.models import CostCenter

        today = timezone.localdate()
        closed = CostCenter.objects.create(
            code="CC716",
            name="Cerrada",
            operates_flights=True,
            contract_status=CostCenter.CONTRACT_CLOSED,
        )
        permit = FlightPermission.objects.create(
            cost_center=closed,
            purpose="photogrammetry",
            status=FlightPermission.STATUS_APPROVED,
            location="Sector",
            area_type="unpopulated",
            valid_from=today - timedelta(days=5),
            valid_until=today + timedelta(days=30),
        )
        client.force_login(admin_user)
        with translation.override("es"):
            body = client.get(
                reverse("monthly-report"), {"period": f"{today:%Y-%m}"}
            ).content.decode()
            heading = gettext("Review before issuing")
        assert heading in body
        warning = body.split(heading, 1)[1].split("</div>", 1)[0]
        assert "CC716" in warning and permit.internal_folio in warning
