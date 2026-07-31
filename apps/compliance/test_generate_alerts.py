import logging
from datetime import date, timedelta

from django.utils import timezone

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command

from apps.registry.models import (
    CostCenter,
    Operator,
    Qualification,
    QualificationType,
)
from apps.workboard.models import KanbanBoard, KanbanStage, KanbanTask
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
    record = next(r for r in caplog.records if r.name == "compliance.alerts")
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

    record = next(r for r in caplog.records if r.name == "compliance.alerts")
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
        expiry_date=timezone.localdate() + timedelta(days=5),
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


@pytest.mark.django_db
def test_status_field_rule_alerts_open_records_not_terminal_ones():
    """A rule watching a `status` field (not a date) alerts records in an open
    status and skips terminal ones (completed/denied)."""
    from apps.operations.models import FlightPermission

    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    common = dict(
        cost_center=cost_center,
        purpose="Survey",
        valid_from=date(2026, 7, 1),
        valid_until=date(2026, 7, 10),
        location="Site",
    )
    open_permission = FlightPermission.objects.create(
        permission_number="P-OPEN", status="requested", **common
    )
    FlightPermission.objects.create(
        permission_number="P-DONE", status="completed", **common
    )
    AlertRule.objects.create(
        name="Permits pending",
        entity_type="operations.flightpermission",
        field_to_watch="status",
    )

    call_command("generate_alerts")

    ct = ContentType.objects.get_for_model(FlightPermission)
    alerts = Alert.objects.filter(content_type=ct)
    assert [a.object_id for a in alerts] == [open_permission.pk]


@pytest.mark.django_db
def test_digest_item_count_sums_all_buckets():
    from apps.compliance.digest import digest_item_count

    buckets = {"overdue": [1, 2], "due_7": [3], "due_15": [], "due_30": [4]}
    assert digest_item_count(buckets) == 4


def _kanban_rule(**kwargs):
    board = KanbanBoard.objects.create(name="Compliance")
    stage = KanbanStage.objects.create(
        board=board, name="Por vencer", status_type="pending"
    )
    defaults = dict(
        name="Expiring quals",
        entity_type="qualification",
        field_to_watch="expiry_date",
        days_before_expiry=30,
        create_kanban_task=True,
        target_board=board,
        target_stage=stage,
    )
    defaults.update(kwargs)
    return AlertRule.objects.create(**defaults), board, stage


@pytest.mark.django_db
def test_generate_alerts_creates_linked_task_with_urgency_priority():
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    operator = Operator.objects.create(
        employee_id="P1", full_name="Pilot One", cost_center=cost_center
    )
    qualification = Qualification.objects.create(
        operator=operator,
        qualification_type=QualificationType.objects.get_or_create(
            code="night-rating", defaults={"name": "Night rating"}
        )[0],
        issue_date=date(2026, 1, 1),
        expiry_date=timezone.localdate() - timedelta(days=1),  # already expired
    )
    rule, board, stage = _kanban_rule()

    call_command("generate_alerts")

    alert = Alert.objects.get()
    task = KanbanTask.objects.get()
    assert task.board_id == board.pk
    assert task.stage_id == stage.pk
    assert task.source_object == alert
    assert task.due_date == qualification.expiry_date
    assert task.priority == "critical"  # expired
    assert task.assigned_to_id == operator.pk  # derived from qualification.operator


@pytest.mark.django_db
def test_generate_alerts_task_creation_is_idempotent():
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    operator = Operator.objects.create(
        employee_id="P1", full_name="Pilot One", cost_center=cost_center
    )
    Qualification.objects.create(
        operator=operator,
        qualification_type=QualificationType.objects.get_or_create(
            code="night-rating", defaults={"name": "Night rating"}
        )[0],
        issue_date=date(2026, 1, 1),
        expiry_date=timezone.localdate() + timedelta(days=3),
    )
    _kanban_rule()

    call_command("generate_alerts")
    call_command("generate_alerts")

    assert Alert.objects.count() == 1
    assert KanbanTask.objects.count() == 1
    assert KanbanTask.objects.get().priority == "high"  # within 7 days


@pytest.mark.django_db
def test_rule_without_kanban_flag_creates_no_task():
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    operator = Operator.objects.create(
        employee_id="P1", full_name="Pilot One", cost_center=cost_center
    )
    Qualification.objects.create(
        operator=operator,
        qualification_type=QualificationType.objects.get_or_create(
            code="night-rating", defaults={"name": "Night rating"}
        )[0],
        issue_date=date(2026, 1, 1),
        expiry_date=timezone.localdate() + timedelta(days=3),
    )
    AlertRule.objects.create(
        name="Quals no task",
        entity_type="qualification",
        field_to_watch="expiry_date",
        create_kanban_task=False,
    )

    call_command("generate_alerts")

    assert Alert.objects.count() == 1
    assert KanbanTask.objects.count() == 0


@pytest.mark.django_db
def test_resolving_alert_moves_linked_task_to_completed_stage():
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    operator = Operator.objects.create(
        employee_id="P1", full_name="Pilot One", cost_center=cost_center
    )
    Qualification.objects.create(
        operator=operator,
        qualification_type=QualificationType.objects.get_or_create(
            code="night-rating", defaults={"name": "Night rating"}
        )[0],
        issue_date=date(2026, 1, 1),
        expiry_date=timezone.localdate() + timedelta(days=3),
    )
    rule, board, pending_stage = _kanban_rule()
    done_stage = KanbanStage.objects.create(
        board=board, name="Aprobado", status_type="completed", order=5
    )
    call_command("generate_alerts")
    alert = Alert.objects.get()
    task = KanbanTask.objects.get()
    assert task.stage_id == pending_stage.pk

    moved = alert.resolve()

    assert moved is not None
    task.refresh_from_db()
    assert task.stage_id == done_stage.pk
    alert.refresh_from_db()
    assert alert.is_resolved is True


@pytest.mark.django_db
def test_resolving_alert_without_task_returns_none():
    doc_type = DocumentType.objects.create(code="cert", name="Certificate")
    ct = ContentType.objects.get_for_model(Document)
    document = Document.objects.create(
        title="Doc",
        doc_type=doc_type,
        content_type=ct,
        object_id="00000000-0000-0000-0000-000000000001",
        file_path="cert/document/file.pdf",
        issue_date=date(2026, 1, 1),
        expiry_date=timezone.localdate() + timedelta(days=3),
    )
    rule = AlertRule.objects.create(
        name="Docs no task",
        entity_type="document",
        field_to_watch="expiry_date",
        create_kanban_task=False,
    )
    alert = Alert.objects.create(
        alert_rule=rule,
        content_type=ct,
        object_id=document.pk,
        message="no task alert",
    )

    assert alert.resolve() is None
    alert.refresh_from_db()
    assert alert.is_resolved is True


@pytest.mark.django_db
def test_document_resolve_related_alerts_closes_open_alerts_and_task():
    doc_type = DocumentType.objects.create(code="cert", name="Certificate")
    ct = ContentType.objects.get_for_model(Document)
    old_document = Document.objects.create(
        title="Old cert",
        doc_type=doc_type,
        content_type=ct,
        object_id="00000000-0000-0000-0000-000000000001",
        file_path="cert/document/old.pdf",
        issue_date=date(2026, 1, 1),
        expiry_date=timezone.localdate() + timedelta(days=2),
    )
    board = KanbanBoard.objects.create(name="Compliance")
    pending = KanbanStage.objects.create(
        board=board, name="Por vencer", status_type="pending"
    )
    done = KanbanStage.objects.create(
        board=board, name="Aprobado", status_type="completed", order=5
    )
    rule = AlertRule.objects.create(
        name="Doc expiry",
        entity_type="document",
        field_to_watch="expiry_date",
        create_kanban_task=True,
        target_board=board,
        target_stage=pending,
    )
    alert = Alert.objects.create(
        alert_rule=rule,
        content_type=ct,
        object_id=old_document.pk,
        message="Doc expiring",
    )
    task = alert.ensure_follow_up_task()
    assert task.stage_id == pending.pk

    resolved = old_document.resolve_related_alerts()

    assert resolved == 1
    alert.refresh_from_db()
    assert alert.is_resolved is True
    task.refresh_from_db()
    assert task.stage_id == done.pk
