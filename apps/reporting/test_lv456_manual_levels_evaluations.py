"""LV-456: los dos huecos de la sección 5 del informe mensual, cerrados.

1. **Mantención por niveles** (`maintenance.kpis.due_by_level`, `due_soon_by_level`,
   `level_without_data` y `maintenance.levels`): sale de `level_statuses` con el corte
   como «hoy». Sin dato es «Pendiente» (`None`), nunca 0.
2. **Evaluaciones por tipo** (`evaluations.format` y `evaluations.by_kind`): `act19`
   sólo si el padrón al corte tiene algún intento de un tipo nuevo; si no, `lv158` y
   `by_kind` en `None` (los informes viejos no cambian).

Datos ficticios y fechas fijas (el corte es el 2026-11-30; nada depende de «hoy»:
lección LV-223).
"""

from datetime import date

import pytest

from apps.maintenance.models import MaintenanceProgram, MaintenanceRecord
from apps.registry.models import KnowledgeAssessment, QualificationType
from apps.reporting.builder import build
from apps.reporting.manual_case import (
    CUTOFF,
    PERIOD,
    aircraft,
    at,
    centre,
    doc_types,
    operator,
)


@pytest.fixture
def site(db):
    doc_types()
    return centre("CC901")


@pytest.fixture
def programmes(db):
    """Un programa general de 200 h/6 m, 400 h/12 m y 600 h/18 m (sin el sembrado)."""
    MaintenanceProgram.objects.all().delete()
    for level, hours, months in (
        ("basic", 200, 6),
        ("medium", 400, 12),
        ("advanced", 600, 18),
    ):
        MaintenanceProgram.objects.create(
            name="General ficticio",
            model_keywords="",
            level=level,
            interval_hours=hours,
            interval_months=months,
        )


def _manual():
    payload, missing = build(PERIOD, cutoff=CUTOFF)
    return payload["manual"], missing


def _done(tail, level, on):
    return MaintenanceRecord.objects.create(
        aircraft=tail,
        maintenance_type="scheduled",
        description=f"{level} hecha",
        level=level,
        status="completed",
        completed_date=on,
    )


def _levels(manual):
    return {
        row["level"]: (row["overdue"]["value"], row["soon"]["value"])
        for row in manual["maintenance"]["levels"]
    }


def _kpi(manual, key):
    return manual["maintenance"]["kpis"][key]["value"]


class TestMaintenanceByLevel:
    def test_overdue_soon_and_without_data_are_counted_at_the_cutoff(
        self, site, programmes
    ):
        overdue = aircraft("RPA-9001", site)
        _done(overdue, "basic", date(2026, 4, 1))  # vence 2026-10-01: vencida
        soon = aircraft("RPA-9002", site)
        _done(soon, "basic", date(2026, 6, 10))  # vence 2026-12-10: 10 días, próxima
        fine = aircraft("RPA-9003", site)
        _done(fine, "basic", date(2026, 11, 1))  # vence 2027-05-01: al día
        aircraft("RPA-9004", site)  # sin ninguna mantención: sin dato

        manual, missing = _manual()

        assert _kpi(manual, "due_by_level") == 1
        assert _kpi(manual, "due_soon_by_level") == 1
        assert _kpi(manual, "level_without_data") == 1
        assert _levels(manual)["basic"] == (1, 1)
        assert "manual.maintenance.kpis.due_by_level" not in missing

    def test_the_cutoff_is_the_reference_day_not_today(self, site, programmes):
        # Vence el 2026-12-05: al corte (30-11) quedan 5 días, es «próxima»; si se
        # midiera con otro día cambiaría de estado.
        tail = aircraft("RPA-9001", site)
        _done(tail, "basic", date(2026, 6, 5))

        manual, _missing = _manual()

        assert (_kpi(manual, "due_by_level"), _kpi(manual, "due_soon_by_level")) == (
            0,
            1,
        )

    def test_an_aircraft_overdue_in_two_levels_counts_once_in_the_total(
        self, site, programmes
    ):
        tail = aircraft("RPA-9001", site)
        _done(tail, "basic", date(2026, 4, 1))  # vence 2026-10-01
        _done(tail, "medium", date(2025, 10, 1))  # vence 2026-10-01

        manual, _missing = _manual()

        assert _kpi(manual, "due_by_level") == 1
        assert _levels(manual)["basic"][0] == 1
        assert _levels(manual)["medium"][0] == 1

    def test_a_level_nobody_can_measure_is_pending_not_zero(self, site, programmes):
        tail = aircraft("RPA-9001", site)
        _done(tail, "basic", date(2026, 4, 1))

        manual, missing = _manual()
        levels = _levels(manual)

        assert levels["basic"] == (1, 0)
        assert levels["medium"] == (None, None)
        assert levels["advanced"] == (None, None)
        assert "manual.maintenance.levels[2].overdue" in missing

    def test_the_levels_come_in_programme_order(self, site, programmes):
        _done(aircraft("RPA-9001", site), "basic", date(2026, 4, 1))

        manual, _missing = _manual()

        assert [row["level"] for row in manual["maintenance"]["levels"]] == [
            "basic",
            "medium",
            "advanced",
        ]

    def test_no_aircraft_with_data_leaves_every_figure_pending(self, site, programmes):
        aircraft("RPA-9001", site)  # con programa, pero sin mantención que contar

        manual, missing = _manual()

        assert _kpi(manual, "due_by_level") is None
        assert _kpi(manual, "due_soon_by_level") is None
        assert _kpi(manual, "level_without_data") == 1
        assert manual["maintenance"]["levels"] == []
        assert "manual.maintenance.kpis.due_soon_by_level" in missing
        # El detalle por nivel no repite el hueco del total: no suma pendientes.
        assert not [path for path in missing if "maintenance.levels" in path]

    def test_an_aircraft_without_a_programme_has_no_data(self, site, db):
        MaintenanceProgram.objects.all().delete()
        aircraft("RPA-9001", site)

        manual, _missing = _manual()

        assert _kpi(manual, "due_by_level") is None
        assert _kpi(manual, "level_without_data") == 1

    def test_an_empty_fleet_is_pending_not_zero(self, site, programmes):
        manual, _missing = _manual()

        assert _kpi(manual, "due_by_level") is None
        assert _kpi(manual, "due_soon_by_level") is None
        assert manual["maintenance"]["levels"] == []

    def test_only_the_report_fleet_is_measured(self, site, programmes):
        from apps.registry.models import Aircraft

        retired = aircraft("RPA-9001", site)
        _done(retired, "basic", date(2026, 4, 1))
        Aircraft.objects.filter(pk=retired.pk).update(status="retired")

        manual, _missing = _manual()

        assert _kpi(manual, "due_by_level") is None


def _attempt(person, kind, *, passed, taken, expires=None, family=None):
    row = KnowledgeAssessment.objects.create(
        operator=person,
        kind=kind,
        aircraft_family=family,
        question_count=25,
        correct_count=25 if passed else 5,
        score_percent=100 if passed else 20,
        passed=passed,
        expires_on=expires,
    )
    KnowledgeAssessment.objects.filter(pk=row.pk).update(taken_at=at(taken))
    return row


def _family(code):
    return QualificationType.objects.create(
        code=code, name=f"Modelo {code}", model_keywords=code.lower()
    )


def _by_kind(manual):
    return {
        row["kind"]: {
            key: row[key]["value"]
            for key in ("in_force", "lapsed", "failed_only", "never")
        }
        for row in manual["evaluations"]["by_kind"]
    }


class TestEvaluationsByKind:
    def test_only_previous_attempts_keep_the_old_format_and_no_kind_lines(self, site):
        person = operator("P1", site)
        _attempt(
            person,
            "legacy",
            passed=True,
            taken=date(2026, 10, 5),
            expires=date(2027, 10, 5),
        )

        manual, _missing = _manual()

        assert manual["evaluations"]["format"] == "lv158"
        # La hoja decide por `format`: sin tipos nuevos no hay líneas por tipo.
        assert manual["evaluations"]["by_kind"] == []

    def test_the_pending_count_does_not_grow_for_what_the_sheet_does_not_draw(
        self, site, programmes
    ):
        from apps.reporting.builder import find_missing

        person = operator("P1", site)
        _attempt(
            person,
            "legacy",
            passed=True,
            taken=date(2026, 10, 5),
            expires=date(2027, 10, 5),
        )
        aircraft("RPA-9001", site)  # sin nivel con dato

        manual, missing = _manual()

        assert missing == [f"manual.{path}" for path in find_missing(manual)]
        assert not [
            path
            for path in missing
            if "evaluations.by_kind" in path or "maintenance.levels" in path
        ]

    def test_a_base_without_assessments_is_still_the_old_format(self, site):
        manual, _missing = _manual()

        assert manual["evaluations"]["format"] == "lv158"

    def test_a_new_kind_attempt_switches_to_the_act19_format(self, site):
        person = operator("P1", site)
        _attempt(person, "general", passed=True, taken=date(2026, 11, 12))

        manual, _missing = _manual()

        assert manual["evaluations"]["format"] == "act19"

    def test_a_new_kind_attempt_after_the_cutoff_does_not_switch_it(self, site):
        person = operator("P1", site)
        _attempt(person, "general", passed=True, taken=date(2026, 12, 2))

        manual, _missing = _manual()

        assert manual["evaluations"]["format"] == "lv158"

    def test_a_new_kind_attempt_of_an_archived_row_does_not_switch_it(self, site):
        person = operator("P1", site)
        row = _attempt(person, "general", passed=True, taken=date(2026, 11, 12))
        KnowledgeAssessment.objects.filter(pk=row.pk).update(is_active=False)

        manual, _missing = _manual()

        assert manual["evaluations"]["format"] == "lv158"

    def test_in_force_lapsed_failed_only_and_never_per_kind(self, site):
        fresh = operator("P1", site)
        stale = operator("P2", site)
        failed = operator("P3", site)
        operator("P4", site)
        _attempt(
            fresh,
            "annual",
            passed=True,
            taken=date(2026, 10, 5),
            expires=date(2027, 10, 5),
            family=_family("ZETA"),
        )
        _attempt(
            stale,
            "annual",
            passed=True,
            taken=date(2025, 6, 1),
            expires=date(2026, 6, 1),
            family=QualificationType.objects.get(code="ZETA"),
        )
        _attempt(
            failed,
            "annual",
            passed=False,
            taken=date(2026, 10, 6),
            family=QualificationType.objects.get(code="ZETA"),
        )

        manual, _missing = _manual()

        assert _by_kind(manual)["annual"] == {
            "in_force": 1,
            "lapsed": 1,
            "failed_only": 1,
            "never": 1,
        }
        # El cuestionario anual no mueve al examen general.
        assert _by_kind(manual)["general"]["never"] == 4

    def test_a_kind_that_does_not_expire_is_in_force(self, site):
        person = operator("P1", site)
        _attempt(person, "general", passed=True, taken=date(2025, 1, 5), expires=None)

        manual, _missing = _manual()

        assert _by_kind(manual)["general"]["in_force"] == 1
        # Y el total heredado ya no revienta con un vencimiento nulo.
        assert manual["evaluations"]["kpis"]["in_force"]["value"] == 1

    def test_a_later_failure_does_not_cancel_a_passed_attempt(self, site):
        person = operator("P1", site)
        _attempt(person, "general", passed=True, taken=date(2026, 10, 5))
        _attempt(person, "general", passed=False, taken=date(2026, 11, 20))

        manual, _missing = _manual()

        assert _by_kind(manual)["general"] == {
            "in_force": 1,
            "lapsed": 0,
            "failed_only": 0,
            "never": 0,
        }

    def test_an_attempt_after_the_cutoff_does_not_count(self, site):
        person = operator("P1", site)
        _attempt(person, "general", passed=True, taken=date(2026, 11, 10))
        _attempt(
            person,
            "limitations",
            passed=True,
            taken=date(2026, 12, 2),
            family=_family("ZETA"),
        )

        manual, _missing = _manual()

        assert _by_kind(manual)["limitations"]["never"] == 1
        assert _by_kind(manual)["general"]["in_force"] == 1

    def test_a_family_kind_is_in_force_if_any_family_is(self, site):
        person = operator("P1", site)
        old = _family("OLDM")
        new = _family("NEWM")
        _attempt(
            person,
            "annual",
            passed=True,
            taken=date(2025, 6, 1),
            expires=date(2026, 6, 1),
            family=old,
        )
        _attempt(
            person,
            "annual",
            passed=True,
            taken=date(2026, 10, 5),
            expires=date(2027, 10, 5),
            family=new,
        )

        manual, _missing = _manual()

        assert _by_kind(manual)["annual"]["in_force"] == 1
        assert _by_kind(manual)["annual"]["lapsed"] == 0

    def test_a_family_kind_lapsed_in_every_family_is_lapsed(self, site):
        person = operator("P1", site)
        _attempt(
            person,
            "annual",
            passed=True,
            taken=date(2025, 6, 1),
            expires=date(2026, 6, 1),
            family=_family("OLDM"),
        )
        _attempt(
            person,
            "annual",
            passed=True,
            taken=date(2025, 7, 1),
            expires=date(2026, 7, 1),
            family=_family("NEWM"),
        )

        manual, _missing = _manual()

        assert _by_kind(manual)["annual"]["lapsed"] == 1
        assert _by_kind(manual)["annual"]["in_force"] == 0

    def test_a_newer_lapsed_pass_in_the_same_family_replaces_an_older_one(self, site):
        # Dentro de una familia manda el último aprobado; sus fechas no se mezclan.
        person = operator("P1", site)
        family = _family("ZETA")
        _attempt(
            person,
            "annual",
            passed=True,
            taken=date(2026, 1, 5),
            expires=date(2027, 1, 5),
            family=family,
        )
        _attempt(
            person,
            "annual",
            passed=True,
            taken=date(2026, 6, 5),
            expires=date(2026, 8, 5),
            family=family,
        )

        manual, _missing = _manual()

        assert _by_kind(manual)["annual"]["lapsed"] == 1

    def test_the_existing_kpis_do_not_change(self, site):
        person = operator("P1", site)
        _attempt(
            person,
            "legacy",
            passed=True,
            taken=date(2026, 10, 5),
            expires=date(2027, 10, 5),
        )
        _attempt(person, "general", passed=True, taken=date(2026, 11, 12))

        manual, _missing = _manual()
        kpis = manual["evaluations"]["kpis"]

        assert set(kpis) == {
            "roster",
            "in_force",
            "lapsed",
            "failed_only",
            "never",
            "reg018_operators",
            "reg019_operators",
        }
        assert kpis["roster"]["value"] == 1 and kpis["in_force"]["value"] == 1


class TestTheSheetDrawsTheNewLines:
    @pytest.fixture
    def reader(self, client, db):
        from django.contrib.auth.models import Permission, User

        user = User.objects.create_user("reader", password="x")
        user.user_permissions.add(
            Permission.objects.get(
                codename="view_reportrun", content_type__app_label="reporting"
            )
        )
        client.force_login(user)
        return client

    @staticmethod
    def _html(client, payload):
        from django.urls import reverse

        from apps.reporting.models import ReportRun

        ReportRun.objects.create(
            period=PERIOD, revision=0, generated_by="t", payload=payload
        )
        return client.get(
            reverse("monthly-report"), {"period": "2026-11"}
        ).content.decode()

    def test_act19_draws_one_line_per_kind_and_drops_the_old_label(
        self, reader, site, programmes
    ):
        person = operator("P1", site)
        _attempt(person, "general", passed=True, taken=date(2026, 11, 12))
        tail = aircraft("RPA-9001", site)
        _done(tail, "basic", date(2026, 4, 1))
        payload, _missing = build(PERIOD, cutoff=CUTOFF)

        html = self._html(reader, payload)

        assert "Examen general:" in html
        assert "Limitaciones y emergencias:" in html
        assert "Cuestionario anual:" in html
        assert "formato previo a la Act. 19" not in html
        assert "aeronaves con algún nivel vencido" in html
        assert "Básica:" in html and "Avanzada:" in html
        assert "las horas son las registradas al construir el informe" in html

    def test_the_old_format_keeps_its_label_and_no_kind_lines(
        self, reader, site, programmes
    ):
        person = operator("P1", site)
        _attempt(
            person,
            "legacy",
            passed=True,
            taken=date(2026, 10, 5),
            expires=date(2027, 10, 5),
        )
        payload, _missing = build(PERIOD, cutoff=CUTOFF)

        html = self._html(reader, payload)

        assert "formato previo a la Act. 19" in html
        assert "Examen general:" not in html
        assert "Cuestionario anual:" not in html
