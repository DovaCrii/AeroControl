"""LV-30: operational records repository + monthly compliance review."""

from datetime import date, time

import pytest
from django.contrib.auth.models import Group, User
from django.contrib.contenttypes.models import ContentType
from django.core import mail
from django.core.management import call_command
from django.test import Client
from django.urls import reverse

from apps.compliance.models import (
    Alert,
    Document,
    DocumentType,
    MonthlyComplianceReview,
)
from apps.core.groups import REPORT_RECIPIENTS
from apps.operations.models import FlightPermission, FlightRecord
from apps.registry.models import Aircraft, CostCenter, Operator

PERIOD = date(2026, 5, 1)


@pytest.fixture
def world(db):
    cc = CostCenter.objects.create(code="CC1", name="Flew this month")
    operator = Operator.objects.create(
        employee_id="OP-1", full_name="Pilot One", cost_center=cc
    )
    aircraft = Aircraft.objects.create(
        registration="RPA-1",
        type="RPAS",
        model="M300",
        manufacturer="DJI",
        cost_center=cc,
    )
    return cc, operator, aircraft


def _flew(cc, operator, aircraft, when):
    permission = FlightPermission.objects.create(
        permission_number=f"P-{when:%Y%m%d}",
        cost_center=cc,
        purpose="Survey",
        valid_from=when,
        valid_until=when,
        location="Site",
    )
    return FlightRecord.objects.create(
        permission=permission,
        actual_date=when,
        departure_time=time(9, 0),
        arrival_time=time(10, 0),
        pilot=operator,
        aircraft=aircraft,
    )


def _op_record(cc, when, code="flight-log"):
    doc_type, _ = DocumentType.objects.get_or_create(
        code=code, defaults={"name": code, "is_operational_record": True}
    )
    return Document.objects.create(
        title=f"Record {when}",
        doc_type=doc_type,
        content_type=ContentType.objects.get_for_model(CostCenter),
        object_id=cc.pk,
        file_path=f"rec/{when}.pdf",
        issue_date=when,
    )


def _admin_client():
    User.objects.create_superuser("admin", "admin@x.cl", "pw")
    client = Client()
    assert client.login(username="admin", password="pw")
    return client


# ── Operational-records repository ────────────────────────────────────────────


@pytest.mark.django_db
def test_operational_records_page_lists_and_filters(world):
    cc, _operator, _aircraft = world
    other = CostCenter.objects.create(code="CC2", name="Other")
    _op_record(cc, date(2026, 5, 10))
    _op_record(other, date(2026, 5, 11))
    _op_record(cc, date(2026, 4, 9))
    client = _admin_client()

    # Unfiltered: all three operational records show.
    response = client.get(reverse("operational-records"))
    assert response.status_code == 200
    assert len(response.context["documents"]) == 3

    # By cost center.
    response = client.get(reverse("operational-records"), {"cost_center": cc.pk})
    assert len(response.context["documents"]) == 2

    # By month (CC filter + May).
    response = client.get(
        reverse("operational-records"), {"cost_center": cc.pk, "month": "2026-05"}
    )
    assert len(response.context["documents"]) == 1


@pytest.mark.django_db
def test_operational_records_excludes_non_operational_documents(world):
    cc, _operator, _aircraft = world
    ordinary = DocumentType.objects.create(code="aoc", name="AOC")
    Document.objects.create(
        title="Company AOC",
        doc_type=ordinary,
        content_type=ContentType.objects.get_for_model(CostCenter),
        object_id=cc.pk,
        file_path="aoc.pdf",
        issue_date=date(2026, 5, 1),
    )
    client = _admin_client()

    response = client.get(reverse("operational-records"))
    assert list(response.context["documents"]) == []


# ── MonthlyComplianceReview + alert lifecycle ────────────────────────────────


@pytest.mark.django_db
def test_pending_review_alerts_and_marking_resolves_it(world):
    cc, _operator, _aircraft = world
    call_command("seed_alert_rules", "--with-optional")
    review = MonthlyComplianceReview.objects.create(cost_center=cc, period=PERIOD)

    call_command("generate_alerts")
    review_ct = ContentType.objects.get_for_model(MonthlyComplianceReview)
    alert = Alert.objects.get(content_type=review_ct, object_id=review.pk)
    assert alert.is_resolved is False

    user = User.objects.create_user("dir", password="pw")
    review.mark(MonthlyComplianceReview.STATUS_COMPLETED, user)

    alert.refresh_from_db()
    assert alert.is_resolved is True
    review.refresh_from_db()
    assert review.reviewed_by == user
    assert review.reviewed_at is not None


@pytest.mark.django_db
def test_generate_alerts_treats_non_compliant_as_terminal(world):
    cc, _operator, _aircraft = world
    call_command("seed_alert_rules", "--with-optional")
    MonthlyComplianceReview.objects.create(
        cost_center=cc,
        period=PERIOD,
        status=MonthlyComplianceReview.STATUS_NON_COMPLIANT,
    )

    call_command("generate_alerts")

    review_ct = ContentType.objects.get_for_model(MonthlyComplianceReview)
    assert not Alert.objects.filter(content_type=review_ct).exists()


# ── check_monthly_records command ────────────────────────────────────────────


@pytest.mark.django_db
def test_check_monthly_records_creates_reviews_for_flown_cost_centers(world):
    cc, operator, aircraft = world
    idle = CostCenter.objects.create(code="CC3", name="Did not fly")
    _flew(cc, operator, aircraft, date(2026, 5, 15))

    call_command("check_monthly_records", "--period", "2026-05")

    reviews = MonthlyComplianceReview.objects.all()
    assert reviews.count() == 1
    review = reviews.get()
    assert review.cost_center == cc
    assert review.period == PERIOD
    assert review.status == MonthlyComplianceReview.STATUS_PENDING
    assert not MonthlyComplianceReview.objects.filter(cost_center=idle).exists()


@pytest.mark.django_db
def test_check_monthly_records_is_idempotent_and_dry_run_writes_nothing(world):
    cc, operator, aircraft = world
    _flew(cc, operator, aircraft, date(2026, 5, 15))

    call_command("check_monthly_records", "--period", "2026-05", "--dry-run")
    assert MonthlyComplianceReview.objects.count() == 0

    call_command("check_monthly_records", "--period", "2026-05")
    call_command("check_monthly_records", "--period", "2026-05")
    assert MonthlyComplianceReview.objects.count() == 1


@pytest.mark.django_db
def test_check_monthly_records_emails_direccion(world):
    cc, operator, aircraft = world
    _flew(cc, operator, aircraft, date(2026, 5, 15))
    reviewer = User.objects.create_user("dir", email="dir@x.cl", password="pw")
    Group.objects.create(name=REPORT_RECIPIENTS).user_set.add(reviewer)

    call_command("check_monthly_records", "--period", "2026-05")

    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["dir@x.cl"]
    assert cc.code in mail.outbox[0].body


# ── check_monthly_review_deadline command (R6.5) ─────────────────────────────


@pytest.mark.django_db
def test_deadline_check_escalates_a_still_pending_review(world):
    cc, _operator, _aircraft = world
    MonthlyComplianceReview.objects.create(cost_center=cc, period=PERIOD)
    reviewer = User.objects.create_user("dir", email="dir@x.cl", password="pw")
    Group.objects.create(name=REPORT_RECIPIENTS).user_set.add(reviewer)

    call_command("check_monthly_review_deadline", "--period", "2026-05")

    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["dir@x.cl"]
    assert cc.code in mail.outbox[0].body


@pytest.mark.django_db
def test_deadline_check_never_creates_or_changes_a_review(world):
    """This command only reports; check_monthly_records owns creating and
    updating MonthlyComplianceReview rows."""
    cc, _operator, _aircraft = world
    review = MonthlyComplianceReview.objects.create(cost_center=cc, period=PERIOD)

    call_command("check_monthly_review_deadline", "--period", "2026-05", "--dry-run")

    assert MonthlyComplianceReview.objects.count() == 1
    review.refresh_from_db()
    assert review.status == MonthlyComplianceReview.STATUS_PENDING


@pytest.mark.django_db
def test_deadline_check_sends_nothing_when_nothing_is_pending(world):
    cc, _operator, _aircraft = world
    MonthlyComplianceReview.objects.create(
        cost_center=cc,
        period=PERIOD,
        status=MonthlyComplianceReview.STATUS_COMPLETED,
    )
    Group.objects.create(name=REPORT_RECIPIENTS).user_set.add(
        User.objects.create_user("dir", email="dir@x.cl", password="pw")
    )

    call_command("check_monthly_review_deadline", "--period", "2026-05")

    assert mail.outbox == []


@pytest.mark.django_db
def test_deadline_check_reports_but_does_not_mail_without_recipients(world):
    cc, _operator, _aircraft = world
    MonthlyComplianceReview.objects.create(cost_center=cc, period=PERIOD)

    call_command("check_monthly_review_deadline", "--period", "2026-05")

    assert mail.outbox == []


@pytest.mark.django_db
def test_deadline_check_only_acts_on_the_15th_unless_forced(world):
    cc, _operator, _aircraft = world
    MonthlyComplianceReview.objects.create(cost_center=cc, period=PERIOD)
    Group.objects.create(name=REPORT_RECIPIENTS).user_set.add(
        User.objects.create_user("dir", email="dir@x.cl", password="pw")
    )

    call_command("check_monthly_review_deadline")  # no --period, no --force

    assert mail.outbox == []


# ── Monthly-review page ──────────────────────────────────────────────────────


@pytest.mark.django_db
def test_monthly_review_page_shows_counts_and_marks(world):
    cc, operator, aircraft = world
    _flew(cc, operator, aircraft, date(2026, 5, 15))
    _op_record(cc, date(2026, 5, 16))
    review = MonthlyComplianceReview.objects.create(cost_center=cc, period=PERIOD)
    client = _admin_client()

    response = client.get(reverse("monthly-review"))
    assert response.status_code == 200
    row = response.context["reviews"][0]
    assert row.flights == 1
    assert row.records == 1

    marked = client.post(
        reverse("monthly-review-mark", args=[review.pk]),
        {"status": "non_compliant", "notes": "missing checklist"},
    )
    assert marked.status_code == 302
    review.refresh_from_db()
    assert review.status == MonthlyComplianceReview.STATUS_NON_COMPLIANT
    assert review.notes == "missing checklist"


@pytest.mark.django_db
def test_monthly_review_mark_requires_change_permission(world):
    cc, _operator, _aircraft = world
    review = MonthlyComplianceReview.objects.create(cost_center=cc, period=PERIOD)
    User.objects.create_user("plain", password="pw")
    client = Client()
    assert client.login(username="plain", password="pw")

    response = client.post(
        reverse("monthly-review-mark", args=[review.pk]), {"status": "completed"}
    )
    assert response.status_code in (302, 403)
    review.refresh_from_db()
    assert review.status == MonthlyComplianceReview.STATUS_PENDING


@pytest.mark.django_db
def test_monthly_review_csv_export(world):
    cc, _operator, _aircraft = world
    MonthlyComplianceReview.objects.create(cost_center=cc, period=PERIOD)
    client = _admin_client()

    response = client.get(reverse("monthly-review"), {"export": "csv"})

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/csv")
    body = response.content.decode()
    assert "cost_center" in body
    assert cc.code in body
