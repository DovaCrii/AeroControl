from datetime import date, timedelta

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core import mail
from django.core.management import call_command

from apps.core.models import JobRun
from apps.registry.models import Aircraft, CostCenter, Operator, Qualification
from .digest import bucket_for, build_digest
from .models import Document, DocumentType

TODAY = date(2026, 7, 24)


@pytest.fixture
def cost_center(db):
    cc = CostCenter.objects.create(code="FAENA-01", name="Faena Norte")
    responsible = Operator.objects.create(
        employee_id="OP-RESP",
        full_name="Ana Responsable",
        email="ana@example.test",
        cost_center=cc,
    )
    cc.responsible_operator = responsible
    cc.save(update_fields=["responsible_operator"])
    return cc


def _qualification(cost_center, days_from_today, name="Credencial DGAC"):
    operator = Operator.objects.create(
        employee_id=f"OP-{days_from_today}-{name[:3]}",
        full_name=f"Piloto {days_from_today}",
        cost_center=cost_center,
    )
    return Qualification.objects.create(
        operator=operator,
        qualification_type=name,
        issue_date=date(2026, 1, 1),
        expiry_date=TODAY + timedelta(days=days_from_today),
    )


def test_bucket_boundaries():
    assert bucket_for(TODAY - timedelta(days=1), TODAY) == "overdue"
    assert bucket_for(TODAY, TODAY) == "due_7"
    assert bucket_for(TODAY + timedelta(days=7), TODAY) == "due_7"
    assert bucket_for(TODAY + timedelta(days=8), TODAY) == "due_15"
    assert bucket_for(TODAY + timedelta(days=15), TODAY) == "due_15"
    assert bucket_for(TODAY + timedelta(days=16), TODAY) == "due_30"
    assert bucket_for(TODAY + timedelta(days=30), TODAY) == "due_30"
    # Beyond the horizon the item is not part of the digest
    assert bucket_for(TODAY + timedelta(days=31), TODAY) is None


@pytest.mark.django_db
def test_build_digest_groups_items_by_urgency(cost_center):
    _qualification(cost_center, -3, "Vencida")
    _qualification(cost_center, 5, "Semana")
    _qualification(cost_center, 12, "Quincena")
    _qualification(cost_center, 25, "Mes")
    _qualification(cost_center, 90, "Fuera de rango")

    buckets = build_digest(cost_center, today=TODAY)

    assert [item["label"] for item in buckets["overdue"]] == ["Vencida"]
    assert [item["label"] for item in buckets["due_7"]] == ["Semana"]
    assert [item["label"] for item in buckets["due_15"]] == ["Quincena"]
    assert [item["label"] for item in buckets["due_30"]] == ["Mes"]


@pytest.mark.django_db
def test_build_digest_includes_documents_of_the_cost_centers_aircraft(cost_center):
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Multirotor",
        model="M300",
        manufacturer="DJI",
        cost_center=cost_center,
    )
    other_cc = CostCenter.objects.create(code="OTRA", name="Otra faena")
    other_aircraft = Aircraft.objects.create(
        registration="CC-ZZZ",
        type="Multirotor",
        model="M300",
        manufacturer="DJI",
        cost_center=other_cc,
    )
    doc_type = DocumentType.objects.create(code="seguro", name="Seguro")
    aircraft_ct = ContentType.objects.get_for_model(Aircraft)
    Document.objects.create(
        title="Seguro CC-AAA",
        doc_type=doc_type,
        content_type=aircraft_ct,
        object_id=aircraft.pk,
        file_path="seguro/a.pdf",
        issue_date=date(2026, 1, 1),
        expiry_date=TODAY + timedelta(days=4),
    )
    Document.objects.create(
        title="Seguro ajeno",
        doc_type=doc_type,
        content_type=aircraft_ct,
        object_id=other_aircraft.pk,
        file_path="seguro/z.pdf",
        issue_date=date(2026, 1, 1),
        expiry_date=TODAY + timedelta(days=4),
    )

    buckets = build_digest(cost_center, today=TODAY)

    labels = [item["label"] for item in buckets["due_7"]]
    assert labels == ["Seguro CC-AAA"]


@pytest.mark.django_db
def test_digest_is_emailed_to_the_responsible_operator(cost_center, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    _qualification(cost_center, 3, "Credencial urgente")

    call_command("send_alert_digest")

    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.to == ["ana@example.test"]
    assert "Faena Norte" in message.subject
    assert "Credencial urgente" in message.body
    # HTML alternative attached as well
    assert any(kind == "text/html" for _content, kind in message.alternatives)


@pytest.mark.django_db
def test_dry_run_sends_nothing_but_reports(cost_center, settings, capsys):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    _qualification(cost_center, 3)

    call_command("send_alert_digest", "--dry-run")

    assert mail.outbox == []
    out = capsys.readouterr().out
    assert "[dry-run]" in out
    assert "ana@example.test" in out


@pytest.mark.django_db
def test_cost_center_without_responsible_email_is_skipped(cost_center, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    cost_center.responsible_operator = None
    cost_center.save(update_fields=["responsible_operator"])
    _qualification(cost_center, 3)

    call_command("send_alert_digest")

    assert mail.outbox == []
    job = JobRun.objects.get(command="send_alert_digest")
    assert "1 skipped" in job.summary


@pytest.mark.django_db
def test_digest_reaches_an_external_contact_with_no_operator(cost_center, settings):
    """The responsible person for a cost center is not always an operator."""
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    cost_center.responsible_operator = None
    cost_center.responsible_contact_email = "secretaria@example.test"
    cost_center.save(
        update_fields=["responsible_operator", "responsible_contact_email"]
    )
    _qualification(cost_center, 3)

    call_command("send_alert_digest")

    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["secretaria@example.test"]


@pytest.mark.django_db
def test_cost_center_without_expiring_items_gets_no_email(cost_center, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    _qualification(cost_center, 200)

    call_command("send_alert_digest")

    assert mail.outbox == []


@pytest.mark.django_db
def test_digest_records_a_job_run(cost_center, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    _qualification(cost_center, 2)

    call_command("send_alert_digest")

    job = JobRun.objects.get(command="send_alert_digest")
    assert job.result == JobRun.RESULT_OK
    assert "1 digests" in job.summary
