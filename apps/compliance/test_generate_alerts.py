import logging
from datetime import date, timedelta

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command

from .models import Alert, AlertRule, Document, DocumentType


@pytest.mark.django_db
def test_invalid_entity_type_is_skipped_and_logged(caplog):
    AlertRule.objects.create(
        name="Bogus rule",
        entity_type="not_a_real_model",
        field_to_watch="expiry_date",
    )

    with caplog.at_level(logging.WARNING, logger="compliance.alerts"):
        call_command("generate_alerts")

    assert Alert.objects.count() == 0
    record = next(
        r for r in caplog.records if r.name == "compliance.alerts"
    )
    assert record.rule_name == "Bogus rule"
    assert record.entity_type == "not_a_real_model"
    assert record.reason == "unknown_entity_type"


@pytest.mark.django_db
def test_invalid_field_to_watch_is_skipped_and_logged(caplog):
    AlertRule.objects.create(
        name="Wrong field",
        entity_type="document",
        field_to_watch="not_a_real_field",
    )

    with caplog.at_level(logging.WARNING, logger="compliance.alerts"):
        call_command("generate_alerts")

    record = next(
        r for r in caplog.records if r.name == "compliance.alerts"
    )
    assert record.reason == "unknown_field_to_watch"
    assert record.field_to_watch == "not_a_real_field"


@pytest.mark.django_db
def test_valid_rule_creates_one_alert_and_skips_duplicates_on_rerun():
    doc_type = DocumentType.objects.create(code="cert", name="Certificate")
    content_type = ContentType.objects.get_for_model(Document)
    document = Document.objects.create(
        title="Expiring soon",
        doc_type=doc_type,
        content_type=content_type,
        object_id="00000000-0000-0000-0000-000000000001",
        file_path="cert/document/file.pdf",
        issue_date=date(2026, 1, 1),
        expiry_date=date.today() + timedelta(days=5),
    )
    AlertRule.objects.create(
        name="Expiring documents",
        entity_type="document",
        field_to_watch="expiry_date",
        days_before_expiry=30,
    )

    call_command("generate_alerts")
    call_command("generate_alerts")

    assert Alert.objects.count() == 1
    alert = Alert.objects.get()
    assert alert.object_id == document.pk
    assert alert.is_resolved is False
