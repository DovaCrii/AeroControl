"""LV-439: una prueba de conocimientos reprobada no cuenta como vigente.

`KnowledgeAssessment.expires_on` se sella a 12 meses también en el intento
reprobado (`assessment_views`), y las dos lecturas que juzgan la vigencia
—«¿Puedo volar?» y la lista de vencimientos— sólo miraban la fecha: un
reprobado reciente salía como «en vigor». Regla: la vigencia es la del último
intento **aprobado**; un reprobado posterior no anula un aprobado vigente.
"""

from datetime import date, timedelta

import pytest
from django.utils import timezone

from apps.compliance.expirations import upcoming_expirations
from apps.core.testing import login_as
from apps.operations.readiness import _check_operator
from apps.registry.models import CostCenter, KnowledgeAssessment, Operator

TODAY = date(2026, 9, 7)
CUTOFF = TODAY + timedelta(days=30)


@pytest.fixture
def operator(db):
    centre = CostCenter.objects.create(code="CC738", name="MLP")
    return Operator.objects.create(
        employee_id="E1",
        full_name="Ana Rivas",
        cost_center=centre,
        credential_expiry=TODAY + timedelta(days=200),
    )


def _attempt(operator, *, passed, taken_days_ago, expires_in):
    row = KnowledgeAssessment.objects.create(
        operator=operator,
        question_count=25,
        correct_count=25 if passed else 10,
        score_percent=100 if passed else 40,
        passed=passed,
        expires_on=TODAY + timedelta(days=expires_in),
    )
    KnowledgeAssessment.objects.filter(pk=row.pk).update(
        taken_at=timezone.now() - timedelta(days=taken_days_ago)
    )
    return row


def _assessment_findings(operator):
    # Credencial y habilitaciones de la fixture están al día: todo hallazgo es
    # de la prueba.
    check = _check_operator(operator, TODAY)
    return check.blockers + check.warnings


def _listed(operator):
    user = login_as("view_knowledgeassessment", "view_operator").user
    return [
        row
        for row in upcoming_expirations(TODAY, CUTOFF, None, user)
        # La credencial de la fixture vence en 200 días: toda fila de esta
        # persona dentro de la ventana es de la prueba.
        if row["label"] == str(operator)
    ]


class TestReadiness:
    def test_a_failed_attempt_alone_blocks(self, operator):
        _attempt(operator, passed=False, taken_days_ago=1, expires_in=365)

        assert _assessment_findings(operator)
        assert not _check_operator(operator, TODAY).passed

    def test_a_valid_pass_followed_by_a_fail_still_counts(self, operator):
        _attempt(operator, passed=True, taken_days_ago=30, expires_in=300)
        _attempt(operator, passed=False, taken_days_ago=1, expires_in=365)

        assert _check_operator(operator, TODAY).passed

    def test_an_expired_pass_blocks(self, operator):
        _attempt(operator, passed=True, taken_days_ago=400, expires_in=-1)

        assert not _check_operator(operator, TODAY).passed

    def test_an_expired_pass_does_not_hide_behind_a_fresh_fail(self, operator):
        _attempt(operator, passed=True, taken_days_ago=400, expires_in=-1)
        _attempt(operator, passed=False, taken_days_ago=1, expires_in=365)

        assert not _check_operator(operator, TODAY).passed

    def test_no_attempt_at_all_stays_silent(self, operator):
        """Sin prueba cargada no hay nada que juzgar: no cambia lo de siempre."""
        assert _check_operator(operator, TODAY).passed


class TestExpirations:
    def test_a_failed_attempt_is_not_listed_as_a_validity(self, operator):
        _attempt(operator, passed=False, taken_days_ago=1, expires_in=10)

        assert _listed(operator) == []

    def test_the_pass_is_listed_even_if_a_fail_came_later(self, operator):
        passed = _attempt(operator, passed=True, taken_days_ago=30, expires_in=10)
        _attempt(operator, passed=False, taken_days_ago=1, expires_in=10)

        rows = _listed(operator)
        assert len(rows) == 1
        assert rows[0]["date"] == passed.expires_on
