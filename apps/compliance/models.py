from datetime import date, timedelta

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
import re
from pathlib import Path
from uuid import uuid4

from apps.core.models import BaseModel, OperationalTenant
from apps.core.tenancy import get_default_tenant
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
    # LV-4: flags the type whose expiry the Aircraft list surfaces as a
    # column (e.g. liability insurance). Not unique by design -- a fleet may
    # split insurance into more than one policy type -- the aircraft list
    # takes whichever of this aircraft's current documents of a flagged type
    # expires soonest.
    is_insurance = models.BooleanField(
        default=False,
        verbose_name=_("Insurance document type"),
        help_text=_(
            "Shows this type's expiry on the aircraft list (e.g. liability insurance)."
        ),
    )
    # LV-30: flags the per-flight operational records (flight log, RPA
    # checklist, drone inspection) that the operational-records repository and
    # the monthly compliance review track -- a different category from the
    # company-wide procedures, which stay ordinary documents.
    is_operational_record = models.BooleanField(
        default=False,
        verbose_name=_("Operational record type"),
        help_text=_(
            "A per-flight record (flight log, checklist, inspection) tracked in "
            "the operational-records repository and the monthly review."
        ),
    )

    def __str__(self):
        return self.name


class Document(BaseModel):
    # T3.2 Fase 0b: own tenant FK. A Document points at any entity through a
    # GenericForeignKey, so its tenant cannot be derived with a cheap join like
    # the other records -- this is also the F-05 gap (download authorization had
    # no tenant path). Root aggregate, carries its own tenant.
    tenant = models.ForeignKey(
        OperationalTenant,
        on_delete=models.PROTECT,
        default=get_default_tenant,
        related_name="documents",
    )
    content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT)
    object_id = models.UUIDField()
    content_object = GenericForeignKey("content_type", "object_id")
    doc_type = models.ForeignKey(DocumentType, on_delete=models.PROTECT)
    title = models.CharField(max_length=200)
    file_path = models.CharField(max_length=500)
    issue_date = models.DateField()
    expiry_date = models.DateField(null=True, blank=True)
    is_current_version = models.BooleanField(default=True)
    # R4.2: idempotency and provenance for the Z: repository importer.
    # `file_path` cannot detect a re-import -- document_upload_path() mints a
    # fresh uuid4() into the path every time. `content_sha256` catches the
    # real case found in production of two files sharing a name with
    # different content (a policy PDF filed under two subfolders, 110176 B
    # vs 107152 B) -- deduplicating by name alone would silently keep only
    # one. `source_reference` is the path relative to the import source
    # (e.g. `Z:`), so a rerun can tell "already imported this exact file"
    # from "new file at this path" without re-hashing everything.
    content_sha256 = models.CharField(max_length=64, blank=True)
    source_reference = models.CharField(max_length=500, blank=True)

    class Meta:
        verbose_name = _("document")
        verbose_name_plural = _("documents")
        indexes = [
            models.Index(
                fields=["expiry_date", "is_current_version"],
                name="compliance_doc_expiry_cur_idx",
            ),
            # Django only indexes the FK half of a GenericForeignKey; the
            # report and the calendar filter on the (type, id) pair.
            models.Index(
                fields=["content_type", "object_id"],
                name="compliance_doc_subject_idx",
            ),
        ]

    def __str__(self):
        return self.title

    @property
    def is_expired(self):
        """LV-84: past its expiry date.

        A document with no expiry is **not** expired -- it simply does not
        lapse (a procedure, a manual). Same reading as
        `Aircraft.insurance_is_overdue`: a null is "does not apply", never
        "overdue".
        """
        from django.utils import timezone

        return self.expiry_date is not None and self.expiry_date < timezone.localdate()

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


class MonthlyComplianceReview(BaseModel):
    """LV-30: the end-of-month sign-off that a cost center's operational records
    (flight logs, checklists, inspections) are on file for the flights it flew.

    One row per (cost_center, period). `check_monthly_records` creates it in
    `pending` on the last day of the month and mails the reviewer (Dirección);
    the reviewer then marks it `completed` or `non_compliant`. The alert rule
    watching `status` keeps a pending review as a live alert (generate_alerts
    treats completed/non_compliant as terminal); marking it resolves that alert
    via `resolve_open_alerts_for`.

    Tenancy: derives through `cost_center` (ADR-0001 -- only roots carry a
    tenant), so no own tenant FK.
    """

    STATUS_PENDING = "pending"
    STATUS_COMPLETED = "completed"
    STATUS_NON_COMPLIANT = "non_compliant"
    STATUS_CHOICES = [
        (STATUS_PENDING, _("Pending review")),
        (STATUS_COMPLETED, _("Compliant")),
        (STATUS_NON_COMPLIANT, _("Non-compliant")),
    ]
    # generate_alerts stops alerting once the status is one of these (the
    # reviewer has acted); mirrors its ("completed", "denied") terminal set.
    RESOLVED_STATUSES = frozenset({STATUS_COMPLETED, STATUS_NON_COMPLIANT})

    cost_center = models.ForeignKey(
        "registry.CostCenter",
        on_delete=models.PROTECT,
        related_name="monthly_reviews",
    )
    # First day of the month under review, the canonical key for the period.
    period = models.DateField(verbose_name=_("Period (month)"))
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("monthly compliance review")
        verbose_name_plural = _("monthly compliance reviews")
        ordering = ["-period", "cost_center__code"]
        constraints = [
            models.UniqueConstraint(
                fields=["cost_center", "period"],
                name="compliance_monthlyreview_cc_period_uniq",
            )
        ]

    def __str__(self):
        return f"{self.cost_center} · {self.period:%Y-%m}"

    @transaction.atomic
    def mark(self, status, user, notes=""):
        """Record the reviewer's decision and clear the pending alert.

        Marking either terminal status resolves the open alert (the review is
        done); a status back to pending is not offered in the UI.
        """
        from .alerts import resolve_open_alerts_for

        self.status = status
        self.reviewed_by = user if getattr(user, "is_authenticated", False) else None
        self.reviewed_at = timezone.now()
        if notes:
            self.notes = notes
        self.save(
            update_fields=[
                "status",
                "reviewed_by",
                "reviewed_at",
                "notes",
                "updated_at",
            ]
        )
        if status in self.RESOLVED_STATUSES:
            resolve_open_alerts_for(self)
        return self


class ComplianceSnapshot(BaseModel):
    """R7.7 (ISO 9.1.1): the documentary totals as they stood on one date.

    Exists to make **trend** possible. `build_compliance_report` evaluates
    `valid`/`expired`/`due_*` always "as of today" regardless of the period
    asked for (only the resolution stats honour `start`/`end`), so comparing
    "this period" against "the previous one" reads *no change* on those
    counters by construction -- two photographs of the same instant. ISO 9.1.1
    asks for a KPI with a target **and a trend**; without stored history there
    is no trend to show. Found and documented while doing R6.4, resolved here.

    Written by the `snapshot_compliance` command, one row per (date, cost
    center) plus one consolidated row with `cost_center=None`. Append-only in
    spirit: a rerun for the same date overwrites that date rather than
    accumulating duplicates, so a job that runs twice does not corrupt a trend.

    Tenancy: carries its own `tenant` FK. The consolidated row has no cost
    center to derive it from (ADR-0001: only roots carry a tenant), the same
    reason `AlertRule` and `Document` carry theirs.
    """

    tenant = models.ForeignKey(
        OperationalTenant,
        on_delete=models.PROTECT,
        default=get_default_tenant,
        related_name="compliance_snapshots",
    )
    date = models.DateField(verbose_name=_("Snapshot date"))
    # NULL = the consolidated row across every cost center of this tenant.
    cost_center = models.ForeignKey(
        "registry.CostCenter",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="compliance_snapshots",
    )
    total = models.PositiveIntegerField(default=0)
    valid = models.PositiveIntegerField(default=0)
    expired = models.PositiveIntegerField(default=0)
    due_7 = models.PositiveIntegerField(default=0)
    due_15 = models.PositiveIntegerField(default=0)
    due_30 = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = _("compliance snapshot")
        verbose_name_plural = _("compliance snapshots")
        ordering = ["-date"]
        constraints = [
            # Two constraints, not one: SQLite (and Postgres) treat NULLs as
            # distinct in a unique index, so a single constraint over
            # (tenant, date, cost_center) would happily store the consolidated
            # row twice for the same date. Split by whether cost_center is set.
            models.UniqueConstraint(
                fields=["tenant", "date", "cost_center"],
                condition=models.Q(cost_center__isnull=False),
                name="compliance_snapshot_cc_date_uniq",
            ),
            models.UniqueConstraint(
                fields=["tenant", "date"],
                condition=models.Q(cost_center__isnull=True),
                name="compliance_snapshot_total_date_uniq",
            ),
        ]
        indexes = [
            # The trend lookup is "the most recent snapshot before date X".
            models.Index(
                fields=["cost_center", "-date"], name="compliance_snap_trend_idx"
            )
        ]

    def __str__(self):
        scope = self.cost_center.code if self.cost_center else _("All cost centers")
        return f"{self.date:%Y-%m-%d} · {scope}"

    @property
    def valid_pct(self):
        """Recomputed, never stored: a stored percentage can silently disagree
        with the counters it came from once either is edited."""
        return round(self.valid * 100 / self.total, 1) if self.total else 0.0


class AlertRule(BaseModel):
    # T3.2 Fase 0b: own tenant FK. A rule is per-tenant configuration with no
    # single parent to derive from. The alerts it generates derive their tenant
    # from the rule (or the watched record).
    tenant = models.ForeignKey(
        OperationalTenant,
        on_delete=models.PROTECT,
        default=get_default_tenant,
        related_name="alert_rules",
    )
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


class EffectivenessVerificationMixin(models.Model):
    """R7.6 (ISO 10.2): "was the corrective action effective?", shared.

    Extracted when `NonConformity` became the second user of the pattern that
    `Alert` introduced -- the repo's rule is to extract on the second use, not
    to anticipate it (AGENTS.md). The fields and the clock are identical; what
    differs per model is *when* the subject counts as closed, which subclasses
    answer through `effectiveness_subject_is_closed`.
    """

    # 30 days: one monthly cycle, matching the cadence the compliance review
    # already runs on (R6.5), so verification lands in a rhythm the operation
    # keeps rather than a new one. Decided with the user 2026-08-12.
    EFFECTIVENESS_DAYS = 30

    # Nullable, so records closed before this existed are not retroactively
    # overdue -- there is no honest due date to invent for them.
    effectiveness_due_date = models.DateField(null=True, blank=True)
    effectiveness_verified_at = models.DateTimeField(null=True, blank=True)
    effectiveness_verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    effectiveness_note = models.TextField(blank=True)

    class Meta:
        abstract = True

    def effectiveness_subject_is_closed(self):
        """Whether the corrective action has been taken at all."""
        raise NotImplementedError

    def start_effectiveness_clock(self):
        self.effectiveness_due_date = timezone.localdate() + timedelta(
            days=self.EFFECTIVENESS_DAYS
        )

    def clear_effectiveness(self):
        """Used when the closure is undone: any verification recorded attested
        to a closure that no longer stands."""
        self.effectiveness_due_date = None
        self.effectiveness_verified_at = None
        self.effectiveness_verified_by = None
        self.effectiveness_note = ""

    @property
    def effectiveness_is_due(self):
        """Closed, past its due date, and nobody has confirmed it worked."""
        return (
            self.effectiveness_subject_is_closed()
            and self.effectiveness_due_date is not None
            and self.effectiveness_verified_at is None
            and self.effectiveness_due_date <= timezone.localdate()
        )

    def verify_effectiveness(self, *, user=None, note=""):
        """Record that the corrective action was checked and held.

        Deliberately *not* the inverse of undoing the closure: it leaves the
        record closed and its reason untouched, and adds a second, later
        statement -- "and it worked" -- which is what ISO 10.2 asks for beyond
        the fix itself.
        """
        if not self.effectiveness_subject_is_closed():
            return False
        self.effectiveness_verified_at = timezone.now()
        self.effectiveness_verified_by = user
        self.effectiveness_note = note
        self.save(
            update_fields=[
                "effectiveness_verified_at",
                "effectiveness_verified_by",
                "effectiveness_note",
                "updated_at",
            ]
        )
        return True


class Alert(EffectivenessVerificationMixin, BaseModel):
    triggered_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    alert_rule = models.ForeignKey(AlertRule, on_delete=models.PROTECT)
    content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT)
    object_id = models.UUIDField()
    content_object = GenericForeignKey("content_type", "object_id")
    message = models.TextField()
    is_resolved = models.BooleanField(default=False)
    # Where the linked Kanban task stood before resolving moved it to the
    # completed stage. Without it, undoing could only guess a destination.
    # SET_NULL rather than PROTECT: an archived stage must not block the undo,
    # it just costs the exact restore.
    resolved_from_stage = models.ForeignKey(
        "workboard.KanbanStage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        editable=False,
    )
    # R6.2: ISO 10.2 asks for the root cause on record, not just "handled" --
    # the manual "Resolve" button required nothing before this. Blank at the
    # model level (automatic resolutions -- resolve_open_alerts_for,
    # resolve_related_alerts, R6.1's task-completion signal -- have no human
    # to ask, and stay reason-less); AlertResolveForm is what actually makes
    # it required for the one place a human clicks "Resolve".
    resolution_reason = models.TextField(blank=True)
    # R7.6 (ISO 10.2): the effectiveness fields and the 30-day clock come from
    # EffectivenessVerificationMixin, shared with NonConformity. Resolving used
    # to be terminal -- nobody ever went back to ask whether the action worked,
    # so a reason on record could describe a fix that never held.
    # `check_alert_effectiveness` escalates whatever is due and unverified.

    class Meta:
        indexes = [
            models.Index(
                fields=["is_resolved", "is_active"], name="compliance_alert_open_idx"
            ),
            # check_alert_effectiveness runs daily over exactly this pair.
            models.Index(
                fields=["effectiveness_due_date", "effectiveness_verified_at"],
                name="compliance_alert_effect_idx",
            ),
            # generate_alerts dedupes and resolve_related_alerts filters on the
            # watched (type, id) pair.
            models.Index(
                fields=["content_type", "object_id"],
                name="compliance_alert_subject_idx",
            ),
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

    @transaction.atomic
    def resolve(self, reason=""):
        """Mark the alert resolved and close its linked task (B1.6).

        Moves the linked task (if any, and not already there) to the board's
        first stage whose status_type is 'completed'. Returns the moved task
        so the caller can record it in the audit trail, or None if nothing
        moved.

        Atomic: the alert flag and the task move are one fact. A crash between
        the two saves left a resolved alert with its task still open -- the
        exact desynchronisation the alert-task link exists to prevent.

        `reason` (R6.2, ISO 10.2's root cause on record) is optional here --
        the automatic callers (resolve_open_alerts_for, resolve_related_alerts,
        R6.1's task-completion signal) have no human to ask. AlertResolveForm
        is what actually requires it for the one manual "Resolve" button.
        """
        self.is_resolved = True
        self.resolved_at = timezone.now()
        self.resolution_reason = reason
        # R7.6: the clock for "did this actually work?" starts here, for every
        # caller including the automatic ones. An automatic close (a renewed
        # expiry date, a completed maintenance) is still a corrective action
        # whose effect the norm expects someone to confirm.
        self.start_effectiveness_clock()
        task = self.linked_task()
        completed_stage = None
        if task is not None:
            completed_stage = (
                task.board.stages.filter(status_type="completed", is_active=True)
                .order_by("order")
                .first()
            )
        moved = (
            task is not None
            and completed_stage is not None
            and task.stage_id != completed_stage.pk
        )
        # Recorded before the move, so reopen() can put the task back exactly
        # where it was instead of guessing a stage.
        self.resolved_from_stage = task.stage if moved else None
        self.save(
            update_fields=[
                "is_resolved",
                "resolved_at",
                "resolution_reason",
                "resolved_from_stage",
                "effectiveness_due_date",
                "updated_at",
            ]
        )
        if not moved:
            return None
        task.stage = completed_stage
        task.save(update_fields=["stage", "updated_at"])
        return task

    @transaction.atomic
    def reopen(self):
        """Undo a resolution and send the linked task back (B1.6, inverse).

        Resolving is one click and easy to hit by mistake, so it has to be
        reversible. Returns the task that moved back, or None when nothing did.

        The task returns to the stage recorded at resolve time. When that stage
        is gone -- or the alert was resolved before this was tracked -- it falls
        back to the first stage that is not a completed one, which is the
        closest honest guess.
        """
        if not self.is_resolved:
            return None

        self.is_resolved = False
        self.resolved_at = None
        self.resolution_reason = ""
        # R7.6: reopening *is* the answer to "did it work?" -- no. The pending
        # verification goes with it; the alert is open again and will get its
        # own new due date when it is next resolved.
        self.clear_effectiveness()
        origin = self.resolved_from_stage
        self.resolved_from_stage = None
        self.save(
            update_fields=[
                "is_resolved",
                "resolved_at",
                "resolution_reason",
                "resolved_from_stage",
                "effectiveness_due_date",
                "effectiveness_verified_at",
                "effectiveness_verified_by",
                "effectiveness_note",
                "updated_at",
            ]
        )

        task = self.linked_task()
        if task is None:
            return None
        target = origin if origin is not None and origin.is_active else None
        if target is None:
            target = (
                task.board.stages.filter(is_active=True)
                .exclude(status_type="completed")
                .order_by("order")
                .first()
            )
        if target is None or task.stage_id == target.pk:
            return None
        task.stage = target
        task.save(update_fields=["stage", "updated_at"])
        return task

    def effectiveness_subject_is_closed(self):
        """For an alert, the corrective action is taken once it is resolved.
        Verifying an open one would attest to the effectiveness of an action
        nobody has taken."""
        return self.is_resolved


class NonConformity(EffectivenessVerificationMixin, BaseModel):
    """R7.6: a reflight, a rejected survey or an incident, on record (ISO 10.2).

    **Deliberately not an Alert.** `AlertRule` watches "this date expires in N
    days"; a reflight is not that, and forcing it through that engine would
    repeat the mistake R5.1 already avoided. What the two share is the
    effectiveness follow-up, which is why that lives in a mixin rather than in
    either model.

    The source object is a GFK (`Document` and `Alert` already use the pattern)
    because the origin can be a deliverable, a maintenance record, a flight --
    or nothing at all, for a finding that came out of an audit.

    Reporting to the DGAC is two plain fields rather than a workflow: for an
    incident that legally requires notification, "reported on this date with
    this reference" *is* the evidence an auditor asks for. Whether a given
    incident requires it is a regulatory question nobody has answered yet, so
    this records the fact and does not gate on it.
    """

    SOURCE_REFLIGHT = "reflight"
    SOURCE_REJECTED_DELIVERABLE = "rejected_deliverable"
    SOURCE_INCIDENT = "incident"
    SOURCE_AUDIT_FINDING = "audit_finding"
    SOURCE_CHOICES = [
        (SOURCE_REFLIGHT, _("Reflight")),
        (SOURCE_REJECTED_DELIVERABLE, _("Rejected deliverable")),
        (SOURCE_INCIDENT, _("Incident")),
        (SOURCE_AUDIT_FINDING, _("Audit finding")),
    ]

    STATUS_OPEN = "open"
    STATUS_CLOSED = "closed"
    # Under a context: the bare "Closed" msgid is already the contract status
    # ("Cerrado", masculine, agreeing with *contrato*), and reusing it renders
    # "Cerrado" next to *no conformidad*, which is feminine in Spanish. Same
    # mechanism LV-61 needed for "Registry".
    STATUS_CHOICES = [
        (STATUS_OPEN, pgettext_lazy("non-conformity status", "Open")),
        (STATUS_CLOSED, pgettext_lazy("non-conformity status", "Closed")),
    ]

    title = models.CharField(max_length=200)
    source = models.CharField(max_length=30, choices=SOURCE_CHOICES)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN
    )
    cost_center = models.ForeignKey(
        "registry.CostCenter",
        on_delete=models.PROTECT,
        related_name="non_conformities",
        null=True,
        blank=True,
    )
    # The origin object, when there is one. SET_NULL semantics by hand: a GFK
    # has no on_delete, so both parts are nullable and a vanished origin leaves
    # the finding standing rather than deleting the evidence with it.
    content_type = models.ForeignKey(
        ContentType, on_delete=models.SET_NULL, null=True, blank=True
    )
    object_id = models.UUIDField(null=True, blank=True)
    content_object = GenericForeignKey("content_type", "object_id")

    description = models.TextField()
    # Empty until someone investigates. ISO 10.2 wants the root cause on
    # record, but demanding it at creation would push people to write "pending"
    # -- which is worse than an empty field, because it looks answered.
    root_cause = models.TextField(blank=True)
    corrective_action = models.TextField(blank=True)
    detected_on = models.DateField(default=date.today)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    reported_to_dgac_at = models.DateField(null=True, blank=True)
    dgac_report_reference = models.CharField(max_length=100, blank=True)

    class Meta:
        verbose_name = _("non-conformity")
        verbose_name_plural = _("non-conformities")
        ordering = ["-detected_on", "-created_at"]
        indexes = [
            models.Index(fields=["status", "source"], name="compliance_nc_status_idx"),
            models.Index(
                fields=["content_type", "object_id"], name="compliance_nc_origin_idx"
            ),
        ]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("nonconformity-detail", kwargs={"pk": self.pk})

    def effectiveness_subject_is_closed(self):
        return self.status == self.STATUS_CLOSED

    @property
    def can_close(self):
        """ISO 10.2 asks for the root cause *and* the action taken. Closing
        without them would file a finding as handled while recording neither
        what caused it nor what was done -- the exact gap R6.2 closed for
        alerts."""
        return bool(self.root_cause.strip() and self.corrective_action.strip())

    def close(self, *, user=None):
        if not self.can_close:
            return False
        self.status = self.STATUS_CLOSED
        self.closed_at = timezone.now()
        self.closed_by = user
        self.start_effectiveness_clock()
        self.save(
            update_fields=[
                "status",
                "closed_at",
                "closed_by",
                "effectiveness_due_date",
                "updated_at",
            ]
        )
        return True

    def reopen(self):
        """Reopening is the answer to "did it work?" -- no."""
        self.status = self.STATUS_OPEN
        self.closed_at = None
        self.closed_by = None
        self.clear_effectiveness()
        self.save(
            update_fields=[
                "status",
                "closed_at",
                "closed_by",
                "effectiveness_due_date",
                "effectiveness_verified_at",
                "effectiveness_verified_by",
                "effectiveness_note",
                "updated_at",
            ]
        )


class Deliverable(BaseModel):
    """R7.4: quality control of what the survey produced (ISO 9001 8.5.1/8.6).

    AeroControl covers *permission to fly* and *the record that it flew*; this
    is the missing third thing -- **whether what was delivered is fit for use**.

    It does **not** store the product. Point clouds and orthophotos live in the
    processing pipeline and on `Z:`; what an auditor asks to see is the metrics
    and the validation signature, so that is what this holds.

    Anchored to `CostCenter` (the contract, always present) with an optional
    M2M to `FlightPermission`: a real deliverable can span several flights and
    several permits, and a permit may produce none, so a single FK to the
    permit would misrepresent both cases.

    **Acceptance is derived, never declared.** The thresholds live on the
    contract (`CostCenter.required_gsd_cm` and friends); this compares against
    them. A contract with no thresholds set has no gate, and the deliverable
    records its metrics without claiming a verdict -- which is what lets this
    ship before the negotiated numbers are known.

    Tenancy derives through `cost_center` (ADR-0001), so no own tenant FK.
    """

    STATUS_DRAFT = "draft"
    STATUS_VALIDATED = "validated"
    STATUS_RELEASED = "released"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = [
        (STATUS_DRAFT, _("Draft")),
        (STATUS_VALIDATED, _("Validated")),
        (STATUS_RELEASED, _("Released")),
        (STATUS_REJECTED, _("Rejected")),
    ]

    title = models.CharField(max_length=200)
    cost_center = models.ForeignKey(
        "registry.CostCenter",
        on_delete=models.PROTECT,
        related_name="deliverables",
    )
    flight_permissions = models.ManyToManyField(
        "operations.FlightPermission",
        blank=True,
        related_name="deliverables",
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT
    )

    # Achieved metrics. All optional: a deliverable is created when the survey
    # is processed and the numbers arrive from the pipeline afterwards.
    gsd_achieved_cm = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True
    )
    # Horizontal and vertical are accepted against different thresholds -- a
    # single combined RMSE cannot support the decision.
    rmse_xy_cm = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True
    )
    rmse_z_cm = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True
    )
    # An RMSE computed over the same points used to fit the model is not an
    # independent check. Keeping control points and check points apart is what
    # makes the number defensible in front of an auditor.
    gcp_count = models.PositiveIntegerField(null=True, blank=True)
    checkpoint_count = models.PositiveIntegerField(null=True, blank=True)
    coverage_pct = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    overlap_pct = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )

    validated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    validated_at = models.DateTimeField(null=True, blank=True)
    # The thresholds in force when this was validated, copied here on purpose.
    # Renegotiating a contract must not silently rewrite the verdict of work
    # already accepted -- same criterion as `purpose_legacy` in R3.1.
    applied_required_gsd_cm = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True, editable=False
    )
    applied_max_rmse_xy_cm = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True, editable=False
    )
    applied_max_rmse_z_cm = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True, editable=False
    )
    # A release that goes out below the agreed criteria has to be a decision
    # someone signed, not a silent override -- see `can_release` below.
    release_waiver_reason = models.TextField(blank=True)

    class Meta:
        verbose_name = _("deliverable")
        verbose_name_plural = _("deliverables")
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["cost_center", "status"], name="compliance_deliv_cc_idx"
            )
        ]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("deliverable-detail", kwargs={"pk": self.pk})

    def _thresholds(self):
        """The thresholds to judge against: the frozen ones once validated,
        the contract's current ones before that."""
        if self.validated_at is not None:
            return (
                self.applied_required_gsd_cm,
                self.applied_max_rmse_xy_cm,
                self.applied_max_rmse_z_cm,
            )
        return (
            self.cost_center.required_gsd_cm,
            self.cost_center.max_rmse_xy_cm,
            self.cost_center.max_rmse_z_cm,
        )

    def acceptance_checks(self):
        """[(label, achieved, threshold, passed), ...] for each criterion the
        contract defines and this deliverable has a measurement for.

        A criterion with no threshold, or no measurement, is left out entirely
        rather than counted as passed: "not assessed" and "meets" are different
        statements, and merging them is how a gate quietly stops gating.
        """
        required_gsd, max_xy, max_z = self._thresholds()
        candidates = [
            # GSD is a resolution: *smaller is better*, so achieving less than
            # or equal to what was required is the pass condition -- the same
            # direction as the RMSE limits, which is why one comparison works
            # for all three.
            (_("GSD (cm)"), self.gsd_achieved_cm, required_gsd),
            (_("Horizontal RMSE (cm)"), self.rmse_xy_cm, max_xy),
            (_("Vertical RMSE (cm)"), self.rmse_z_cm, max_z),
        ]
        return [
            (label, achieved, threshold, achieved <= threshold)
            for label, achieved, threshold in candidates
            if achieved is not None and threshold is not None
        ]

    @property
    def meets_acceptance_criteria(self):
        """True/False, or **None when nothing could be assessed**.

        None is not a failure: it means the contract set no thresholds, or the
        metrics have not arrived yet. Rendering it as a failure would flag
        every deliverable of every contract that has not negotiated criteria.
        """
        checks = self.acceptance_checks()
        if not checks:
            return None
        return all(passed for *_rest, passed in checks)

    @property
    def can_release(self):
        """Whether releasing is allowed as things stand.

        Blocked only on a *measured* failure. An unassessed deliverable
        (`None`) releases freely: with no agreed criteria there is nothing to
        enforce, and inventing one here would be a gate nobody agreed to.
        Overriding a real failure needs `release_waiver_reason` -- the same
        shape as R2.4's document gate, one step from a hard block to a signed
        exception.
        """
        if self.meets_acceptance_criteria is False:
            return bool(self.release_waiver_reason.strip())
        return True

    def validate_quality(self, *, user=None):
        """Sign the internal validation and freeze the thresholds applied."""
        self.status = self.STATUS_VALIDATED
        self.validated_by = user
        self.validated_at = timezone.now()
        self.applied_required_gsd_cm = self.cost_center.required_gsd_cm
        self.applied_max_rmse_xy_cm = self.cost_center.max_rmse_xy_cm
        self.applied_max_rmse_z_cm = self.cost_center.max_rmse_z_cm
        self.save(
            update_fields=[
                "status",
                "validated_by",
                "validated_at",
                "applied_required_gsd_cm",
                "applied_max_rmse_xy_cm",
                "applied_max_rmse_z_cm",
                "updated_at",
            ]
        )
