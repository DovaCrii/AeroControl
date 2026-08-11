"""R7.7 (ISO 9.1.1): stored history so the report's trend is real.

`build_compliance_report` evaluates valid/expired/due_* always "as of today"
regardless of the period asked for, so comparing period against period could
only ever read "no change" on those counters -- the finding R6.4 documented and
left open. `ComplianceSnapshot` plus the `snapshot_compliance` command store the
totals per day so the comparison has something real to compare against.
"""

from datetime import date, timedelta

import pytest
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.utils import IntegrityError
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.core.models import JobRun
from apps.registry.models import Aircraft, CostCenter
from .models import ComplianceSnapshot, Document, DocumentType
from .reports import latest_snapshot_before, totals_from_snapshot

TODAY = timezone.localdate()


@pytest.fixture
def world(db):
    """One cost center with 3 documents: 1 expired, 1 due soon, 1 permanent."""
    cost_center = CostCenter.objects.create(code="FAENA-01", name="Faena Norte")
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Multirotor",
        model="M300",
        manufacturer="DJI",
        cost_center=cost_center,
    )
    doc_type = DocumentType.objects.create(code="SEG", name="Seguro")
    aircraft_ct = ContentType.objects.get_for_model(Aircraft)

    def document(title, offset):
        Document.objects.create(
            title=title,
            doc_type=doc_type,
            content_type=aircraft_ct,
            object_id=aircraft.pk,
            file_path=f"seg/{title}.pdf",
            issue_date=date(2026, 1, 1),
            expiry_date=None if offset is None else TODAY + timedelta(days=offset),
        )

    document("expired", -5)
    document("due-soon", 3)
    document("permanent", None)
    return {"cost_center": cost_center, "doc_type": doc_type}


def _admin_client():
    User.objects.create_superuser("admin", "a@test.com", "password")
    client = Client()
    assert client.login(username="admin", password="password")
    return client


class TestSnapshotCommand:
    @pytest.mark.django_db
    def test_writes_one_row_per_cost_center_plus_a_consolidated_one(self, world):
        call_command("snapshot_compliance")

        rows = ComplianceSnapshot.objects.filter(date=TODAY)
        assert rows.count() == 2  # FAENA-01 + the consolidated row
        per_cc = rows.get(cost_center=world["cost_center"])
        consolidated = rows.get(cost_center__isnull=True)
        assert per_cc.total == 3
        assert per_cc.expired == 1
        assert per_cc.due_7 == 1
        assert consolidated.total == 3

    @pytest.mark.django_db
    def test_numbers_match_the_report_they_are_the_history_of(self, world):
        """The command reads build_compliance_report on purpose: a snapshot that
        disagreed with the report would be worse than no snapshot."""
        from .reports import build_compliance_report

        report = build_compliance_report()
        call_command("snapshot_compliance")

        consolidated = ComplianceSnapshot.objects.get(
            date=TODAY, cost_center__isnull=True
        )
        assert consolidated.total == report["totals"]["total"]
        assert consolidated.valid == report["totals"]["valid"]
        assert consolidated.expired == report["totals"]["expired"]
        assert consolidated.valid_pct == report["totals"]["valid_pct"]

    @pytest.mark.django_db
    def test_rerunning_the_same_date_overwrites_instead_of_duplicating(self, world):
        """A job that fires twice must not corrupt a trend."""
        call_command("snapshot_compliance")
        call_command("snapshot_compliance")

        assert ComplianceSnapshot.objects.filter(date=TODAY).count() == 2

    @pytest.mark.django_db
    def test_dry_run_writes_nothing(self, world):
        call_command("snapshot_compliance", "--dry-run")

        assert ComplianceSnapshot.objects.count() == 0

    @pytest.mark.django_db
    def test_backfills_a_specific_date(self, world):
        call_command("snapshot_compliance", "--date", "2026-07-01")

        assert ComplianceSnapshot.objects.filter(date=date(2026, 7, 1)).exists()
        assert not ComplianceSnapshot.objects.filter(date=TODAY).exists()

    @pytest.mark.django_db
    def test_rejects_a_malformed_date(self, world):
        with pytest.raises(CommandError, match="YYYY-MM-DD"):
            call_command("snapshot_compliance", "--date", "01-07-2026")

    @pytest.mark.django_db
    def test_records_a_job_run(self, world):
        call_command("snapshot_compliance")

        assert JobRun.objects.get(command="snapshot_compliance").result == (
            JobRun.RESULT_OK
        )


class TestSnapshotConstraints:
    @pytest.mark.django_db
    def test_the_consolidated_row_cannot_be_stored_twice_for_one_date(self, world):
        """Two constraints are needed, not one: SQLite and Postgres both treat
        NULLs as distinct in a unique index, so a single constraint over
        (tenant, date, cost_center) would let the consolidated row duplicate."""
        ComplianceSnapshot.objects.create(date=TODAY, cost_center=None, total=1)

        with pytest.raises(IntegrityError):
            ComplianceSnapshot.objects.create(date=TODAY, cost_center=None, total=2)

    @pytest.mark.django_db
    def test_a_cost_center_cannot_be_stored_twice_for_one_date(self, world):
        ComplianceSnapshot.objects.create(
            date=TODAY, cost_center=world["cost_center"], total=1
        )

        with pytest.raises(IntegrityError):
            ComplianceSnapshot.objects.create(
                date=TODAY, cost_center=world["cost_center"], total=2
            )

    @pytest.mark.django_db
    def test_valid_pct_is_computed_not_stored(self, world):
        snapshot = ComplianceSnapshot.objects.create(
            date=TODAY, cost_center=None, total=4, valid=3
        )

        assert snapshot.valid_pct == 75.0
        # And does not divide by zero on an empty tenant.
        empty = ComplianceSnapshot.objects.create(
            date=TODAY - timedelta(days=1), cost_center=None, total=0, valid=0
        )
        assert empty.valid_pct == 0.0


class TestLatestSnapshotBefore:
    @pytest.mark.django_db
    def test_returns_none_when_no_history_exists(self, world):
        assert latest_snapshot_before(TODAY) is None

    @pytest.mark.django_db
    def test_returns_the_most_recent_strictly_before_the_date(self, world):
        older = ComplianceSnapshot.objects.create(
            date=TODAY - timedelta(days=10), cost_center=None, total=1
        )
        newer = ComplianceSnapshot.objects.create(
            date=TODAY - timedelta(days=2), cost_center=None, total=2
        )
        # Same-day must NOT count: comparing today against today is the very
        # thing this table exists to avoid.
        ComplianceSnapshot.objects.create(date=TODAY, cost_center=None, total=3)

        assert latest_snapshot_before(TODAY) == newer
        assert latest_snapshot_before(newer.date) == older

    @pytest.mark.django_db
    def test_scopes_to_the_requested_cost_center(self, world):
        consolidated = ComplianceSnapshot.objects.create(
            date=TODAY - timedelta(days=1), cost_center=None, total=99
        )
        per_cc = ComplianceSnapshot.objects.create(
            date=TODAY - timedelta(days=1),
            cost_center=world["cost_center"],
            total=3,
        )

        assert latest_snapshot_before(TODAY) == consolidated
        assert latest_snapshot_before(TODAY, cost_center=world["cost_center"]) == per_cc

    @pytest.mark.django_db
    def test_totals_from_snapshot_matches_the_report_totals_shape(self, world):
        snapshot = ComplianceSnapshot.objects.create(
            date=TODAY, cost_center=None, total=10, valid=8, expired=2, due_30=1
        )

        totals = totals_from_snapshot(snapshot)

        # Same keys compare_periods reads off report["totals"].
        assert set(totals) >= {"total", "valid", "expired", "due_30", "valid_pct"}
        assert totals["valid_pct"] == 80.0


class TestReportUsesTheSnapshotAsBaseline:
    @pytest.mark.django_db
    def test_without_history_the_comparison_degrades_instead_of_failing(self, world):
        """Day one has no snapshots; that is normal, not an error."""
        response = _admin_client().get(reverse("compliance-report"))

        assert response.status_code == 200
        assert response.context["comparison_baseline"] is None
        # The documentary rows read flat, which is the pre-R7.7 behaviour.
        assert all(row["delta"] == 0 for row in response.context["comparison"][:3])

    @pytest.mark.django_db
    def test_a_stored_snapshot_becomes_the_baseline_and_the_trend_moves(self, world):
        """The whole point: with history, the counters can finally differ."""
        start = TODAY - timedelta(days=30)
        baseline = ComplianceSnapshot.objects.create(
            date=start - timedelta(days=1),
            cost_center=None,
            total=3,
            valid=1,
            expired=2,
        )

        response = _admin_client().get(reverse("compliance-report"))

        assert response.context["comparison_baseline"] == baseline
        valid_pct_row = response.context["comparison"][0]
        # Today is 2 valid of 3 (66.7%); the baseline was 1 of 3 (33.3%).
        assert valid_pct_row["previous"] == pytest.approx(33.3)
        assert valid_pct_row["delta"] != 0
        assert valid_pct_row["direction"] == "better"

    @pytest.mark.django_db
    def test_a_doc_type_filter_ignores_the_snapshot(self, world):
        """Snapshots are unfiltered; comparing a type-filtered view against one
        would be apples to oranges."""
        ComplianceSnapshot.objects.create(
            date=TODAY - timedelta(days=40), cost_center=None, total=99, valid=1
        )

        response = _admin_client().get(
            reverse("compliance-report"), {"doc_type": world["doc_type"].pk}
        )

        assert response.context["comparison_baseline"] is None

    @pytest.mark.django_db
    def test_the_baseline_follows_the_cost_center_filter(self, world):
        start = TODAY - timedelta(days=30)
        ComplianceSnapshot.objects.create(
            date=start - timedelta(days=1), cost_center=None, total=99, valid=1
        )
        per_cc = ComplianceSnapshot.objects.create(
            date=start - timedelta(days=1),
            cost_center=world["cost_center"],
            total=3,
            valid=1,
        )

        response = _admin_client().get(
            reverse("compliance-report"),
            {"cost_center": world["cost_center"].pk},
        )

        assert response.context["comparison_baseline"] == per_cc

    @pytest.mark.django_db
    def test_the_pdf_export_still_works_with_a_snapshot_present(self, world):
        """report_and_comparison_for grew a third return value; the PDF view is
        its other caller."""
        ComplianceSnapshot.objects.create(
            date=TODAY - timedelta(days=40), cost_center=None, total=3, valid=1
        )

        response = _admin_client().get(reverse("compliance-report-pdf"))

        assert response.status_code == 200
        assert response.content.startswith(b"%PDF-")
