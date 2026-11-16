"""LV-444: «¿Puedo volar?» y los vencimientos con los tipos de evaluación nuevos.

La regla (ver `readiness._check_evaluations`): sin intentos no se juzga nada; con
sólo `legacy` rige lo de siempre; **desde el primer intento de las evaluaciones del
Manual** rige el conjunto completo — examen general (o convalidación REG-018),
limitaciones y emergencias del modelo de **esta** aeronave, y cuestionario anual
vigente o instrucción inicial de menos de 12 meses. Cada pata se prueba variando
**una a la vez** (la lección de UX-27: un test que sólo ejercita la pata fácil
comparte el punto ciego del código).
"""

from datetime import date, datetime, timedelta, timezone as dt_timezone

import pytest
from django.contrib.contenttypes.models import ContentType
from django.utils.translation import gettext

from apps.compliance.expirations import upcoming_expirations
from apps.compliance.models import Document, DocumentType
from apps.core.testing import login_as
from apps.operations.readiness import _check_operator, can_fly
from apps.registry.assessment_testing import make_family
from apps.registry.models import Aircraft, CostCenter, KnowledgeAssessment, Operator

TODAY = date(2026, 9, 7)
CUTOFF = TODAY + timedelta(days=30)

GENERAL = gettext("General exam")
LIMITATIONS = gettext("Limitations and emergencies")
ANNUAL = gettext("Annual questionnaire")


@pytest.fixture
def world(db):
    centre = CostCenter.objects.create(code="CC738", name="MLP")
    operator = Operator.objects.create(
        employee_id="E1",
        full_name="Operator A",
        cost_center=centre,
        credential_expiry=TODAY + timedelta(days=200),
    )
    mavic = make_family()
    matrice = make_family("matrice", "Matrice series", "matrice")
    aircraft = Aircraft.objects.create(
        registration="RPA-1", model="Mavic 3 Enterprise", cost_center=centre
    )
    return {
        "operator": operator,
        "aircraft": aircraft,
        "mavic": mavic,
        "matrice": matrice,
        "centre": centre,
    }


def _attempt(
    operator,
    kind,
    *,
    passed=True,
    family=None,
    taken_on=TODAY - timedelta(days=30),
    expires_in=None,
):
    row = KnowledgeAssessment.objects.create(
        operator=operator,
        kind=kind,
        aircraft_family=family,
        question_count=20,
        correct_count=20 if passed else 5,
        score_percent=100 if passed else 25,
        passed=passed,
        expires_on=None if expires_in is None else TODAY + timedelta(days=expires_in),
    )
    KnowledgeAssessment.objects.filter(pk=row.pk).update(
        taken_at=datetime.combine(
            taken_on, datetime.min.time().replace(hour=12)
        ).replace(tzinfo=dt_timezone.utc)
    )
    return row


def _labels(items):
    return {str(item.label) for item in items}


def _check(world):
    return _check_operator(world["operator"], TODAY, world["aircraft"])


def _complete(world):
    """General, limitaciones del modelo y anual vigente: la terna que habilita."""
    operator = world["operator"]
    _attempt(operator, "general")
    _attempt(operator, "limitations", family=world["mavic"])
    _attempt(operator, "annual", family=world["mavic"], expires_in=200)


class TestTheRule:
    def test_no_attempt_at_all_stays_silent(self, world):
        assert _check(world).passed
        assert not _check(world).warnings

    def test_the_full_set_enables(self, world):
        _complete(world)

        check = _check(world)

        assert check.passed
        assert not check.warnings

    def test_legacy_alone_keeps_the_old_rule(self, world):
        _attempt(world["operator"], "legacy", expires_in=200)

        assert _check(world).passed

    def test_a_legacy_pass_alone_does_not_start_demanding_the_new_exams(self, world):
        # El día del despliegue nadie cae a «no puede volar» por los tipos nuevos.
        _attempt(world["operator"], "legacy", expires_in=200)

        assert GENERAL not in _labels(_check(world).blockers)
        assert LIMITATIONS not in _labels(_check(world).blockers)

    def test_an_expired_legacy_alone_blocks_as_before(self, world):
        _attempt(world["operator"], "legacy", expires_in=-1)

        assert not _check(world).passed

    def test_a_failed_legacy_alone_blocks_as_before(self, world):
        _attempt(world["operator"], "legacy", passed=False, expires_in=300)

        assert not _check(world).passed


class TestEachLegVariedAlone:
    def test_without_the_general_exam_it_blocks(self, world):
        operator = world["operator"]
        _attempt(operator, "limitations", family=world["mavic"])
        _attempt(operator, "annual", family=world["mavic"], expires_in=200)

        assert _labels(_check(world).blockers) == {GENERAL}

    def test_a_failed_general_exam_blocks_with_the_failed_message(self, world):
        operator = world["operator"]
        _complete(world)
        KnowledgeAssessment.objects.filter(kind="general").delete()
        _attempt(operator, "general", passed=False)

        assert GENERAL in _labels(_check(world).blockers)

    def test_a_convalidation_document_stands_for_the_general_exam(self, world):
        operator = world["operator"]
        _attempt(operator, "limitations", family=world["mavic"])
        _attempt(operator, "annual", family=world["mavic"], expires_in=200)
        doc_type = DocumentType.objects.create(
            code="convalidation", name="Convalidación", reference_code="REG-018"
        )
        Document.objects.create(
            doc_type=doc_type,
            title="Convalidación DJI",
            content_type=ContentType.objects.get_for_model(Operator),
            object_id=operator.pk,
        )

        assert _check(world).passed

    def test_a_document_of_another_type_is_not_a_convalidation(self, world):
        operator = world["operator"]
        _attempt(operator, "limitations", family=world["mavic"])
        _attempt(operator, "annual", family=world["mavic"], expires_in=200)
        doc_type = DocumentType.objects.create(code="other", name="Otro")
        Document.objects.create(
            doc_type=doc_type,
            title="Otro",
            content_type=ContentType.objects.get_for_model(Operator),
            object_id=operator.pk,
        )

        assert GENERAL in _labels(_check(world).blockers)

    def test_without_limitations_for_the_model_it_blocks(self, world):
        operator = world["operator"]
        _attempt(operator, "general")
        _attempt(operator, "annual", family=world["mavic"], expires_in=200)

        assert _labels(_check(world).blockers) == {LIMITATIONS}

    def test_limitations_of_another_model_do_not_cover_this_aircraft(self, world):
        operator = world["operator"]
        _attempt(operator, "general")
        _attempt(operator, "limitations", family=world["matrice"])
        _attempt(operator, "annual", family=world["mavic"], expires_in=200)

        assert _labels(_check(world).blockers) == {LIMITATIONS}

    def test_failed_limitations_for_the_model_block(self, world):
        operator = world["operator"]
        _complete(world)
        KnowledgeAssessment.objects.filter(kind="limitations").delete()
        _attempt(operator, "limitations", passed=False, family=world["mavic"])

        assert LIMITATIONS in _labels(_check(world).blockers)

    def test_an_aircraft_no_catalog_model_covers_warns_and_does_not_block(self, world):
        _complete(world)
        stranger = Aircraft.objects.create(
            registration="RPA-2", model="Unknown X1", cost_center=world["centre"]
        )

        check = _check_operator(world["operator"], TODAY, stranger)

        assert check.passed
        assert LIMITATIONS in _labels(check.warnings)

    def test_without_the_aircraft_the_limitations_are_not_judged(self, world):
        operator = world["operator"]
        _attempt(operator, "general")
        _attempt(operator, "annual", family=world["mavic"], expires_in=200)

        assert _check_operator(operator, TODAY).passed

    def test_without_annual_and_with_an_old_general_it_blocks(self, world):
        operator = world["operator"]
        _attempt(operator, "general", taken_on=TODAY - timedelta(days=400))
        _attempt(operator, "limitations", family=world["mavic"])

        assert _labels(_check(world).blockers) == {ANNUAL}

    def test_a_recent_general_exam_is_the_initial_instruction(self, world):
        operator = world["operator"]
        _attempt(operator, "general", taken_on=TODAY - timedelta(days=100))
        _attempt(operator, "limitations", family=world["mavic"])

        assert _check(world).passed

    def test_the_initial_instruction_lapses_at_twelve_months(self, world):
        operator = world["operator"]
        _attempt(operator, "limitations", family=world["mavic"])
        # 12 meses justos desde 2025-09-07 es hoy: vigente (avisa, no bloquea).
        _attempt(operator, "general", taken_on=date(2025, 9, 7))
        assert _check(world).passed

        KnowledgeAssessment.objects.filter(kind="general").delete()
        _attempt(operator, "general", taken_on=date(2025, 9, 6))
        assert ANNUAL in _labels(_check(world).blockers)

    def test_an_expired_annual_blocks_when_the_initial_instruction_is_old(self, world):
        operator = world["operator"]
        _attempt(operator, "general", taken_on=TODAY - timedelta(days=500))
        _attempt(operator, "limitations", family=world["mavic"])
        _attempt(operator, "annual", family=world["mavic"], expires_in=-1)

        assert ANNUAL in _labels(_check(world).blockers)

    def test_a_failed_annual_does_not_hide_behind_old_papers(self, world):
        operator = world["operator"]
        _attempt(operator, "general", taken_on=TODAY - timedelta(days=500))
        _attempt(operator, "limitations", family=world["mavic"])
        _attempt(
            operator, "annual", passed=False, family=world["mavic"], expires_in=300
        )

        assert ANNUAL in _labels(_check(world).blockers)

    def test_a_valid_legacy_counts_as_the_annual_until_it_expires(self, world):
        operator = world["operator"]
        _attempt(operator, "general", taken_on=TODAY - timedelta(days=500))
        _attempt(operator, "limitations", family=world["mavic"])
        legacy = _attempt(operator, "legacy", expires_in=100)

        assert _check(world).passed

        KnowledgeAssessment.objects.filter(pk=legacy.pk).update(
            expires_on=TODAY - timedelta(days=1)
        )
        assert ANNUAL in _labels(_check(world).blockers)

    def test_the_general_exam_and_limitations_never_expire_by_calendar(self, world):
        operator = world["operator"]
        _attempt(operator, "general", taken_on=TODAY - timedelta(days=3000))
        _attempt(
            operator,
            "limitations",
            family=world["mavic"],
            taken_on=TODAY - timedelta(days=3000),
        )
        _attempt(operator, "annual", family=world["mavic"], expires_in=200)

        assert _check(world).passed

    def test_an_expiring_annual_warns(self, world):
        operator = world["operator"]
        _attempt(operator, "general", taken_on=TODAY - timedelta(days=500))
        _attempt(operator, "limitations", family=world["mavic"])
        _attempt(operator, "annual", family=world["mavic"], expires_in=10)

        check = _check(world)

        assert check.passed
        assert ANNUAL in _labels(check.warnings)

    def test_the_screen_verdict_uses_the_aircraft_of_the_triple(self, world):
        operator = world["operator"]
        _attempt(operator, "general")
        _attempt(operator, "limitations", family=world["matrice"])
        _attempt(operator, "annual", family=world["matrice"], expires_in=200)

        operator_check = can_fly(
            world["aircraft"], operator, world["centre"], TODAY
        ).checks[1]

        assert LIMITATIONS in _labels(operator_check.blockers)


class TestExpirationList:
    def _listed(self, operator):
        user = login_as("view_knowledgeassessment", "view_operator").user
        return [
            row
            for row in upcoming_expirations(TODAY, CUTOFF, None, user)
            if row["label"] == str(operator)
        ]

    def test_general_and_limitations_never_appear(self, world):
        operator = world["operator"]
        _attempt(operator, "general", expires_in=10)  # aunque algo les sellara fecha
        _attempt(operator, "limitations", family=world["mavic"], expires_in=10)

        assert self._listed(operator) == []

    def test_an_annual_without_an_expiry_does_not_appear(self, world):
        _attempt(world["operator"], "annual", family=world["mavic"])

        assert self._listed(world["operator"]) == []

    def test_the_annual_questionnaire_is_listed(self, world):
        operator = world["operator"]
        annual = _attempt(operator, "annual", family=world["mavic"], expires_in=10)

        rows = self._listed(operator)

        assert [row["date"] for row in rows] == [annual.expires_on]

    def test_a_legacy_pass_is_still_listed(self, world):
        operator = world["operator"]
        legacy = _attempt(operator, "legacy", expires_in=10)

        assert [row["date"] for row in self._listed(operator)] == [legacy.expires_on]

    def test_a_newer_annual_outside_the_window_hides_the_older_one(self, world):
        operator = world["operator"]
        _attempt(
            operator, "legacy", taken_on=TODAY - timedelta(days=300), expires_in=10
        )
        _attempt(operator, "annual", family=world["mavic"], expires_in=300)

        assert self._listed(operator) == []
