from datetime import date, timedelta

import pytest
from django.contrib.auth.models import Group, User
from django.contrib.contenttypes.models import ContentType
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.core.exports import neutralize
from apps.core.models import JobRun
from apps.registry.models import Aircraft, CostCenter, Operator
from .models import Alert, AlertRule, Document, DocumentType
from .reports import build_compliance_report

# The report's period is bound in the project timezone, so the fixtures must be
# too: with a naive date these tests fail whenever the OS date and the project
# date differ, which is a real four-hour window every evening under UTC.
TODAY = timezone.localdate()


@pytest.fixture
def world(db):
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
        return Document.objects.create(
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
    document("due-mid", 12)
    document("due-late", 25)
    document("no-expiry", None)
    return {"cost_center": cost_center, "doc_type": doc_type, "aircraft": aircraft}


@pytest.mark.django_db
def test_report_counts_documents_by_urgency(world):
    report = build_compliance_report()

    totals = report["totals"]
    assert totals["total"] == 5
    assert totals["expired"] == 1
    assert totals["due_7"] == 1
    assert totals["due_15"] == 1
    assert totals["due_30"] == 1
    # A document with no expiry date is permanently valid, not missing data
    assert totals["valid"] == 4
    assert totals["valid_pct"] == 80.0


@pytest.mark.django_db
def test_report_can_be_filtered_by_document_type(world):
    other_type = DocumentType.objects.create(code="LIC", name="Licencia")

    report = build_compliance_report(doc_type=other_type)

    assert report["totals"]["total"] == 0


@pytest.mark.django_db
def test_report_includes_vigencias_alongside_documents(world):
    """LV-49: DGAC vigencias already drive real alerts (LV-29) but were never
    reflected in this report, which read 0/0.0% even with open vigencia alerts."""
    world["aircraft"].insurance_expiry = TODAY + timedelta(days=3)
    world["aircraft"].save(update_fields=["insurance_expiry"])
    Operator.objects.create(
        employee_id="OP-1",
        full_name="Pilot One",
        cost_center=world["cost_center"],
        credential_expiry=TODAY - timedelta(days=1),
    )

    report = build_compliance_report()

    totals = report["totals"]
    # 5 documents (world fixture) + 2 vigencias (1 due_7, 1 expired)
    assert totals["total"] == 7
    assert totals["expired"] == 2
    assert totals["due_7"] == 2


@pytest.mark.django_db
def test_report_excludes_vigencias_when_filtered_by_document_type(world):
    """Vigencias have no doc_type -- filtering by one should not silently
    pull them back into a narrower view than the filter implies."""
    world["aircraft"].insurance_expiry = TODAY + timedelta(days=3)
    world["aircraft"].save(update_fields=["insurance_expiry"])

    report = build_compliance_report(doc_type=world["doc_type"])

    assert report["totals"]["total"] == 5


@pytest.mark.django_db
def test_report_does_not_count_an_unset_vigencia_as_valid(world):
    """Unlike Document.expiry_date (null = never expires, counts as valid),
    a null vigencia means the value was never entered -- it should not count
    at all, matching what generate_alerts already does with these fields."""
    assert world["aircraft"].insurance_expiry is None

    report = build_compliance_report()

    # Same 5 as the plain document count -- the aircraft's unset vigencia adds nothing
    assert report["totals"]["total"] == 5


@pytest.mark.django_db
def test_report_ignores_documents_of_other_cost_centers(world):
    other_cc = CostCenter.objects.create(code="OTRA", name="Otra faena")
    other_aircraft = Aircraft.objects.create(
        registration="CC-ZZZ",
        type="Multirotor",
        model="M300",
        manufacturer="DJI",
        cost_center=other_cc,
    )
    Document.objects.create(
        title="ajeno",
        doc_type=world["doc_type"],
        content_type=ContentType.objects.get_for_model(Aircraft),
        object_id=other_aircraft.pk,
        file_path="seg/ajeno.pdf",
        issue_date=date(2026, 1, 1),
        expiry_date=TODAY + timedelta(days=3),
    )

    report = build_compliance_report(cost_center=world["cost_center"])

    assert report["totals"]["total"] == 5


@pytest.mark.django_db
def test_report_averages_alert_resolution_time(world):
    rule = AlertRule.objects.create(
        name="Docs", entity_type="compliance.document", field_to_watch="expiry_date"
    )
    document = Document.objects.first()
    alert = Alert.objects.create(
        alert_rule=rule,
        content_type=ContentType.objects.get_for_model(Document),
        object_id=document.pk,
        message="test",
    )
    # Resolved four days after being triggered
    Alert.objects.filter(pk=alert.pk).update(
        triggered_at=timezone.now() - timedelta(days=4),
        resolved_at=timezone.now(),
        is_resolved=True,
    )

    report = build_compliance_report()

    assert report["resolution"]["resolved_count"] == 1
    assert report["resolution"]["avg_days"] == pytest.approx(4.0, abs=0.2)


def test_neutralize_defuses_spreadsheet_formulas():
    assert neutralize("=SUM(A1:A9)").startswith("'")
    assert neutralize("+1") == "'+1"
    assert neutralize("-2") == "'-2"
    assert neutralize("@cmd") == "'@cmd"
    assert neutralize("CC-AAA") == "CC-AAA"
    assert neutralize(None) == ""
    assert neutralize(date(2026, 7, 24)) == "2026-07-24"


@pytest.mark.django_db
def test_report_page_requires_view_permission(world):
    User.objects.create_user("viewer", password="password")
    client = Client()
    assert client.login(username="viewer", password="password")

    assert client.get(reverse("compliance-report")).status_code == 403


@pytest.mark.django_db
def test_report_page_renders_for_an_authorised_user(world):
    User.objects.create_superuser("admin", "a@test.com", "password")
    client = Client()
    assert client.login(username="admin", password="password")

    response = client.get(reverse("compliance-report"))

    assert response.status_code == 200
    assert "FAENA-01" in response.content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize("param", ["doc_type", "cost_center"])
def test_report_page_ignores_a_malformed_filter_value(world, param):
    """A non-UUID value in doc_type/cost_center (bookmarked URL, autofill, bot
    probing query strings) must be treated as "no filter", not a 500."""
    User.objects.create_superuser("admin", "a@test.com", "password")
    client = Client()
    assert client.login(username="admin", password="password")

    response = client.get(reverse("compliance-report"), {param: "not-a-uuid"})

    assert response.status_code == 200
    assert "FAENA-01" in response.content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "route,content_type",
    [
        ("compliance-report-csv", "text/csv"),
        (
            "compliance-report-xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
        (
            "compliance-report-docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
    ],
)
def test_exports_return_an_attachment(world, route, content_type):
    User.objects.create_superuser("admin", "a@test.com", "password")
    client = Client()
    assert client.login(username="admin", password="password")

    response = client.get(reverse(route))

    assert response.status_code == 200
    assert content_type in response["Content-Type"]
    assert "attachment" in response["Content-Disposition"]


@pytest.mark.django_db
def test_exports_require_view_permission(world):
    User.objects.create_user("viewer", password="password")
    client = Client()
    assert client.login(username="viewer", password="password")

    for route in (
        "compliance-report-csv",
        "compliance-report-xlsx",
        "compliance-report-docx",
    ):
        assert client.get(reverse(route)).status_code == 403


@pytest.mark.django_db
def test_command_prints_the_report_and_records_a_job_run(world, capsys):
    call_command("compliance_report")

    out = capsys.readouterr().out
    assert "FAENA-01" in out
    assert JobRun.objects.get(command="compliance_report").result == JobRun.RESULT_OK


@pytest.mark.django_db
def test_command_writes_xlsx_into_a_directory_that_does_not_exist_yet(world, tmp_path):
    target = tmp_path / "nueva-carpeta"

    call_command("compliance_report", "--output", str(target))

    written = list(target.glob("*.xlsx"))
    assert len(written) == 1
    assert written[0].stat().st_size > 0


@pytest.mark.django_db
def test_command_rejects_an_unknown_cost_center(world):
    with pytest.raises(CommandError, match="No active cost center"):
        call_command("compliance_report", "--cost-center", "NOPE")


@pytest.mark.django_db
def test_executive_report_emails_the_direccion_group(world, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    group = Group.objects.create(name="Dirección")
    user = User.objects.create_user(
        "jefa", email="jefa@example.test", password="password"
    )
    user.groups.add(group)

    call_command("send_executive_report", "--period", "week")

    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.to == ["jefa@example.test"]
    # The spreadsheet from 6.1 travels with the summary
    assert len(message.attachments) == 1
    assert message.attachments[0][0].endswith(".xlsx")


@pytest.mark.django_db
def test_executive_report_without_recipients_is_refused(world, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

    with pytest.raises(CommandError, match="No recipients"):
        call_command("send_executive_report")

    assert mail.outbox == []


@pytest.mark.django_db
def test_executive_report_dry_run_sends_nothing(world, settings, capsys):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

    call_command("send_executive_report", "--dry-run", "--to", "jefa@example.test")

    assert mail.outbox == []
    assert "[dry-run]" in capsys.readouterr().out


@pytest.mark.django_db
def test_executive_report_compares_against_the_previous_period(world, settings, capsys):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

    call_command(
        "send_executive_report",
        "--dry-run",
        "--period",
        "month",
        "--to",
        "a@test.local",
    )

    out = capsys.readouterr().out
    # Each compared KPI reports its previous value and the delta
    assert "prev" in out
    assert JobRun.objects.get(command="send_executive_report").summary.startswith(
        "[dry-run] month"
    )
