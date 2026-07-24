from datetime import date

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models
import re
from pathlib import Path
from uuid import uuid4

from apps.core.models import BaseModel
from apps.workboard.models import KanbanBoard, KanbanStage, KanbanTask


def document_upload_path(instance, filename):
    """Return the relative storage path used for manually saved documents."""

    def safe_segment(value, fallback):
        segment = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(str(value)).name).strip("._")
        return segment or fallback

    model_name = instance.content_type.model if instance.content_type_id else "entity"
    doc_type_code = safe_segment(instance.doc_type.code, "document")
    safe_model = safe_segment(model_name, "entity")
    safe_filename = safe_segment(filename, "upload")
    return (
        f"{doc_type_code}/{safe_model}/{instance.object_id}/{uuid4()}_{safe_filename}"
    )


class DocumentType(BaseModel):
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=50, unique=True)
    requires_expiry = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Document(BaseModel):
    content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT)
    object_id = models.UUIDField()
    content_object = GenericForeignKey("content_type", "object_id")
    doc_type = models.ForeignKey(DocumentType, on_delete=models.PROTECT)
    title = models.CharField(max_length=200)
    file_path = models.CharField(max_length=500)
    issue_date = models.DateField()
    expiry_date = models.DateField(null=True, blank=True)
    is_current_version = models.BooleanField(default=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["expiry_date", "is_current_version"],
                name="compliance_doc_expiry_cur_idx",
            )
        ]

    def __str__(self):
        return self.title


class AlertRule(BaseModel):
    name = models.CharField(max_length=150)
    entity_type = models.CharField(max_length=100)
    field_to_watch = models.CharField(max_length=100)
    days_before_expiry = models.PositiveIntegerField(default=30)
    enabled = models.BooleanField(default=True)
    create_kanban_task = models.BooleanField(default=False)
    target_board = models.ForeignKey(
        KanbanBoard,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="alert_rules",
    )
    target_stage = models.ForeignKey(
        KanbanStage,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="alert_rules",
    )

    def clean(self):
        super().clean()
        if not self.create_kanban_task:
            return
        if not self.target_board_id or not self.target_stage_id:
            raise ValidationError(
                "target_board and target_stage are required when "
                "create_kanban_task is enabled."
            )
        if self.target_stage.board_id != self.target_board_id:
            raise ValidationError("target_stage must belong to target_board.")


class Alert(BaseModel):
    triggered_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    alert_rule = models.ForeignKey(AlertRule, on_delete=models.PROTECT)
    content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT)
    object_id = models.UUIDField()
    content_object = GenericForeignKey("content_type", "object_id")
    message = models.TextField()
    is_resolved = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(
                fields=["is_resolved", "is_active"], name="compliance_alert_open_idx"
            )
        ]

    def _watched_value(self):
        field = self.alert_rule.field_to_watch
        return getattr(self.content_object, field, None)

    def _derive_assigned_operator(self):
        """Best-effort responsible operator for the follow-up task.

        The schema only lets us resolve an Operator when the watched entity
        *is* an Operator or exposes one (e.g. Qualification.operator). The
        cost-center path the roadmap mentions is not usable here because
        CostCenter.responsible is free text, not an FK, so those cases stay
        unassigned on purpose.
        """
        from apps.registry.models import Operator

        obj = self.content_object
        if isinstance(obj, Operator):
            return obj
        candidate = getattr(obj, "operator", None)
        return candidate if isinstance(candidate, Operator) else None

    def _follow_up_priority(self):
        value = self._watched_value()
        if not isinstance(value, date):
            return "medium"
        days_left = (value - date.today()).days
        if days_left < 0:
            return "critical"
        if days_left <= 7:
            return "high"
        return "medium"

    def ensure_follow_up_task(self):
        """Create (idempotently) the Kanban task linked to this alert.

        Returns the task, or None if the rule does not request one. Safe to
        call repeatedly: a second call returns the existing task instead of
        creating a duplicate (B1.8).
        """
        rule = self.alert_rule
        if not (rule.create_kanban_task and rule.target_board_id and rule.target_stage_id):
            return None
        alert_ct = ContentType.objects.get_for_model(Alert)
        existing = KanbanTask.objects.filter(
            source_content_type=alert_ct, source_object_id=self.pk, is_active=True
        ).first()
        if existing is not None:
            return existing
        watched = self._watched_value()
        due_date = watched if isinstance(watched, date) else None
        return KanbanTask.objects.create(
            board=rule.target_board,
            stage=rule.target_stage,
            title=f"{rule.name}: {self.content_object}",
            description=self.message,
            due_date=due_date,
            priority=self._follow_up_priority(),
            assigned_to=self._derive_assigned_operator(),
            source_object=self,
        )
