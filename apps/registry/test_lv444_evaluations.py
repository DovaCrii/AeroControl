"""LV-444: las evaluaciones del Manual Act. 19 (REG-019) y su banco fuera del repo.

Tres tipos (examen general 75 %; limitaciones y emergencias 100 % por modelo de RPA;
cuestionario anual con parte A 75 % y parte B 100 %), el banco en la base cargado
con `load_assessment_bank`, y los intentos anteriores (`legacy`) que siguen
leyéndose. **Todas las preguntas de estos tests son inventadas**: el repo es
público y el banco real vive fuera de él.
"""

import importlib
import json
from datetime import timedelta

import pytest
from django.apps import apps as django_apps
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from apps.core.models import OperationalTenant
from apps.core.testing import login_as
from apps.registry import assessments
from apps.registry.assessment_testing import (
    correct_answers,
    make_bank,
    make_family,
    make_question,
)
from apps.registry.models import AssessmentQuestion, KnowledgeAssessment, Operator

TODAY = timezone.localdate()


def _operator(user=None, **kwargs):
    return Operator.objects.create(
        employee_id=kwargs.pop("employee_id", "E-1"),
        full_name=kwargs.pop("full_name", "Operator A"),
        user=user,
        **kwargs,
    )


def _client(*codenames):
    client = login_as("add_knowledgeassessment", *codenames)
    return client, _operator(user=client.user)


# ── Umbrales por parte ───────────────────────────────────────────────────────


class TestThresholds:
    @pytest.mark.parametrize(
        ("correct", "total", "threshold", "passes"),
        [
            (74, 100, 75, False),  # 74 % reprueba…
            (75, 100, 75, True),  # …75 % aprueba: el borde
            (14, 20, 75, False),  # 70 %
            (15, 20, 75, True),  # 75 % exacto
            (99, 100, 100, False),  # 99 % reprueba la parte de 100 %
            (100, 100, 100, True),
            (17, 18, 100, False),  # una sola falla en limitaciones reprueba
            (18, 18, 100, True),
        ],
    )
    def test_the_edge_of_each_threshold(self, correct, total, threshold, passes):
        assert assessments.score_part(correct, total, threshold)["passed"] is passes

    def test_the_comparison_is_not_made_on_the_rounded_percent(self):
        # 7496/10000 = 74,96 %: redondeado a una cifra daría 75,0 y aprobaría.
        score = assessments.score_part(7496, 10000, 75)

        assert score["percent"] == 75.0
        assert score["passed"] is False

    def test_a_part_with_no_questions_never_passes(self):
        assert assessments.score_part(0, 0, 75)["passed"] is False

    def test_the_constants_are_the_manuals(self):
        assert assessments.GENERAL_THRESHOLD == 75
        assert assessments.LIMITATIONS_THRESHOLD == 100
        assert assessments.ANNUAL_A_THRESHOLD == 75
        assert assessments.ANNUAL_B_THRESHOLD == 100
        assert assessments.ANNUAL_VALID_MONTHS == 12


@pytest.mark.django_db
class TestGradingAnAttempt:
    def _grade(self, kind, family, wrong_in=()):
        """Corrige un sorteo dejando mal `wrong_in` = {parte: cuántas}."""
        drawn = assessments.draw_questions(kind, family, seed=3)
        ids_by_part = {p: [q["id"] for q in qs] for p, qs in drawn.items()}
        by_id = {
            str(pk): question
            for pk, question in AssessmentQuestion.objects.in_bulk(
                [i for ids in ids_by_part.values() for i in ids]
            ).items()
        }
        given = {}
        for part, ids in ids_by_part.items():
            for position, qid in enumerate(ids):
                broken = position < dict(wrong_in).get(part, 0)
                given[qid] = "z" if broken else by_id[qid].answer
        return assessments.grade_attempt(kind, ids_by_part, given)

    def test_the_annual_needs_both_parts(self):
        family = make_family()
        make_bank(family)

        _rows, scores, passed, _c, _t = self._grade("annual", family)
        assert passed is True
        assert scores["A"]["threshold"] == 75
        assert scores["B"]["threshold"] == 100

        # Parte A perfecta, una falla en la B: reprueba aunque el total sea 96 %.
        _rows, scores, passed, _c, _t = self._grade("annual", family, {"B": 1})
        assert scores["A"]["passed"] is True
        assert scores["B"]["passed"] is False
        assert passed is False

        # Parte B perfecta, A en 70 % (3 de 10 mal): reprueba por la A.
        _rows, scores, passed, _c, _t = self._grade("annual", family, {"A": 3})
        assert scores["A"]["passed"] is False
        assert passed is False

        # A en 80 % (2 de 10 mal) y B perfecta: aprueba.
        _rows, _scores, passed, _c, _t = self._grade("annual", family, {"A": 2})
        assert passed is True

    def test_the_general_exam_passes_at_75_and_fails_at_70(self):
        make_bank()
        # 20 preguntas: 5 mal = 75 % (aprueba); 6 mal = 70 % (reprueba).
        assert self._grade("general", None, {"A": 5})[2] is True
        assert self._grade("general", None, {"A": 6})[2] is False

    def test_limitations_need_every_answer(self):
        family = make_family()
        make_bank(family)

        assert self._grade("limitations", family)[2] is True
        assert self._grade("limitations", family, {"A": 1})[2] is False

    def test_each_row_keeps_the_question_its_part_and_both_answers(self):
        make_bank()

        rows = self._grade("general", None, {"A": 1})[0]

        row = rows[0]
        assert {"id", "part", "text", "options", "given", "answer", "correct"} <= set(
            row
        )
        assert row["part"] == "A"
        assert row["correct"] is False

    def test_a_question_no_longer_in_the_bank_is_not_counted_as_correct(self):
        make_bank()
        ids = {"A": ["00000000-0000-0000-0000-000000000000", "not-a-uuid"]}

        rows, scores, passed, correct, _total = assessments.grade_attempt(
            "general", ids, {}
        )

        assert correct == 0
        assert rows[0]["correct"] is False
        assert passed is False
        assert scores["A"]["total"] == 2


# ── El sorteo ────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestTheDraw:
    def test_each_type_draws_what_the_manual_asks(self):
        family = make_family()
        make_bank(family)

        general = assessments.draw_questions("general")
        limitations = assessments.draw_questions("limitations", family)
        annual = assessments.draw_questions("annual", family)

        assert len(general["A"]) == 20
        assert len(limitations["A"]) == 15 + 3
        assert len(annual["A"]) == 10
        assert len(annual["B"]) == 15 + 3

    def test_the_equipment_questions_are_of_the_chosen_model_only(self):
        mavic = make_family()
        matrice = make_family("matrice", "Matrice series", "matrice")
        make_bank(mavic)
        for number in range(1, 5):
            make_question("limitations", number, family=matrice)
        own = set(
            AssessmentQuestion.objects.filter(aircraft_family=mavic).values_list(
                "pk", flat=True
            )
        )
        theirs = set(
            AssessmentQuestion.objects.filter(aircraft_family=matrice).values_list(
                "pk", flat=True
            )
        )

        ids = {q["id"] for q in assessments.draw_questions("limitations", mavic)["A"]}

        assert len(ids & {str(i) for i in own}) == 3
        assert not ids & {str(i) for i in theirs}

    def test_the_correct_answer_never_leaves_the_server(self):
        make_bank()

        for question in assessments.draw_questions("general", seed=1)["A"]:
            assert "answer" not in question

    def test_a_short_bank_draws_what_there_is(self):
        make_bank(general=7)

        assert len(assessments.draw_questions("general")["A"]) == 7
        assert assessments.planned_counts("general") == {"A": 7}

    def test_an_empty_bank_is_not_available(self):
        assert not assessments.bank_is_available("general")
        assert not assessments.bank_is_available("limitations", make_family())

    def test_limitations_need_a_common_question_to_be_available(self):
        family = make_family()
        make_question("limitations", 1, family=family)  # sólo del equipo

        assert not assessments.bank_is_available("limitations", family)

    def test_a_seed_makes_the_draw_repeatable(self):
        make_bank()

        first = [q["id"] for q in assessments.draw_questions("general", seed=7)["A"]]
        second = [q["id"] for q in assessments.draw_questions("general", seed=7)["A"]]
        other = [q["id"] for q in assessments.draw_questions("general", seed=8)["A"]]

        assert first == second
        assert first != other


# ── Modelo: familia obligatoria, restricciones ───────────────────────────────


@pytest.mark.django_db
class TestModelRules:
    def _attempt(self, kind, family=None):
        return KnowledgeAssessment(
            operator=Operator.objects.get_or_create(
                employee_id="E-1", defaults={"full_name": "Operator A"}
            )[0],
            kind=kind,
            aircraft_family=family,
            question_count=1,
            correct_count=1,
            score_percent=100,
            passed=True,
        )

    @pytest.mark.parametrize("kind", ["limitations", "annual"])
    def test_a_per_model_assessment_without_a_model_is_rejected_by_clean(self, kind):
        with pytest.raises(ValidationError) as caught:
            self._attempt(kind).full_clean()

        assert "aircraft_family" in caught.value.message_dict

    @pytest.mark.parametrize("kind", ["limitations", "annual"])
    def test_and_by_the_database_constraint(self, kind):
        with pytest.raises(IntegrityError), transaction.atomic():
            self._attempt(kind).save()

    def test_general_and_legacy_do_not_need_a_model(self):
        for kind in ("general", "legacy"):
            self._attempt(kind).full_clean(exclude=["answers"])

    def test_the_expiry_may_be_empty_and_then_it_is_not_overdue(self):
        attempt = self._attempt("general")
        attempt.expires_on = None
        attempt.save()

        assert attempt.is_expired is False

    def test_a_bank_number_is_unique_per_kind_and_model(self):
        family = make_family()
        make_question("limitations", 1)
        make_question("limitations", 1, family=family)

        with pytest.raises(IntegrityError), transaction.atomic():
            make_question("limitations", 1)
        with pytest.raises(IntegrityError), transaction.atomic():
            make_question("limitations", 1, family=family)

    def test_only_limitations_have_questions_by_model(self):
        family = make_family()

        with pytest.raises(IntegrityError), transaction.atomic():
            make_question("general", 1, family=family)

    def test_a_question_whose_answer_is_not_an_option_is_invalid(self):
        question = AssessmentQuestion(
            kind="general",
            number=1,
            text="x",
            options=[{"key": "a", "text": "A"}, {"key": "b", "text": "B"}],
            answer="z",
        )

        with pytest.raises(ValidationError):
            question.full_clean()

    def test_only_the_annual_questionnaire_expires(self):
        assert assessments.validity_for("general", TODAY) is None
        assert assessments.validity_for("limitations", TODAY) is None
        assert assessments.validity_for("annual", TODAY) == assessments.valid_until(
            TODAY
        )


# ── load_assessment_bank ─────────────────────────────────────────────────────


def _write(tmp_path, questions, name="bank.json"):
    path = tmp_path / name
    path.write_text(json.dumps({"questions": questions}), encoding="utf-8")
    return str(path)


def _question(number=1, kind="general", **extra):
    return {
        "kind": kind,
        "number": number,
        "text": f"Invented   question\n {number}",
        "options": [{"key": "A", "text": "One"}, {"key": "B", "text": "Two"}],
        "answer": "B",
        **extra,
    }


@pytest.mark.django_db
class TestLoadAssessmentBank:
    def test_the_documented_example_loads(self, tmp_path, settings):
        # El ejemplo de docs/ es el contrato del formato: si deja de cargar, la
        # guía miente. Se copia fuera del repo: el comando no lee desde docs/.
        import shutil

        copy = tmp_path / "example.json"
        shutil.copy(
            settings.BASE_DIR / "docs/examples/assessment_bank_example.json", copy
        )
        call_command("load_assessment_bank", str(copy))
        kinds = set(AssessmentQuestion.objects.values_list("kind", flat=True))
        assert kinds == {"general", "limitations", "annual"}
        assert AssessmentQuestion.objects.count() == 3

    def test_the_happy_path_normalises_and_stores(self, tmp_path):
        call_command("load_assessment_bank", _write(tmp_path, [_question()]))

        row = AssessmentQuestion.objects.get()
        assert row.text == "Invented question 1"
        assert row.answer == "b"
        assert [o["key"] for o in row.options] == ["a", "b"]

    def test_running_it_twice_does_not_duplicate_and_updates(self, tmp_path):
        call_command("load_assessment_bank", _write(tmp_path, [_question()]))
        changed = _question(text="Changed text")
        call_command("load_assessment_bank", _write(tmp_path, [changed]))

        assert AssessmentQuestion.objects.count() == 1
        assert AssessmentQuestion.objects.get().text == "Changed text"

    def test_a_family_question_resolves_the_catalog_code(self, tmp_path):
        family = make_family()

        call_command(
            "load_assessment_bank",
            _write(tmp_path, [_question(kind="limitations", family="mavic")]),
        )

        assert AssessmentQuestion.objects.get().aircraft_family == family

    def test_dry_run_validates_and_writes_nothing(self, tmp_path, capsys):
        call_command(
            "load_assessment_bank", _write(tmp_path, [_question()]), "--dry-run"
        )

        assert not AssessmentQuestion.objects.exists()
        assert "dry-run" in capsys.readouterr().out

    @pytest.mark.parametrize(
        "broken",
        [
            {"kind": "exam"},  # tipo desconocido
            {"number": 0},
            {"text": "  "},
            {"options": [{"key": "a", "text": "only one"}]},
            {"answer": "z"},
            {"kind": "limitations", "family": "no-such-code"},
            {"family": "mavic"},  # family en un tipo que no es limitaciones
        ],
    )
    def test_an_invalid_question_loads_nothing_at_all(self, tmp_path, broken):
        make_family()
        questions = [_question(1), {**_question(2), **broken}]

        with pytest.raises(CommandError) as caught:
            call_command("load_assessment_bank", _write(tmp_path, questions))

        assert "question #2" in str(caught.value)
        assert not AssessmentQuestion.objects.exists()

    def test_a_duplicate_in_the_file_is_an_error(self, tmp_path):
        with pytest.raises(CommandError, match="duplicate"):
            call_command(
                "load_assessment_bank", _write(tmp_path, [_question(1), _question(1)])
            )

    def test_not_json_and_missing_file_are_command_errors(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")

        with pytest.raises(CommandError, match="not valid JSON"):
            call_command("load_assessment_bank", str(bad))
        with pytest.raises(CommandError, match="Cannot read"):
            call_command("load_assessment_bank", str(tmp_path / "missing.json"))

    @pytest.mark.parametrize(
        "relative", ["apps/registry/bank.json", "docs/bank.json", "bank.json"]
    )
    def test_a_file_inside_the_repo_but_not_in_private_is_refused(
        self, settings, relative
    ):
        inside = settings.BASE_DIR / relative

        with pytest.raises(CommandError, match="private/"):
            call_command("load_assessment_bank", str(inside))

    def test_private_is_accepted(self, settings):
        private = settings.BASE_DIR / "private" / "_test_bank_lv444.json"
        private.parent.mkdir(exist_ok=True)
        private.write_text(json.dumps({"questions": [_question()]}), encoding="utf-8")
        try:
            call_command("load_assessment_bank", str(private))
        finally:
            private.unlink()

        assert AssessmentQuestion.objects.count() == 1

    def test_replace_with_a_one_model_file_archives_only_that_model(self, tmp_path):
        mavic = make_family()
        matrice = make_family("matrice", "Matrice series", "matrice")
        make_question("limitations", 1)  # común
        make_question("limitations", 1, family=mavic)
        make_question("limitations", 2, family=mavic)
        make_question("limitations", 1, family=matrice)
        make_question("general", 1)

        call_command(
            "load_assessment_bank",
            _write(tmp_path, [_question(1, kind="limitations", family="mavic")]),
            "--replace",
        )

        active = {
            (q.kind, q.aircraft_family and q.aircraft_family.code, q.number)
            for q in AssessmentQuestion.objects.filter(is_active=True)
        }
        assert active == {
            ("limitations", None, 1),
            ("limitations", "mavic", 1),
            ("limitations", "matrice", 1),
            ("general", None, 1),
        }
        assert not AssessmentQuestion.objects.get(
            aircraft_family=mavic, number=2
        ).is_active

    def test_replace_archives_what_is_no_longer_listed_and_never_deletes(
        self, tmp_path
    ):
        call_command(
            "load_assessment_bank",
            _write(tmp_path, [_question(1), _question(2)]),
        )
        make_question("annual", 1)  # otro tipo: --replace no lo toca

        call_command(
            "load_assessment_bank", _write(tmp_path, [_question(1)]), "--replace"
        )

        assert AssessmentQuestion.objects.count() == 3
        assert (
            AssessmentQuestion.objects.get(kind="general", number=2).is_active is False
        )
        assert AssessmentQuestion.objects.get(kind="general", number=1).is_active
        assert AssessmentQuestion.objects.get(kind="annual", number=1).is_active

    def test_reloading_an_archived_question_reactivates_it(self, tmp_path):
        call_command(
            "load_assessment_bank", _write(tmp_path, [_question(1), _question(2)])
        )
        call_command(
            "load_assessment_bank", _write(tmp_path, [_question(1)]), "--replace"
        )

        call_command(
            "load_assessment_bank", _write(tmp_path, [_question(1), _question(2)])
        )

        assert AssessmentQuestion.objects.filter(is_active=True).count() == 2

    def test_an_archived_question_is_not_drawn(self):
        make_bank(general=22)
        AssessmentQuestion.objects.filter(kind="general", number__gt=20).update(
            is_active=False
        )

        ids = {q["id"] for q in assessments.draw_questions("general")["A"]}

        archived = AssessmentQuestion.objects.filter(is_active=False)
        assert not ids & {str(pk) for pk in archived.values_list("pk", flat=True)}


def test_no_question_bank_file_lives_in_the_versioned_code(settings):
    """El banco publicaba preguntas con su clave en un repo público (LV-444)."""
    offenders = [
        str(path.relative_to(settings.BASE_DIR))
        for path in (settings.BASE_DIR / "apps").rglob("*.json")
        if "bank" in path.name.lower() or "question" in path.name.lower()
    ]

    assert offenders == []


# ── Migración de datos ───────────────────────────────────────────────────────


@pytest.mark.django_db
class TestLegacyAttemptsMigration:
    def _run(self):
        module = importlib.import_module(
            "apps.registry.migrations.0045_classify_legacy_assessments"
        )
        module.classify_legacy_attempts(django_apps, None)

    def test_an_old_attempt_is_read_as_legacy_with_its_own_threshold(self):
        old = KnowledgeAssessment.objects.create(
            operator=_operator(),
            question_count=25,
            correct_count=20,
            score_percent=80,
            passed=True,
            expires_on=TODAY + timedelta(days=200),
            answers=[{"id": 1}],
        )

        self._run()
        old.refresh_from_db()

        assert old.kind == "legacy"
        assert old.part_scores["A"]["threshold"] == 80
        assert old.part_scores["A"]["correct"] == 20
        assert old.part_scores["A"]["total"] == 25
        # lo guardado no se toca
        assert old.passed is True
        assert old.answers == [{"id": 1}]
        assert old.expires_on == TODAY + timedelta(days=200)

    def test_it_does_not_overwrite_an_attempt_that_already_has_parts(self):
        family = make_family()
        new = KnowledgeAssessment.objects.create(
            operator=_operator(),
            kind="annual",
            aircraft_family=family,
            question_count=28,
            correct_count=28,
            score_percent=100,
            passed=True,
            part_scores={"A": {"threshold": 75}, "B": {"threshold": 100}},
        )

        self._run()
        new.refresh_from_db()

        assert new.kind == "annual"
        assert set(new.part_scores) == {"A", "B"}

    def test_a_legacy_attempt_still_reviews_with_its_80_percent(self):
        old = KnowledgeAssessment.objects.create(
            operator=_operator(),
            question_count=25,
            correct_count=20,
            score_percent=80,
            passed=True,
            expires_on=TODAY + timedelta(days=200),
        )
        self._run()
        client = login_as("view_knowledgeassessment", "view_operator")

        response = client.get(reverse("assessment-detail", args=[old.pk]))

        assert response.status_code == 200
        assert response.context["pass_percent"] == assessments.LEGACY_PASS_PERCENT


# ── Vistas ───────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestTakingEachKind:
    def test_without_a_bank_the_screen_says_so_instead_of_failing(self):
        client, _op = _client()

        chooser = client.get(reverse("assessment-take"))
        general = client.get(
            reverse("assessment-take"), {"kind": "general"}, follow=True
        )

        assert chooser.status_code == 200
        assert chooser.context["bank_loaded"] is False
        assert b"alert-warning" in chooser.content
        assert general.status_code == 200
        message = str([m for m in general.context["messages"]][0])
        assert message == str(_not_loaded())

    def test_an_unknown_kind_goes_back_to_the_chooser(self):
        client, _op = _client()

        response = client.get(reverse("assessment-take"), {"kind": "bogus"})

        assert response.status_code == 302
        assert not KnowledgeAssessment.objects.exists()

    def test_limitations_without_a_model_are_not_offered(self):
        make_bank()
        client, _op = _client()

        response = client.get(reverse("assessment-take"), {"kind": "limitations"})

        assert response.status_code == 302
        assert "kind" not in response["Location"]

    def test_a_general_exam_passing_leaves_no_expiry(self):
        make_bank()
        client, operator = _client()
        client.get(reverse("assessment-take"), {"kind": "general"})
        payload = correct_answers(client.session["knowledge_assessment_questions"])

        response = client.post(reverse("assessment-take"), payload)
        attempt = KnowledgeAssessment.objects.get()

        assert response.status_code == 302
        assert attempt.kind == "general"
        assert attempt.operator == operator
        assert attempt.passed is True
        assert attempt.expires_on is None
        assert attempt.part_scores["A"]["threshold"] == 75
        assert attempt.question_count == 20

    @pytest.mark.parametrize(("wrong", "expected"), [(6, False), (5, True)])
    def test_the_view_fails_at_14_of_20_and_passes_at_15(self, wrong, expected):
        make_bank()
        client, _op = _client()
        client.get(reverse("assessment-take"), {"kind": "general"})
        payload = correct_answers(client.session["knowledge_assessment_questions"])
        for key in list(payload)[:wrong]:
            payload[key] = "z"

        client.post(reverse("assessment-take"), payload)

        assert KnowledgeAssessment.objects.get().passed is expected

    def test_limitations_are_filed_for_the_chosen_model(self):
        family = make_family()
        make_bank(family)
        client, _op = _client()
        client.get(
            reverse("assessment-take"), {"kind": "limitations", "family": family.pk}
        )
        payload = correct_answers(client.session["knowledge_assessment_questions"])

        client.post(reverse("assessment-take"), payload)
        attempt = KnowledgeAssessment.objects.get()

        assert attempt.kind == "limitations"
        assert attempt.aircraft_family == family
        assert attempt.passed is True
        assert attempt.expires_on is None

    def test_one_wrong_answer_in_limitations_is_insufficient(self):
        family = make_family()
        make_bank(family)
        client, _op = _client()
        client.get(
            reverse("assessment-take"), {"kind": "limitations", "family": family.pk}
        )
        payload = correct_answers(client.session["knowledge_assessment_questions"])
        payload[next(iter(payload))] = "z"

        client.post(reverse("assessment-take"), payload)

        assert KnowledgeAssessment.objects.get().passed is False

    def test_the_annual_questionnaire_has_two_parts_and_a_year_of_validity(self):
        family = make_family()
        make_bank(family)
        client, _op = _client()
        response = client.get(
            reverse("assessment-take"), {"kind": "annual", "family": family.pk}
        )
        assert [p["part"] for p in response.context["parts"]] == ["A", "B"]
        payload = correct_answers(client.session["knowledge_assessment_questions"])

        client.post(reverse("assessment-take"), payload)
        attempt = KnowledgeAssessment.objects.get()

        assert attempt.kind == "annual"
        assert attempt.passed is True
        assert attempt.expires_on == assessments.valid_until(TODAY)
        assert set(attempt.part_scores) == {"A", "B"}

    def test_the_page_never_carries_the_answers_or_a_checked_option(self):
        make_bank()
        client, _op = _client()

        content = client.get(
            reverse("assessment-take"), {"kind": "general"}
        ).content.decode()

        assert "checked" not in content

    def test_posting_without_a_draw_starts_over(self):
        client, _op = _client()

        response = client.post(reverse("assessment-take"), {})

        assert response.status_code == 302
        assert not KnowledgeAssessment.objects.exists()

    def test_the_session_is_cleared_after_submitting(self):
        make_bank()
        client, _op = _client()
        client.get(reverse("assessment-take"), {"kind": "general"})

        client.post(reverse("assessment-take"), {})

        assert "knowledge_assessment_questions" not in client.session


@pytest.mark.django_db
class TestPermissions:
    def test_taking_it_is_403_without_add_permission(self):
        client = login_as("view_knowledgeassessment")
        _operator(user=client.user)

        assert client.get(reverse("assessment-take")).status_code == 403
        assert client.post(reverse("assessment-take"), {}).status_code == 403

    def test_the_review_is_403_without_view_permission(self):
        attempt = KnowledgeAssessment.objects.create(
            operator=_operator(),
            question_count=1,
            correct_count=1,
            score_percent=100,
            passed=True,
        )

        response = login_as().get(reverse("assessment-detail", args=[attempt.pk]))

        assert response.status_code == 403

    def test_the_bank_list_is_403_without_its_permission(self):
        assert (
            login_as("view_knowledgeassessment")
            .get(reverse("assessment-bank"))
            .status_code
            == 403
        )

    def test_the_bank_list_hides_the_key_without_the_answers_permission(self):
        make_question("general", 1, text="Invented marker question", answer="b")
        reader = login_as("view_assessmentquestion")
        keyholder = login_as("view_assessmentquestion", "view_assessment_answers")

        plain = reader.get(reverse("assessment-bank"))
        keyed = keyholder.get(reverse("assessment-bank"))

        assert plain.status_code == 200
        assert b"Invented marker question" in plain.content
        assert b"badge bg-success" not in plain.content
        assert b"badge bg-success" in keyed.content

    def test_an_empty_bank_list_says_it_is_not_loaded(self):
        response = login_as("view_assessmentquestion").get(reverse("assessment-bank"))

        assert response.status_code == 200
        assert b"alert-warning" in response.content

    def test_the_review_does_not_cross_tenants(self):
        mine = OperationalTenant.objects.create(name="Mine", slug="mine")
        theirs = OperationalTenant.objects.create(name="Theirs", slug="theirs")
        other = _operator(employee_id="E-9", full_name="Operator B", tenant=theirs)
        attempt = KnowledgeAssessment.objects.create(
            operator=other,
            question_count=1,
            correct_count=1,
            score_percent=100,
            passed=True,
        )
        client = login_as("view_knowledgeassessment", "view_operator", member_of=mine)

        response = client.get(reverse("assessment-detail", args=[attempt.pk]))

        assert response.status_code == 404

    def test_compliance_role_can_read_the_bank(self):
        from apps.core.management.commands.bootstrap_roles import ROLE_PERMISSIONS

        assert "view_assessmentquestion" in ROLE_PERMISSIONS["Compliance"]
        assert "view_assessmentquestion" not in ROLE_PERMISSIONS["Operations"]


def _not_loaded():
    from django.utils.translation import gettext

    return gettext("The question bank is not loaded.")


@pytest.mark.django_db
class TestNewKindsKeepTheReadingRules:
    """Las reglas de lectura de LV-158/LV-184 valen igual para los tipos nuevos."""

    def _limitations(self, operator, family):
        return KnowledgeAssessment.objects.create(
            operator=operator,
            kind="limitations",
            aircraft_family=family,
            question_count=1,
            correct_count=0,
            score_percent=0,
            passed=False,
            part_scores={
                "A": {"correct": 0, "total": 1, "percent": 0, "threshold": 100}
            },
            answers=[
                {
                    "id": "1",
                    "part": "A",
                    "text": "Invented stem",
                    "options": [
                        {"key": "a", "text": "Right choice"},
                        {"key": "b", "text": "Wrong choice"},
                    ],
                    "given": "b",
                    "answer": "a",
                    "correct": False,
                }
            ],
        )

    def test_an_operator_cannot_read_another_operators_attempt_of_the_same_company(
        self,
    ):
        family = make_family()
        client, _mine = _client("view_knowledgeassessment")
        other = _operator(employee_id="E-2", full_name="Operator B")
        theirs = self._limitations(other, family)

        response = client.get(reverse("assessment-detail", args=[theirs.pk]))

        assert response.status_code == 404

    def test_the_owner_reads_it_and_the_key_stays_hidden_without_its_permission(self):
        family = make_family()
        client, mine = _client("view_knowledgeassessment")
        attempt = self._limitations(mine, family)

        body = client.get(
            reverse("assessment-detail", args=[attempt.pk])
        ).content.decode()

        assert "Wrong choice" in body, "lo que contestó se ve"
        assert "Right choice" not in body, "la clave es el examen"

    def test_the_key_holder_sees_the_correct_answer(self):
        family = make_family()
        attempt = self._limitations(_operator(), family)
        client = login_as(
            "view_knowledgeassessment", "view_operator", "view_assessment_answers"
        )

        body = client.get(
            reverse("assessment-detail", args=[attempt.pk])
        ).content.decode()

        assert "Right choice" in body

    def test_the_history_on_the_record_lists_the_kind_with_and_without_permission(
        self,
    ):
        family = make_family()
        operator = _operator()
        attempt = self._limitations(operator, family)
        reader = login_as("view_operator", "view_knowledgeassessment")
        blind = login_as("view_operator")

        shown = reader.get(reverse("operator-detail", args=[operator.pk]))
        hidden = blind.get(reverse("operator-detail", args=[operator.pk]))

        assert reverse("assessment-detail", args=[attempt.pk]) in shown.content.decode()
        assert str(family) in shown.content.decode()
        assert hidden.context["assessments"] is None
