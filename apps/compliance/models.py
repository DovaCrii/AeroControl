from datetime import date

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
import re
from pathlib import Path
from uuid import uuid4

from apps.core.models import BaseModel
from apps.workboard.models import KanbanBoard, KanbanStage, KanbanTask
from .watchables import resolve_model, watchable_fields

DGAC_BOARD_NAME = "Cumplimiento DGAC"


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
        verbose_name = _("document")
        verbose_name_plural = _("documents")
        indexes = [
            models.Index(
                fields=["expiry_date", "is_current_version"],
                name="compliance_doc_expiry_cur_idx",
            )
        ]

    def __str__(self):
        return self.title

    def resolve_related_alerts(self):
        """Resolve open alerts pointing at this document (B1.7).

        Invoked when a newer version supersedes this one: the "expiring soon"
        alert is now addressed. Each alert is resolved via Alert.resolve(), so
        any linked Kanban task is closed too. Returns the number resolved.
        """
        doc_ct = ContentType.objects.get_for_model(Document)
        open_alerts = Alert.objects.filter(
            content_type=doc_ct,
            object_id=self.pk,
            is_resolved=False,
            is_active=True,
        )
        resolved = 0
        for alert in open_alerts:
            alert.resolve()
            resolved += 1
        return resolved


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

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        errors = {}

        # A rule pointing at a model or field that does not exist used to be
        # accepted and then skipped every night without anyone noticing.
        model = resolve_model(self.entity_type)
        if model is None:
            errors["entity_type"] = _(
                "Unknown entity type. Choose one of the watchable models."
            )
        else:
            allowed = watchable_fields(model)
            if self.field_to_watch not in allowed:
                errors["field_to_watch"] = _(
                    "%(field)s is not a watchable field of %(model)s. "
                    "Available: %(allowed)s"
                ) % {
                    "field": self.field_to_watch,
                    "model": model._meta.verbose_name,
                    "allowed": ", ".join(allowed) or "-",
                }

        if self.create_kanban_task:
            if not self.target_board_id or not self.target_stage_id:
                errors["target_board"] = _(
                    "A board and a stage are required to create Kanban tasks."
                )
            elif self.target_stage.board_id != self.target_board_id:
                errors["target_stage"] = _("The stage must belong to the board.")

        if errors:
            raise ValidationError(errors)

    @property
    def watched_model(self):
        return resolve_model(self.entity_type)


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

    def __str__(self):
        entity = self.content_object
        return f"{self.alert_rule.name} · {entity}" if entity else self.alert_rule.name

    def _watched_value(self):
        field = self.alert_rule.field_to_watch
        return getattr(self.content_object, field, None)

    @property
    def entity_label(self):
        """Human-readable name of the watched model (not the raw model slug)."""
        model = self.content_type.model_class()
        label = model._meta.verbose_name if model else self.content_type.model
        return str(label).capitalize()

    @property
    def watched_date(self):
        """The watched value when it is a date, for display in listings."""
        value = self._watched_value()
        return value if isinstance(value, date) else None

    @property
    def is_overdue(self):
        watched = self.watched_date
        return watched is not None and watched < timezone.localdate()

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
        days_left = (value - timezone.localdate()).days
        if days_left < 0:
            return "critical"
        if days_left <= 7:
            return "high"
        return "medium"

    def linked_task(self):
        """Return the active Kanban task spawned from this alert, if any."""
        alert_ct = ContentType.objects.get_for_model(Alert)
        return KanbanTask.objects.filter(
            source_content_type=alert_ct, source_object_id=self.pk, is_active=True
        ).first()

    def _default_board_and_stage(self):
        """Fallback destination when the rule has no explicit target.

        Used by the manual "create follow-up task" action so the operator gets
        a one-click flow instead of a board/stage picker: the compliance board
        seeded by `init_dgac_board` is the intended home for these tasks.
        Returns (board, stage) or (None, None) when no usable board exists.
        """
        board = (
            KanbanBoard.objects.filter(name=DGAC_BOARD_NAME, is_active=True).first()
            or KanbanBoard.objects.filter(is_active=True).order_by("created_at").first()
        )
        if board is None:
            return None, None
        stage = board.stages.filter(is_active=True).order_by("order").first()
        return (board, stage) if stage is not None else (None, None)

    def ensure_follow_up_task(self, allow_default_board=False):
        """Create (idempotently) the Kanban task linked to this alert.

        Returns the task, or None if no destination can be resolved. Safe to
        call repeatedly: a second call returns the existing task instead of
        creating a duplicate (B1.8).

        `allow_default_board=True` (the manual action) falls back to the
        compliance board when the rule has no target configured; automatic
        generation stays opt-in via the rule's create_kanban_task flag.
        """
        rule = self.alert_rule
        board, stage = rule.target_board, rule.target_stage
        if not (
            rule.create_kanban_task and rule.target_board_id and rule.target_stage_id
        ):
            if not allow_default_board:
                return None
            board, stage = self._default_board_and_stage()
            if board is None:
                return None
        existing = self.linked_task()
        if existing is not None:
            return existing
        watched = self._watched_value()
        due_date = watched if isinstance(watched, date) else None
        return KanbanTask.objects.create(
            board=board,
            stage=stage,
            title=f"{rule.name}: {self.content_object}",
            description=self.message,
            due_date=due_date,
            priority=self._follow_up_priority(),
            assigned_to=self._derive_assigned_operator(),
            source_object=self,
        )

    def resolve(self):
        """Mark the alert resolved and close its linked task (B1.6).

        Moves the linked task (if any, and not already there) to the board's
        first stage whose status_type is 'completed'. Returns the moved task
        so the caller can record it in the audit trail, or None if nothing
        moved.
        """
        from django.utils import timezone

        self.is_resolved = True
        self.resolved_at = timezone.now()
        self.save(update_fields=["is_resolved", "resolved_at", "updated_at"])
        task = self.linked_task()
        if task is None:
            return None
        completed_stage = (
            task.board.stages.filter(status_type="completed", is_active=True)
            .order_by("order")
            .first()
        )
        if completed_stage is None or task.stage_id == completed_stage.pk:
            return None
        task.stage = completed_stage
        task.save(update_fields=["stage", "updated_at"])
        return task
