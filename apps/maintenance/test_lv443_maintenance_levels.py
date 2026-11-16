"""LV-443 (B8): mantención por niveles del Manual Act. 19 (Anexo F) y hoja de vida REG-020.

Lo que se afirma:

* la regla «lo que ocurra primero» (horas de vuelo o meses) por nivel, con el límite que
  corresponde, y un nivel sólo en meses (Elios 3) que ignora las horas;
* un nivel superior reinicia los inferiores, y uno inferior no reinicia los superiores;
* completar un nivel abre el siguiente `scheduled` **una sola vez**, que lo avisa la regla de
  alerta de siempre sobre `scheduled_date`;
* las horas acumuladas son la base más los vuelos posteriores; sin libro, `None` (no cero);
* la hoja de vida exige las dos lecturas, acota por empresa y su PDF sale en `application/pdf`;
* la siembra del Anexo F y que no inventa lo que el Manual deja «según fabricante».

Datos ficticios. Los programas de las reglas se crean acá con una palabra clave propia, para
no depender de lo sembrado por la migración.
"""

import datetime
import re
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from apps.compliance.models import Alert, AlertRule
from apps.compliance.test_lv372_tenant_scope import world  # noqa: F401
from apps.core.testing import login_as
from apps.maintenance import levels
from apps.maintenance.models import (
    AircraftLogbook,
    MaintenanceProgram,
    MaintenanceRecord,
    add_months,
)
from apps.operations.models import FlightRecord
from apps.registry.models import Aircraft

D = datetime.date


def _aircraft(model="Zeta 1", registration="CC-L443"):
    return Aircraft.objects.create(
        registration=registration, type="RPA", model=model, manufacturer="Test"
    )


def _program(level, hours, months, keywords="zeta", name="Zeta programme"):
    return MaintenanceProgram.objects.create(
        name=name,
        model_keywords=keywords,
        level=level,
        interval_hours=hours,
        interval_months=months,
    )


def _done(aircraft, level, on, hours_at=None, **extra):
    return MaintenanceRecord.objects.create(
        aircraft=aircraft,
        maintenance_type="scheduled",
        description=f"{level} done",
        level=level,
        status="completed",
        completed_date=on,
        hours_at=hours_at,
        **extra,
    )


def _logbook(aircraft, hours, on=D(2026, 1, 1)):
    return AircraftLogbook.objects.create(
        aircraft=aircraft, hours_baseline=Decimal(hours), baseline_on=on
    )


def _basic(aircraft, today, hours_now=None):
    (status,) = [
        item
        for item in levels.level_statuses(aircraft, today, hours_now)
        if item.level == "basic"
    ]
    return status


@pytest.mark.django_db
class TestFirstOfHoursOrMonths:
    """DJI basic = 200 h or 6 months, whichever comes first."""

    @pytest.fixture(autouse=True)
    def programme(self, db):
        _program("basic", 200, 6)
        self.aircraft = _aircraft()
        _done(self.aircraft, "basic", D(2026, 1, 10), hours_at=Decimal("1000"))

    def test_nothing_reached_is_up_to_date(self):
        status = _basic(self.aircraft, D(2026, 3, 1), Decimal("1050"))
        assert status.state == levels.OK
        assert status.due_date == D(2026, 7, 10)
        assert status.due_hours == Decimal("1200")

    def test_hours_reached_before_the_date_makes_it_overdue_by_hours(self):
        status = _basic(self.aircraft, D(2026, 3, 1), Decimal("1200"))
        assert status.state == levels.OVERDUE
        assert status.limiting == "hours"

    def test_date_reached_before_the_hours_makes_it_overdue_by_date(self):
        status = _basic(self.aircraft, D(2026, 7, 10), Decimal("1010"))
        assert status.state == levels.OVERDUE
        assert status.limiting == "date"

    def test_the_hours_notice_is_ten_percent_of_the_interval(self):
        assert _basic(self.aircraft, D(2026, 3, 1), Decimal("1179")).state == levels.OK
        assert (
            _basic(self.aircraft, D(2026, 3, 1), Decimal("1180")).state == levels.SOON
        )

    def test_the_date_notice_is_fifteen_days(self):
        assert _basic(self.aircraft, D(2026, 6, 24), Decimal("1010")).state == levels.OK
        assert (
            _basic(self.aircraft, D(2026, 6, 25), Decimal("1010")).state == levels.SOON
        )

    def test_without_hours_data_only_the_date_counts(self):
        status = _basic(self.aircraft, D(2026, 3, 1), None)
        assert status.state == levels.OK
        assert _basic(self.aircraft, D(2026, 7, 11), None).state == levels.OVERDUE

    def test_a_completion_without_hours_still_counts_by_date(self):
        MaintenanceRecord.objects.all().delete()
        _done(self.aircraft, "basic", D(2026, 1, 10), hours_at=None)
        status = _basic(self.aircraft, D(2026, 3, 1), Decimal("99999"))
        assert status.due_hours is None
        assert status.state == levels.OK

    def test_a_level_never_done_has_no_data_not_a_guess(self):
        MaintenanceRecord.objects.all().delete()
        status = _basic(self.aircraft, D(2026, 3, 1), Decimal("5000"))
        assert status.state == levels.NO_DATA
        assert status.due_date is None and status.due_hours is None


@pytest.mark.django_db
def test_a_months_only_programme_ignores_the_hours():
    """Elios 3: «al menos cada 12 meses», sin horas."""
    _program("basic", None, 12, keywords="zeta")
    aircraft = _aircraft()
    _logbook(aircraft, "9999")
    _done(aircraft, "basic", D(2026, 1, 10), hours_at=Decimal("5"))

    status = _basic(aircraft, D(2026, 6, 1), Decimal("9999"))

    assert status.state == levels.OK
    assert status.due_hours is None
    assert status.due_date == D(2027, 1, 10)
    assert _basic(aircraft, D(2027, 1, 10), Decimal("9999")).state == levels.OVERDUE


@pytest.mark.django_db
class TestHigherLevelsRestartLowerOnes:
    @pytest.fixture(autouse=True)
    def programmes(self, db):
        _program("basic", 200, 6)
        _program("medium", 400, 12)
        _program("advanced", 600, 18)
        self.aircraft = _aircraft()

    def _by_level(self, today):
        return {
            item.level: item
            for item in levels.level_statuses(self.aircraft, today, Decimal("0"))
        }

    def test_an_advanced_completion_restarts_basic_and_medium(self):
        _done(self.aircraft, "basic", D(2026, 1, 10), Decimal("100"))
        advanced = _done(self.aircraft, "advanced", D(2026, 3, 1), Decimal("300"))

        statuses = self._by_level(D(2026, 3, 2))

        assert statuses["basic"].last == advanced
        assert statuses["basic"].due_date == D(2026, 9, 1)
        assert statuses["medium"].last == advanced
        assert statuses["advanced"].last == advanced

    def test_a_basic_completion_does_not_restart_medium(self):
        medium = _done(self.aircraft, "medium", D(2026, 1, 10), Decimal("100"))
        _done(self.aircraft, "basic", D(2026, 5, 1), Decimal("250"))

        statuses = self._by_level(D(2026, 5, 2))

        assert statuses["medium"].last == medium
        assert statuses["medium"].due_date == D(2027, 1, 10)

    def test_repair_and_inspection_never_restart_a_clock(self):
        basic = _done(self.aircraft, "basic", D(2026, 1, 10), Decimal("100"))
        _done(self.aircraft, "repair", D(2026, 5, 1), Decimal("250"))
        _done(self.aircraft, "inspection", D(2026, 5, 2), Decimal("251"))

        assert self._by_level(D(2026, 5, 3))["basic"].last == basic

    def test_a_voided_record_does_not_count(self):
        basic = _done(self.aircraft, "basic", D(2026, 1, 10), Decimal("100"))
        voided = _done(self.aircraft, "advanced", D(2026, 3, 1), Decimal("300"))
        voided.is_active = False
        voided.save()

        assert self._by_level(D(2026, 3, 2))["basic"].last == basic


def test_add_months_clamps_to_the_end_of_the_month():
    assert add_months(D(2026, 8, 31), 6) == D(2027, 2, 28)
    assert add_months(D(2027, 8, 31), 6) == D(2028, 2, 29)
    assert add_months(D(2026, 1, 10), 18) == D(2027, 7, 10)
    assert add_months(D(2026, 12, 15), 1) == D(2027, 1, 15)


@pytest.mark.django_db
class TestAccumulatedHours:
    def _flight(self, world, day, start, end):  # noqa: F811
        row = world["a"]
        return FlightRecord.objects.create(
            permission=row["permit"],
            actual_date=day,
            departure_time=start,
            arrival_time=end,
            pilot=row["operator"],
            aircraft=row["aircraft"],
        )

    def test_it_is_the_baseline_plus_the_flights_after_it(self, world):  # noqa: F811
        aircraft = world["a"]["aircraft"]
        _logbook(aircraft, "100", on=D(2026, 5, 1))
        self._flight(world, D(2026, 5, 1), datetime.time(9), datetime.time(12))
        self._flight(world, D(2026, 5, 2), datetime.time(9), datetime.time(10, 30))
        self._flight(world, D(2026, 5, 3), datetime.time(9), datetime.time(9, 30))

        # The flight on the baseline date itself is already inside the baseline.
        assert AircraftLogbook.hours_for(aircraft) == Decimal("102.0")

    def test_without_a_baseline_date_every_flight_counts(self, world):  # noqa: F811
        aircraft = world["a"]["aircraft"]
        AircraftLogbook.objects.create(aircraft=aircraft, hours_baseline=Decimal("0"))
        self._flight(world, D(2026, 5, 2), datetime.time(9), datetime.time(10, 30))

        assert AircraftLogbook.hours_for(aircraft) == Decimal("1.5")

    def test_an_archived_flight_does_not_count(self, world):  # noqa: F811
        aircraft = world["a"]["aircraft"]
        _logbook(aircraft, "10", on=D(2026, 5, 1))
        flight = self._flight(world, D(2026, 5, 2), datetime.time(9), datetime.time(11))
        flight.is_active = False
        flight.save()

        assert AircraftLogbook.hours_for(aircraft) == Decimal("10.0")

    def test_no_logbook_is_no_data_not_zero(self, world):  # noqa: F811
        assert AircraftLogbook.hours_for(world["a"]["aircraft"]) is None


@pytest.mark.django_db
class TestCompletingALevelOpensTheNext:
    @pytest.fixture(autouse=True)
    def programmes(self, db):
        _program("basic", 200, 6)
        _program("medium", 400, 12)
        _program("advanced", 600, 18)
        self.aircraft = _aircraft()
        self.client = login_as(
            "view_maintenancerecord", "change_maintenancerecord", "view_aircraft"
        )

    def _complete(self, level, day="2026-03-10", hours="1000"):
        record = MaintenanceRecord.objects.create(
            aircraft=self.aircraft,
            maintenance_type="scheduled",
            description="work",
            status="in_progress",
        )
        response = self.client.post(
            reverse("maintenance-complete", args=[record.pk]),
            {
                "completed_date": day,
                "performed_by": "Authorised workshop",
                "level": level,
                "hours_at": hours,
                "certificate_number": "CE-1",
                "notes": "",
            },
        )
        assert response.status_code == 302
        record.refresh_from_db()
        return record

    def _open(self, level):
        return list(
            MaintenanceRecord.objects.filter(
                aircraft=self.aircraft, level=level, is_active=True
            ).exclude(status="completed")
        )

    def test_the_form_stores_level_hours_and_certificate(self):
        record = self._complete("basic")
        assert record.level == "basic"
        assert record.hours_at == Decimal("1000.0")
        assert record.certificate_number == "CE-1"

    def test_completing_basic_schedules_the_next_basic_six_months_later(self):
        self._complete("basic")

        (follow_up,) = self._open("basic")
        assert follow_up.status == "pending"
        assert follow_up.maintenance_type == "scheduled"
        assert follow_up.scheduled_date == D(2026, 9, 10)
        assert self._open("medium") == [] and self._open("advanced") == []

    def test_completing_twice_does_not_duplicate_the_open_one(self):
        self._complete("basic")
        self._complete("basic", day="2026-03-11")

        assert len(self._open("basic")) == 1

    def test_advanced_restarts_the_lower_levels_open_records(self):
        stale = MaintenanceRecord.objects.create(
            aircraft=self.aircraft,
            maintenance_type="scheduled",
            description="old plan",
            level="basic",
            status="pending",
            scheduled_date=D(2026, 4, 1),
        )

        self._complete("advanced")

        stale.refresh_from_db()
        assert stale.scheduled_date == D(2026, 9, 10)
        assert len(self._open("basic")) == 1
        (medium,) = self._open("medium")
        assert medium.scheduled_date == D(2027, 3, 10)
        (advanced,) = self._open("advanced")
        assert advanced.scheduled_date == D(2027, 9, 10)

    def test_a_later_open_lower_record_is_left_alone(self):
        later = MaintenanceRecord.objects.create(
            aircraft=self.aircraft,
            maintenance_type="scheduled",
            description="planned later",
            level="basic",
            status="pending",
            scheduled_date=D(2027, 1, 1),
        )

        self._complete("medium")

        later.refresh_from_db()
        assert later.scheduled_date == D(2027, 1, 1)

    def test_repair_opens_nothing(self):
        self._complete("repair")
        assert MaintenanceRecord.objects.filter(status="pending").count() == 0

    def test_a_record_without_level_opens_nothing(self):
        self._complete("")
        assert MaintenanceRecord.objects.filter(status="pending").count() == 0

    def test_hours_only_programme_opens_no_dated_record(self):
        MaintenanceProgram.objects.all().delete()
        _program("basic", 200, None)

        self._complete("basic")

        assert self._open("basic") == []

    def test_the_followup_is_picked_up_by_the_existing_alert_rule(self):
        """«Mantenimiento programado» (scheduled_date, 15 días) avisa sin motor nuevo."""
        AlertRule.objects.create(
            name="Mantenimiento programado",
            entity_type="maintenance.maintenancerecord",
            field_to_watch="scheduled_date",
            days_before_expiry=15,
        )
        today = timezone.localdate()
        # Month arithmetic clamps at month ends, so the date drifts a few days:
        # all that matters is that it lands inside the rule's 15-day window.
        done = add_months(today + datetime.timedelta(5), -6)
        self._complete("basic", day=str(done))

        call_command("generate_alerts")

        (follow_up,) = self._open("basic")
        assert follow_up.scheduled_date == add_months(done, 6)
        assert 0 <= (follow_up.scheduled_date - today).days <= 8
        assert Alert.objects.filter(object_id=follow_up.pk).exists()


@pytest.mark.django_db
class TestProgramme:
    def test_it_needs_at_least_one_interval(self):
        with pytest.raises(IntegrityError), transaction.atomic():
            MaintenanceProgram.objects.create(name="Empty", level="basic")

    def test_name_and_level_are_unique(self):
        _program("basic", 200, 6)
        with pytest.raises(IntegrityError), transaction.atomic():
            _program("basic", 100, 3)

    def test_the_one_that_names_the_model_beats_the_general_one(self):
        _program("basic", 100, 3, keywords="", name="General")
        specific = _program("basic", 200, 6, keywords="zeta", name="Zeta")

        assert MaintenanceProgram.for_aircraft(_aircraft())["basic"] == specific
        other = _aircraft(model="Other", registration="CC-OTH")
        assert MaintenanceProgram.for_aircraft(other)["basic"].name == "General"

    def test_a_non_matching_model_gets_no_programme(self):
        _program("basic", 200, 6)
        assert MaintenanceProgram.for_aircraft(_aircraft(model="Other")) == {}


@pytest.mark.django_db
class TestSeededProgramme:
    """Sembrado por la migración 0014 con lo que el Anexo F dice con número."""

    def _for(self, model):
        return MaintenanceProgram.for_aircraft(_aircraft(model=model))

    @pytest.mark.parametrize(
        "model", ["Matrice 300 RTK", "Mavic 3 Enterprise", "Matrice 4 Thermal"]
    )
    def test_dji_models_get_the_three_levels(self, model):
        programs = self._for(model)
        assert {
            level: (p.interval_hours, p.interval_months)
            for level, p in programs.items()
        } == {"basic": (200, 6), "medium": (400, 12), "advanced": (600, 18)}

    @pytest.mark.parametrize("model", ["Elios 3", "Wingtra One Gen2"])
    def test_manufacturer_models_are_months_only_and_only_the_basic_review(self, model):
        programs = self._for(model)
        assert list(programs) == ["basic"]
        assert programs["basic"].interval_hours is None
        assert programs["basic"].interval_months == 12

    def test_seeding_is_idempotent_by_name_and_level(self):
        import importlib

        migration = importlib.import_module(
            "apps.maintenance.migrations.0014_seed_maintenance_programs"
        )
        before = MaintenanceProgram.objects.count()
        from django.apps import apps

        migration.seed_programs(apps, None)

        assert MaintenanceProgram.objects.count() == before == 5


# --- The REG-020 sheet: permissions and tenant ---------------------------------------


def _sheet_client(world, *extra, tenant="a"):  # noqa: F811
    return login_as(
        "view_maintenancerecord",
        "view_aircraft",
        *extra,
        member_of=world[tenant]["tenant"],
    )


@pytest.mark.django_db
class TestServiceLifeSheet:
    def test_it_renders_hours_levels_and_history(self, world):  # noqa: F811
        aircraft = world["a"]["aircraft"]
        aircraft.model = "Zeta 1"
        aircraft.save()
        _program("basic", 200, 6)
        _logbook(aircraft, "1000")
        _done(
            aircraft, "basic", D(2026, 1, 10), Decimal("1000"), certificate_number="C-9"
        )

        response = _sheet_client(world).get(
            reverse("aircraft-service-life", args=[aircraft.pk])
        )

        assert response.status_code == 200
        html = response.content.decode()
        assert 'data-level="basic"' in html
        assert "C-9" in html
        assert re.search(r"1000[.,]0 h", html)
        assert response.context["levels"][0].due_hours == Decimal("1200")

    def test_it_needs_view_maintenancerecord(self, world):  # noqa: F811
        client = login_as("view_aircraft", member_of=world["a"]["tenant"])
        url = reverse("aircraft-service-life", args=[world["a"]["aircraft"].pk])
        assert client.get(url).status_code == 403

    def test_it_needs_view_aircraft(self, world):  # noqa: F811
        client = login_as("view_maintenancerecord", member_of=world["a"]["tenant"])
        url = reverse("aircraft-service-life", args=[world["a"]["aircraft"].pk])
        assert client.get(url).status_code == 403

    def test_another_tenants_aircraft_is_a_404(self, world):  # noqa: F811
        url = reverse("aircraft-service-life", args=[world["b"]["aircraft"].pk])
        assert _sheet_client(world).get(url).status_code == 404

    def test_the_pdf_needs_both_permissions_and_the_tenant(self, world):  # noqa: F811
        own = reverse("aircraft-service-life-pdf", args=[world["a"]["aircraft"].pk])
        other = reverse("aircraft-service-life-pdf", args=[world["b"]["aircraft"].pk])
        assert (
            login_as("view_aircraft", member_of=world["a"]["tenant"])
            .get(own)
            .status_code
            == 403
        )
        assert (
            login_as("view_maintenancerecord", member_of=world["a"]["tenant"])
            .get(own)
            .status_code
            == 403
        )
        client = _sheet_client(world)
        assert client.get(other).status_code == 404
        response = client.get(own)
        assert response.status_code == 200
        assert response["Content-Type"] == "application/pdf"
        assert response.content.startswith(b"%PDF")

    def test_the_pdf_prints_with_levels_and_history(self, world):  # noqa: F811
        aircraft = world["a"]["aircraft"]
        aircraft.model = "Zeta 1"
        aircraft.save()
        _program("basic", 200, 6)
        _logbook(aircraft, "1000")
        _done(aircraft, "basic", D(2026, 1, 10), Decimal("1000"))

        response = _sheet_client(world).get(
            reverse("aircraft-service-life-pdf", args=[aircraft.pk])
        )

        assert response.status_code == 200 and response.content.startswith(b"%PDF")

    def test_the_documents_section_hides_without_view_document(self, world):  # noqa: F811
        url = reverse("aircraft-service-life", args=[world["a"]["aircraft"].pk])
        response = _sheet_client(world).get(url)
        assert response.context["documents"] is None


@pytest.mark.django_db
class TestLogbookEdit:
    def _url(self, aircraft):
        return reverse("aircraft-logbook", args=[aircraft.pk])

    def test_it_needs_change_aircraftlogbook(self, world):  # noqa: F811
        aircraft = world["a"]["aircraft"]
        client = login_as("view_aircraftlogbook", member_of=world["a"]["tenant"])
        assert client.get(self._url(aircraft)).status_code == 403
        assert (
            client.post(self._url(aircraft), {"hours_baseline": "5"}).status_code == 403
        )
        assert not AircraftLogbook.objects.exists()

    def test_another_tenants_aircraft_is_a_404_and_stays_untouched(self, world):  # noqa: F811
        client = login_as("change_aircraftlogbook", member_of=world["a"]["tenant"])
        response = client.post(
            self._url(world["b"]["aircraft"]),
            {"hours_baseline": "5", "baseline_on": "2026-05-01"},
        )
        assert response.status_code == 404
        assert not AircraftLogbook.objects.exists()

    def test_a_get_does_not_create_the_logbook(self, world):  # noqa: F811
        client = login_as("change_aircraftlogbook", member_of=world["a"]["tenant"])
        assert client.get(self._url(world["a"]["aircraft"])).status_code == 200
        assert not AircraftLogbook.objects.exists()

    def test_saving_creates_then_updates_one_logbook(self, world):  # noqa: F811
        aircraft = world["a"]["aircraft"]
        client = login_as("change_aircraftlogbook", member_of=world["a"]["tenant"])

        client.post(
            self._url(aircraft),
            {"hours_baseline": "120.5", "baseline_on": "2026-05-01"},
        )
        client.post(
            self._url(aircraft), {"hours_baseline": "130", "baseline_on": "2026-06-01"}
        )

        logbook = AircraftLogbook.objects.get(aircraft=aircraft)
        assert logbook.hours_baseline == Decimal("130.0")
        assert logbook.baseline_on == D(2026, 6, 1)

    def test_baseline_hours_need_their_date(self, world):  # noqa: F811
        client = login_as("change_aircraftlogbook", member_of=world["a"]["tenant"])
        response = client.post(
            self._url(world["a"]["aircraft"]), {"hours_baseline": "120"}
        )
        assert response.status_code == 200
        assert "baseline_on" in response.context["form"].errors
        assert not AircraftLogbook.objects.exists()


@pytest.mark.django_db
def test_overdue_by_level_counts_aircraft_per_level():
    """Lo que el informe toma para «vencidas por nivel»."""
    _program("basic", 200, 6)
    _program("medium", 400, 12)
    late, fine = _aircraft(registration="CC-LATE"), _aircraft(registration="CC-FINE")
    _done(late, "basic", D(2026, 1, 10))
    _done(fine, "basic", D(2026, 6, 1))
    _done(fine, "medium", D(2026, 6, 1))
    _done(late, "medium", D(2025, 1, 1))

    counts = levels.overdue_by_level(
        Aircraft.objects.filter(pk__in=[late.pk, fine.pk]), today=D(2026, 8, 1)
    )

    assert counts == {"basic": 1, "medium": 1, "advanced": 0}
