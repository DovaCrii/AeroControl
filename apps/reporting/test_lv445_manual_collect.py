"""LV-445: lo que mide la sección 5 (Manual de Operaciones, Act. 19).

Protege, por orden de gravedad:

1. **Que los informes anteriores a la vigencia no cambien**: sin la llave `manual`.
2. **Que «sin dato» nunca sea cero**: un tipo de documento que no existe deja la cifra
   en `None` y su ruta en `missing_fields`; un tipo que existe sin documentos es 0.
3. **Que el plazo se mida donde se puede medir**: lo importado en lote o sin fecha de
   misión es «sin evaluar», no «en plazo» ni «fuera de plazo».
4. Que cada universo sea el que ya usa el resto del informe (faenas que operan, flota
   operativa, padrón al corte) y que ninguna cuenta se haga con la fecha de hoy.

Todo con fechas fijas (la fecha es andamio: lección LV-223) y datos ficticios.
"""

from datetime import date

import pytest

from apps.compliance.models import DocumentType
from apps.operations.models import FlightPermission, FlightRecord
from apps.registry.models import Operator
from apps.reporting import manual as manual_module
from apps.reporting.builder import build
from apps.reporting.manual import ACT19_EFFECTIVE, collect_manual
from apps.reporting.manual_case import (
    CUTOFF,
    PERIOD,
    aircraft,
    assessment,
    at,
    centre,
    doc_types,
    document,
    operator,
)


@pytest.fixture
def types(db):
    return doc_types()


@pytest.fixture
def site(db):
    return centre("CC901")


def _manual(early=False, cutoff=CUTOFF):
    payload, missing = build(PERIOD, cutoff=cutoff, early=early, early_reason="x" * 12)
    return payload.get("manual"), missing


def _value(node):
    return node["value"]


class TestTheSectionExistsOnlyFromTheEffectiveDate:
    def test_the_constant_is_the_dgac_approval(self):
        assert ACT19_EFFECTIVE == date(2026, 11, 10)

    def test_october_has_no_manual_key_and_november_measures_from_the_10th(
        self, types, site
    ):
        before, _missing = build(date(2026, 10, 1), cutoff=date(2026, 10, 31))
        after, _missing = build(PERIOD, cutoff=CUTOFF)

        assert "manual" not in before
        assert after["manual"]["window"] == {"from": "2026-11-10", "to": "2026-11-30"}
        assert after["manual"]["edition"]["code"] == "Act. 19"

    def test_a_cutoff_before_the_effective_date_gives_none(self, types, site):
        assert collect_manual(PERIOD, date(2026, 11, 9), [site]) is None

    def test_a_record_dated_before_the_effective_date_is_not_counted(self, types, site):
        log = types["flight-log"]
        document(log, site, issue=date(2026, 11, 5), loaded=at(date(2026, 11, 6)))
        document(log, site, issue=date(2026, 11, 12), loaded=at(date(2026, 11, 13)))

        manual, _missing = _manual()

        assert _value(manual["missions"]["kpis"]["records_total"]) == 1

    def test_december_measures_the_whole_month(self, types, site):
        manual = collect_manual(date(2026, 12, 1), date(2026, 12, 31), [site])

        assert manual["window"]["from"] == "2026-12-01"


class TestTheDeadlineIsMeasuredWhereItCanBe:
    @staticmethod
    def _counts(manual):
        kpis = manual["missions"]["kpis"]
        return {
            key: _value(kpis[f"records_{key}"])
            for key in ("on_time", "late", "not_assessable")
        }

    def test_loaded_the_next_day_is_on_time_two_days_later_is_late(self, types, site):
        log = types["flight-log"]
        # Misión el 12-11: cargado el 13-11 cumple; el 14-11 no.
        document(log, site, issue=date(2026, 11, 12), loaded=at(date(2026, 11, 13)))
        document(log, site, issue=date(2026, 11, 12), loaded=at(date(2026, 11, 14)))

        manual, _missing = _manual()

        assert self._counts(manual) == {"on_time": 1, "late": 1, "not_assessable": 0}
        assert _value(manual["missions"]["kpis"]["records_assessable"]) == 2

    def test_a_record_without_a_mission_date_is_not_assessable(self, types, site):
        # Sin fecha de misión, la cuenta cae en el día de carga (que sí está en la
        # ventana) pero no puede medirse contra el plazo.
        document(types["flight-log"], site, loaded=at(date(2026, 11, 15)))

        manual, _missing = _manual()

        assert self._counts(manual) == {"on_time": 0, "late": 0, "not_assessable": 1}

    def test_a_batch_imported_record_is_not_assessable(self, types, site):
        document(
            types["flight-log"],
            site,
            issue=date(2026, 11, 12),
            loaded=at(date(2026, 11, 29)),
            source="Z:/ficticio/registro.pdf",
        )

        manual, _missing = _manual()

        assert self._counts(manual) == {"on_time": 0, "late": 0, "not_assessable": 1}

    def test_the_rows_are_one_per_operating_centre_and_add_up(self, types, site):
        other = centre("CC902")
        log = types["flight-log"]
        document(log, site, issue=date(2026, 11, 12), loaded=at(date(2026, 11, 12)))
        document(log, other, issue=date(2026, 11, 12), loaded=at(date(2026, 11, 20)))

        manual, _missing = _manual()
        rows = {row["code"]: row for row in manual["missions"]["rows"]}

        assert set(rows) == {"CC901", "CC902"}
        assert rows["CC901"]["on_time"] == 1 and rows["CC902"]["late"] == 1
        kpis = manual["missions"]["kpis"]
        assert _value(kpis["records_total"]) == 2
        assert _value(kpis["centres_with_records"]) == 2
        assert _value(kpis["centres_operating"]) == 2

    def test_a_centre_that_does_not_fly_is_not_a_row(self, types, site):
        from apps.registry.models import CostCenter

        CostCenter.objects.create(code="CC950", name="No vuela", operates_flights=False)

        manual, _missing = _manual()

        assert [row["code"] for row in manual["missions"]["rows"]] == ["CC901"]

    def test_the_monthly_review_status_travels_with_the_row(self, types, site):
        from apps.compliance.models import MonthlyComplianceReview

        MonthlyComplianceReview.objects.create(
            cost_center=site, period=PERIOD, status="completed"
        )

        manual, _missing = _manual()

        assert manual["missions"]["rows"][0]["review"] == "completed"


class TestNoDataIsPendingNeverZero:
    def test_a_missing_type_is_none_and_its_path_is_in_missing_fields(
        self, types, site
    ):
        DocumentType.objects.filter(code="flight-log").delete()

        manual, missing = _manual()
        kpis = manual["missions"]["kpis"]

        assert _value(kpis["records_total"]) is None
        assert _value(kpis["records_late"]) is None
        assert manual["missions"]["rows"][0]["records"] is None
        assert "manual.missions.kpis.records_total" in missing

    def test_an_existing_type_with_no_documents_is_zero_not_none(self, types, site):
        manual, missing = _manual()
        kpis = manual["missions"]["kpis"]

        assert _value(kpis["records_total"]) == 0
        assert manual["missions"]["rows"][0]["records"] == 0
        assert "manual.missions.kpis.records_total" not in missing

    def test_a_missing_inspection_type_leaves_the_fleet_pending(self, types, site):
        aircraft("RPA-9001", site)
        DocumentType.objects.filter(code="drone-inspection").delete()

        manual, missing = _manual()
        kpis = manual["inspections"]["kpis"]

        assert _value(kpis["fleet"]) == 1
        assert _value(kpis["in_force"]) is None
        assert manual["inspections"]["gaps"] == []
        assert "manual.inspections.kpis.in_force" in missing

    def test_the_review_in_24_hours_is_pending_until_a_review_exists(self, types, site):
        manual, missing = _manual()

        assert _value(manual["missions"]["kpis"]["reviewed_within_24h"]) is None
        assert _value(manual["maintenance"]["kpis"]["due_by_level"]) is None
        assert "manual.missions.kpis.reviewed_within_24h" in missing


class TestMissions:
    @staticmethod
    def _flight(site, tail, day):
        permit = FlightPermission.objects.create(
            cost_center=site,
            purpose="photogrammetry",
            status="approved",
            location="Sector ficticio",
            area_type="unpopulated",
        )
        pilot = Operator.objects.filter(employee_id="PILOT").first() or operator(
            "PILOT", site
        )
        return FlightRecord.objects.create(
            permission=permit,
            actual_date=day,
            departure_time="10:00",
            arrival_time="11:00",
            pilot=pilot,
            aircraft=tail,
        )

    def test_without_digital_flights_the_missions_are_pending_not_zero(
        self, types, site
    ):
        manual, missing = _manual()
        kpis = manual["missions"]["kpis"]

        assert _value(kpis["missions_flown"]) is None
        assert _value(kpis["missions_without_record"]) is None
        assert "manual.missions.kpis.missions_flown" in missing

    def test_a_mission_day_without_a_record_of_that_day_counts_once(self, types, site):
        tail = aircraft("RPA-9001", site)
        self._flight(site, tail, date(2026, 11, 12))
        self._flight(site, tail, date(2026, 11, 12))  # misma faena y día: una misión
        self._flight(site, tail, date(2026, 11, 20))
        document(
            types["flight-log"],
            site,
            issue=date(2026, 11, 12),
            loaded=at(date(2026, 11, 12)),
        )

        manual, _missing = _manual()
        kpis = manual["missions"]["kpis"]

        assert _value(kpis["missions_flown"]) == 2
        assert _value(kpis["missions_without_record"]) == 1


class TestInspectionsPerAircraft:
    def test_one_aircraft_per_state_and_only_the_operating_fleet(self, types, site):
        from apps.registry.models import Aircraft, CostCenter

        inspection = types["drone-inspection"]
        current = aircraft("RPA-9001", site)
        lapsed = aircraft("RPA-9002", site)
        undated = aircraft("RPA-9003", site)
        aircraft("RPA-9004", site)  # sin documento
        retired = aircraft("RPA-9005", site)
        Aircraft.objects.filter(pk=retired.pk).update(status="retired")
        idle_site = CostCenter.objects.create(
            code="CC950", name="No vuela", operates_flights=False
        )
        aircraft("RPA-9006", idle_site)
        document(inspection, current, expiry=date(2027, 3, 1))
        document(inspection, lapsed, expiry=date(2026, 11, 1))
        document(inspection, undated)

        manual, _missing = _manual()
        kpis = manual["inspections"]["kpis"]

        assert {key: _value(kpis[key]) for key in kpis} == {
            "fleet": 4,
            "in_force": 1,
            "lapsed": 1,
            "undated": 1,
            "missing": 1,
            "reg020_aircraft": 0,
        }
        assert manual["inspections"]["gaps"] == ["RPA-9002", "RPA-9003", "RPA-9004"]

    def test_an_aircraft_loaded_after_the_cutoff_is_not_in_the_fleet(self, types, site):
        from apps.reporting.manual_case import born

        late = aircraft("RPA-9001", site)
        born(late, at(date(2026, 12, 3)))

        manual, _missing = _manual()

        assert _value(manual["inspections"]["kpis"]["fleet"]) == 0

    def test_reg020_counts_aircraft_with_a_current_record(self, types, site):
        with_record = aircraft("RPA-9001", site)
        aircraft("RPA-9002", site)
        document(types["rpa-service-life"], with_record)

        manual, _missing = _manual()

        assert _value(manual["inspections"]["kpis"]["reg020_aircraft"]) == 1


class TestEvaluations:
    def test_a_later_failure_does_not_cancel_a_passed_attempt(self, types, site):
        person = operator("P1", site)
        assessment(
            person, passed=True, taken=date(2026, 10, 5), expires=date(2027, 10, 5)
        )
        assessment(
            person, passed=False, taken=date(2026, 11, 20), expires=date(2027, 11, 20)
        )

        manual, _missing = _manual()
        kpis = manual["evaluations"]["kpis"]

        assert _value(kpis["in_force"]) == 1 and _value(kpis["failed_only"]) == 0

    def test_one_operator_per_state(self, types, site):
        passed = operator("P1", site)
        expired = operator("P2", site)
        failed = operator("P3", site)
        operator("P4", site)
        assessment(
            passed, passed=True, taken=date(2026, 10, 5), expires=date(2027, 10, 5)
        )
        assessment(
            expired, passed=True, taken=date(2025, 6, 1), expires=date(2026, 6, 1)
        )
        assessment(
            failed, passed=False, taken=date(2026, 10, 6), expires=date(2027, 10, 6)
        )

        manual, _missing = _manual()
        kpis = manual["evaluations"]["kpis"]

        assert {key: _value(node) for key, node in kpis.items()} == {
            "roster": 4,
            "in_force": 1,
            "lapsed": 1,
            "failed_only": 1,
            "never": 1,
            "reg018_operators": 0,
            "reg019_operators": 0,
        }
        assert manual["evaluations"]["format"] == "lv158"

    def test_an_attempt_taken_after_the_cutoff_does_not_count(self, types, site):
        person = operator("P1", site)
        assessment(
            person, passed=True, taken=date(2026, 12, 2), expires=date(2027, 12, 2)
        )

        manual, _missing = _manual()

        assert _value(manual["evaluations"]["kpis"]["never"]) == 1

    def test_reg018_and_reg019_count_operators_with_a_current_record(self, types, site):
        first = operator("P1", site)
        operator("P2", site)
        document(types["operator-qualification-intake"], first)
        document(types["operator-theory-evaluations"], first)

        manual, _missing = _manual()
        kpis = manual["evaluations"]["kpis"]

        assert _value(kpis["reg018_operators"]) == 1
        assert _value(kpis["reg019_operators"]) == 1
        assert _value(kpis["roster"]) == 2


class TestMaintenance:
    def test_completed_in_the_window_and_open_at_the_cutoff(self, types, site):
        from apps.maintenance.models import MaintenanceRecord
        from apps.reporting.manual_case import born

        tail = aircraft("RPA-9001", site)

        def record(**fields):
            row = MaintenanceRecord.objects.create(
                aircraft=tail, maintenance_type="preventive", description="x", **fields
            )
            return born(row)

        record(status="completed", completed_date=date(2026, 11, 15))
        record(
            status="completed", completed_date=date(2026, 11, 5)
        )  # antes de la vigencia
        record(status="pending")
        record(status="pending", is_active=False)  # anulada: no cuenta

        manual, _missing = _manual()
        kpis = manual["maintenance"]["kpis"]

        assert _value(kpis["completed_in_window"]) == 1
        assert _value(kpis["open_at_cutoff"]) == 1


class TestAnEarlyCutoffDoesNotCountWhatWasLoadedAfterIt:
    def test_a_document_created_after_the_cutoff_is_left_out(self, types, site):
        log = types["flight-log"]
        document(log, site, issue=date(2026, 11, 12), loaded=at(date(2026, 11, 13)))
        document(log, site, issue=date(2026, 11, 14), loaded=at(date(2026, 11, 22)))

        early, _missing = _manual(early=True, cutoff=date(2026, 11, 18))
        closing, _missing = _manual(cutoff=date(2026, 11, 30))

        assert _value(early["missions"]["kpis"]["records_total"]) == 1
        assert _value(closing["missions"]["kpis"]["records_total"]) == 2


class TestTheDocumentTypesAreLookedUpByCode:
    def test_the_codes_are_the_ones_of_the_monthly_close(self):
        from apps.compliance.monthly import MONTHLY_RECORD_CODES

        assert manual_module.TYPE_CODES["mission"] in MONTHLY_RECORD_CODES

    def test_an_archived_type_still_exists(self, types, site):
        DocumentType.objects.filter(code="flight-log").update(is_active=False)

        manual, _missing = _manual()

        assert _value(manual["missions"]["kpis"]["records_total"]) == 0


class TestTheQueryBudget:
    """La sección no consulta por faena, por aeronave ni por operador: el número de
    consultas es el mismo con pocas que con muchas filas. Medido sobre la segunda
    llamada (la primera calienta `ContentType`, que no es costo del informe)."""

    # Medido el 2026-11-16: 10 (tipos, flota, documentos de aeronave, padrón,
    # documentos y pruebas de operadores, REG-016, cierres, vuelos y mantenciones).
    # El diseño decía 8; no se afloja para que pase un cambio. LV-447 sumó una fuente
    # nueva (las revisiones de 24 h, una sola agregación): 11.
    CEILING = 11

    @staticmethod
    def _count(centres):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from apps.reporting.builder import operating_centres

        operating = operating_centres()
        collect_manual(PERIOD, CUTOFF, operating)
        with CaptureQueriesContext(connection) as queries:
            collect_manual(PERIOD, CUTOFF, operating)
        return len(queries)

    def test_the_count_does_not_grow_with_the_rows(self, db):
        from apps.reporting.manual_case import make_manual_case

        make_manual_case(centres=2, aircraft_count=2)
        small = self._count(2)
        for number in range(3, 13):
            centre(f"CC91{number}")
            aircraft(f"RPA-91{number}", centre(f"CC92{number}"))
            operator(f"Q{number}", centre(f"CC93{number}"))
        large = self._count(12)

        print(f"\nMEDIDO consultas de la sección 5: {small} y {large}")
        assert small == large <= self.CEILING


class TestTheReviewIn24HoursIsReal:
    """LV-447: `reviewed_within_24h` deja de ser siempre «Pendiente»."""

    @staticmethod
    def _review(site, types, mission, reviewed):
        from apps.compliance.models import MissionReview

        document(types["flight-log"], site, issue=mission, loaded=at(mission))
        review = MissionReview.objects.get(document__issue_date=mission)
        if reviewed is not None:
            review.mark("reviewed", None, when=reviewed)
        return review

    @staticmethod
    def _local(day, hour, minute=0):
        from datetime import datetime

        from django.utils import timezone

        return timezone.make_aware(datetime(day.year, day.month, day.day, hour, minute))

    def test_it_counts_the_ones_reviewed_by_the_end_of_the_due_day(self, types, site):
        self._review(
            site, types, date(2026, 11, 12), self._local(date(2026, 11, 13), 23, 59)
        )
        self._review(
            site, types, date(2026, 11, 16), self._local(date(2026, 11, 18), 0, 1)
        )
        self._review(site, types, date(2026, 11, 19), None)

        manual, missing = _manual()

        assert _value(manual["missions"]["kpis"]["reviewed_within_24h"]) == 1
        assert "manual.missions.kpis.reviewed_within_24h" not in missing

    def test_reviews_exist_but_none_on_time_is_zero_not_pending(self, types, site):
        self._review(site, types, date(2026, 11, 12), None)

        manual, _missing = _manual()

        assert _value(manual["missions"]["kpis"]["reviewed_within_24h"]) == 0

    def test_a_mission_before_the_effective_date_is_not_counted(self, types, site):
        self._review(site, types, date(2026, 11, 5), self._local(date(2026, 11, 6), 9))

        manual, _missing = _manual()

        assert _value(manual["missions"]["kpis"]["reviewed_within_24h"]) is None

    def test_an_early_cutoff_ignores_what_was_reviewed_after_it(self, types, site):
        self._review(
            site, types, date(2026, 11, 12), self._local(date(2026, 11, 13), 9)
        )
        self._review(
            site, types, date(2026, 11, 16), self._local(date(2026, 11, 17), 9)
        )

        manual, _missing = _manual(early=True, cutoff=date(2026, 11, 14))

        assert _value(manual["missions"]["kpis"]["reviewed_within_24h"]) == 1

    def test_only_the_reviews_of_the_report_centres_count(self, types, site):
        other = centre("CC902")
        self._review(
            other, types, date(2026, 11, 12), self._local(date(2026, 11, 13), 9)
        )

        manual = collect_manual(PERIOD, CUTOFF, [site])

        assert _value(manual["missions"]["kpis"]["reviewed_within_24h"]) is None
