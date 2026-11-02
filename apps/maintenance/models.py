import re
import unicodedata

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import models, transaction
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from apps.core.models import BaseModel
from apps.core.status_history import StatusHistoryMixin
from apps.registry.models import Aircraft


class MaintenanceRecord(StatusHistoryMixin, BaseModel):
    # T1.3: el historial de estados (`MaintenanceHistory`) lo escribe
    # `StatusHistoryMixin` dentro del guardado, y ya no una señal `pre_save`. La
    # otra señal de esta app (`sync_maintenance_status_transition`) sigue siendo
    # `pre_save`, pero ahora corre **dentro** de esa transacción: si el guardado
    # falla, lo que le hizo a la aeronave se deshace con él.
    STATUS_HISTORY = ("maintenance.MaintenanceHistory", "record", "status")

    TYPES = [
        # LV-8a: a maintenance that is known to be needed but not yet specified
        # (no date/assignee decided). Listed first so it reads as the "inbox"
        # state before the work is planned.
        ("to_be_defined", _("To be defined")),
        ("scheduled", _("Scheduled")),
        ("unscheduled", _("Unscheduled")),
        ("emergency", _("Emergency")),
    ]
    # R5.1: two paths from "pending", chosen at send time -- most maintenance
    # is resolved in-house (the original flat in_progress -> completed) and
    # forcing 5 clicks on a 10-minute in-house check would be friction for no
    # reason. The workshop chain (sent -> at_workshop -> finished ->
    # in_transit) is only for equipment that actually leaves the base;
    # "completed" is the single shared terminal state either path ends at
    # (generate_alerts' generic "still open" check on `status` keeps working
    # unchanged: nothing here is terminal except "completed").
    STATUSES = [
        ("pending", _("Pending")),
        ("in_progress", _("In progress")),
        ("sent", _("Sent to workshop")),
        ("at_workshop", _("At the workshop")),
        ("finished", _("Finished at workshop")),
        ("in_transit", _("In transit back")),
        ("completed", _("Completed")),
    ]
    # The aircraft is physically away from headquarters in all of these --
    # see apps/maintenance/signals.py, which drives Aircraft.current_location/
    # status at the two edges of this set (entering at "sent", leaving at
    # "completed" from "in_transit"). `workshop_dwell_is_overdue` below flags
    # a record that has dwelled in one of these too long.
    # LV-90: "completed" is the single terminal state both paths end at, which
    # the comment above already said -- now the alert engine reads it from here
    # instead of from a literal list of its own.
    TERMINAL_STATUSES = frozenset({"completed"})
    WORKSHOP_STATUSES = frozenset({"sent", "at_workshop", "finished", "in_transit"})
    # How long is too long in one workshop state before it deserves a visual
    # flag (record_list.html/record_detail.html). A fixed constant, not an
    # AlertRule: turning this into an admin-configurable rule would need the
    # generic AlertRule date-field branch (`field <= today + N days`, an
    # "upcoming expiry" query) to also support the opposite direction ("has
    # this timestamp been in the past for more than N days") for every other
    # watched model, not just this one -- more machinery than a first cut
    # earns. Revisit only if this constant proves wrong in practice.
    WORKSHOP_DWELL_ALERT_DAYS = 5
    aircraft = models.ForeignKey(
        Aircraft, on_delete=models.PROTECT, related_name="maintenance_records"
    )
    maintenance_type = models.CharField(max_length=20, choices=TYPES)
    description = models.TextField()
    # LV-8b: a "to be defined" record legitimately has neither a scheduled date
    # nor an assignee yet -- both optional so the gap can be recorded and then
    # surfaced (LV-8e) instead of forcing a placeholder.
    scheduled_date = models.DateField(null=True, blank=True)
    completed_date = models.DateField(null=True, blank=True)
    performed_by = models.CharField(max_length=150, blank=True)
    status = models.CharField(max_length=20, choices=STATUSES, default="pending")
    # R5.1: when `status` last changed -- apps/maintenance/signals.py bumps
    # this on every real transition. Backfilled from `updated_at` for rows
    # that predate this field (migration 0007); not exact for their history,
    # but it is the best available proxy and only matters going forward for
    # rows created after this field existed.
    status_changed_at = models.DateTimeField(null=True, blank=True, editable=False)

    @classmethod
    def needing_planning(cls, queryset):
        """LV-310: the rows that still need planning, as a queryset filter.

        One definition for the panel's "Maintenance to define" count **and** the
        list its chip links to (`?needs_planning=1`): two copies of the criterion
        are how a number and the rows behind it stop agreeing. Same rule as
        `is_incomplete`, expressed for the database.
        """
        return queryset.filter(status__in=["pending", "in_progress"]).filter(
            models.Q(maintenance_type="to_be_defined")
            | models.Q(scheduled_date__isnull=True)
        )

    @property
    def is_incomplete(self):
        """LV-8e: needs planning -- flagged as 'to be defined' or missing a
        scheduled date, and not already finished."""
        return self.status != "completed" and (
            self.maintenance_type == "to_be_defined" or self.scheduled_date is None
        )

    @property
    def sent_without_head_office_notice(self):
        """LV-383 PR 4: True when the active workshop intake says a cost center
        sent the unit by itself. False with no intake (the reverse one-to-one
        raises when absent, even after `select_related`)."""
        try:
            intake = self.workshop_intake
        except ObjectDoesNotExist:
            return False
        return intake.was_sent_without_head_office_notice

    @property
    def is_at_workshop_stage(self):
        """Whether the aircraft is currently away in the workshop chain --
        used by the templates to badge the status distinctly from the short
        in-house path's pending/in_progress/completed."""
        return self.status in self.WORKSHOP_STATUSES

    @property
    def days_in_current_status(self):
        """None when unknown (no status_changed_at on file yet)."""
        if self.status_changed_at is None:
            return None
        return (timezone.now() - self.status_changed_at).days

    @property
    def workshop_dwell_is_overdue(self):
        """R5.1: flags a record that has sat in one workshop state too long
        -- a visual cue on the list/detail pages, not a formal Alert (see
        WORKSHOP_DWELL_ALERT_DAYS)."""
        return (
            self.status in self.WORKSHOP_STATUSES
            and self.days_in_current_status is not None
            and self.days_in_current_status >= self.WORKSHOP_DWELL_ALERT_DAYS
        )

    class Meta:
        verbose_name = _("maintenance record")
        verbose_name_plural = _("maintenance records")
        # The calendar filters (scheduled_date, is_active) on every feed request.
        indexes = [
            models.Index(
                fields=["scheduled_date", "is_active"], name="maint_record_date_idx"
            )
        ]

    def __str__(self):
        return f"{self.get_maintenance_type_display()} · {self.aircraft}"

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("maintenance-detail", kwargs={"pk": self.pk})

    # LV-82: the two paths a record can actually take. Both start at `pending`
    # and end at `completed`; what differs is whether the equipment leaves the
    # base. Declared here, next to STATUSES, and **never spelled out in a
    # template** -- a hand-written list drifting from the real choices is the
    # R1.1 defect.
    IN_HOUSE_FLOW = ["pending", "in_progress", "completed"]
    WORKSHOP_FLOW = [
        "pending",
        "sent",
        "at_workshop",
        "finished",
        "in_transit",
        "completed",
    ]

    def status_flow(self):
        """Which of the two paths this record is on.

        **This is why maintenance could not simply adopt `StatusFlowMixin`**
        (LV-72/LV-81): that mixin takes one class-level flow, and here the flow
        is a property of the individual record. Drawing all seven statuses as
        one line would promise an in-house repair a trip to a workshop it is
        never making -- the mixin's own rule is that a stepper must not claim a
        progression that does not exist.

        Decided by what the record *did*, not by what it might do: its current
        status first, then its history, so a completed record still shows the
        path it actually took. A record still at `pending` has not diverged yet
        and shows the short path -- the common case -- and switches the moment
        it is sent to a workshop.
        """
        if self.status in self.WORKSHOP_STATUSES:
            return self.WORKSHOP_FLOW
        if (
            self.pk
            and self.history.filter(new_status__in=self.WORKSHOP_STATUSES).exists()
        ):
            return self.WORKSHOP_FLOW
        return self.IN_HOUSE_FLOW

    def status_steps(self):
        """[{code, label, state}] for the path this record is on."""
        from apps.core.models import status_steps_for

        return status_steps_for(
            choices=self.STATUSES, flow=self.status_flow(), current=self.status
        )

    @classmethod
    def register_workshop_intake(cls, aircraft, data, user=None, existing_record=None):
        """Record that `aircraft` was received at a workshop and move the file along.

        The business rule lives here (fat model), not in a view: the intake is
        hung on the open record when there is one (`existing_record`, or the
        aircraft's latest open `pending`/`sent` record that has no intake yet),
        and a new `unscheduled` record is created only when there is none.
        The record is then walked pending -> sent -> at_workshop with a
        `save()` per state: creating a record straight in `sent` would NOT move
        the aircraft (the pre_save signal needs a real transition) and the
        history mixin writes nothing on creation. A record that is already in
        `sent`/`at_workshop` is not walked again.

        `data` holds the `WorkshopIntake` fields (workshop_name, received_at,
        sent_by, quote_*, ...). If an active intake with the same (workshop,
        order) exists for this aircraft it is COMPLETED (`merge_proposal`: only
        empty fields are filled), not duplicated. Returns the saved `WorkshopIntake`.
        """
        with transaction.atomic():
            intake = WorkshopIntake.find_by_order(
                data.get("workshop_name", ""), data.get("workshop_order", "")
            )
            if intake is not None:
                # Same job already registered (e.g. its quote arrived first):
                # complete it instead of failing on the duplicate.
                record = cls.objects.select_for_update().get(pk=intake.record_id)
                if record.aircraft_id != aircraft.pk:
                    raise ValidationError(
                        _(
                            "An intake with this workshop and order number is "
                            "already registered."
                        )
                    )
                intake.merge_proposal(**data)
            else:
                record = cls._record_for_intake(aircraft, data, existing_record)
                intake = WorkshopIntake(record=record, **data)
            intake.full_clean()
            intake.save()
            actor = user.get_username() if user is not None else "system"
            for source, target in (("pending", "sent"), ("sent", "at_workshop")):
                if record.status != source:
                    continue
                record._changed_by = actor
                record._changed_by_user = user
                record._transition_notes = ""
                record.status = target
                record.save()
            return intake

    # Outcomes of `void_workshop_intake` for the aircraft's state.
    VOID_AIRCRAFT_RESTORED = "restored"
    VOID_AIRCRAFT_KEPT = "kept"
    VOID_AIRCRAFT_UNTOUCHED = "untouched"

    def void_workshop_intake(self, user=None):
        """LV-388: annul the workshop intake of this record (archive, never delete).

        The intake and the record are archived (`is_active=False`); nothing is
        deleted and the documents stay on the aircraft. Returns one of the
        `VOID_AIRCRAFT_*` outcomes:

        * `untouched`: the record never moved the aircraft out (it is not in a
          workshop state), so the aircraft is left alone.
        * `restored`: the record was in a workshop state, no other active record
          keeps the aircraft there and the aircraft is still marked away
          (`maintenance`/`maintenance`): it goes back to `headquarters`/`active`,
          the same edge `sync_maintenance_status_transition` applies when a
          record completes from `in_transit`. The previous state is not stored
          anywhere, so that edge is the only certain value.
        * `kept`: anything else (another open workshop record, or somebody
          already changed the aircraft by hand): the aircraft is not touched and
          the caller should say so.

        Raises `ValidationError` when there is no active intake to annul.
        """
        from apps.compliance.alerts import resolve_open_alerts_for

        with transaction.atomic():
            record = type(self).objects.select_for_update().get(pk=self.pk)
            intake = (
                WorkshopIntake.objects.select_for_update()
                .filter(record=record, is_active=True)
                .first()
            )
            if intake is None or not record.is_active:
                raise ValidationError(_("This record has no active workshop intake."))
            intake.is_active = False
            intake.save(update_fields=["is_active", "updated_at"])
            record.is_active = False
            record.save(update_fields=["is_active", "updated_at"])
            resolve_open_alerts_for(record)
            outcome = record._release_aircraft(user)
        self.is_active = False
        return outcome

    # Kinds of annulment `void_kind` can report (LV-389).
    VOID_KIND_INTAKE = "intake"
    VOID_KIND_PENDING = "pending"

    def void_kind(self):
        """What annulling this record would mean, or `None` when it cannot be.

        * `intake`: an active workshop intake (LV-388).
        * `pending`: a `pending` record that was never started nor sent: no status
          history and no workshop intake, so nothing ever happened to it.

        Anything else (in progress, sent, completed, or a pending record with
        history) is not annullable: those carry real work that must be closed
        through its own flow. Uses `history.all()` so a list can prefetch it.
        """
        if not self.is_active or not self.pk:
            return None
        try:
            intake = self.workshop_intake
        except ObjectDoesNotExist:
            intake = None
        if intake is not None and intake.is_active:
            return self.VOID_KIND_INTAKE
        if intake is None and self.status == "pending" and not self.history.all():
            return self.VOID_KIND_PENDING
        return None

    @property
    def can_be_voided(self):
        return self.void_kind() is not None

    def void(self, user=None):
        """LV-389: annul the record (archive, never delete). Returns `(kind, outcome)`.

        `outcome` is a `VOID_AIRCRAFT_*` value; a never-started pending record did
        not move the aircraft, so it is always `untouched`. Raises
        `ValidationError` when the record cannot be annulled.
        """
        from apps.compliance.alerts import resolve_open_alerts_for

        kind = self.void_kind()
        if kind == self.VOID_KIND_INTAKE:
            return kind, self.void_workshop_intake(user=user)
        if kind == self.VOID_KIND_PENDING:
            with transaction.atomic():
                record = type(self).objects.select_for_update().get(pk=self.pk)
                if record.void_kind() != self.VOID_KIND_PENDING:
                    raise ValidationError(_("This record cannot be voided."))
                record.is_active = False
                record.save(update_fields=["is_active", "updated_at"])
                resolve_open_alerts_for(record)
            self.is_active = False
            return kind, self.VOID_AIRCRAFT_UNTOUCHED
        raise ValidationError(_("This record cannot be voided."))

    def _release_aircraft(self, user):
        if self.status not in self.WORKSHOP_STATUSES:
            return self.VOID_AIRCRAFT_UNTOUCHED
        aircraft = (
            type(self.aircraft).objects.select_for_update().get(pk=self.aircraft_id)
        )
        still_held = (
            type(self)
            .objects.filter(
                aircraft_id=self.aircraft_id,
                is_active=True,
                status__in=self.WORKSHOP_STATUSES,
            )
            .exclude(pk=self.pk)
            .exists()
        )
        if (
            still_held
            or aircraft.current_location != "maintenance"
            or aircraft.status != "maintenance"
        ):
            return self.VOID_AIRCRAFT_KEPT
        aircraft.current_location = "headquarters"
        aircraft.current_site = None
        aircraft.status = "active"
        aircraft._changed_by_user = user
        aircraft.save(
            update_fields=[
                "current_location",
                "current_site",
                "status",
                "updated_at",
            ]
        )
        return self.VOID_AIRCRAFT_RESTORED

    @classmethod
    def _record_for_intake(cls, aircraft, data, existing_record):
        if existing_record is not None:
            record = cls.objects.select_for_update().get(pk=existing_record.pk)
            if record.aircraft_id != aircraft.pk:
                raise ValidationError(
                    _("The maintenance record does not belong to this aircraft.")
                )
            if record.status not in ("pending", "sent", "at_workshop"):
                raise ValidationError(
                    _("This maintenance record is no longer open for an intake.")
                )
            if WorkshopIntake.objects.filter(record=record).exists():
                raise ValidationError(
                    _("This maintenance record already has a workshop intake.")
                )
            return record
        record = (
            cls.objects.select_for_update()
            .filter(
                aircraft=aircraft,
                is_active=True,
                status__in=["pending", "sent"],
                workshop_intake__isnull=True,
            )
            .order_by("-created_at")
            .first()
        )
        if record is not None:
            return record
        findings = (data.get("findings") or data.get("diagnosis") or "").strip()
        return cls.objects.create(
            aircraft=aircraft,
            maintenance_type="unscheduled",
            status="pending",
            description=findings or "Received at workshop (intake)",
            performed_by=data.get("workshop_name", ""),
        )


class MaintenanceHistory(BaseModel):
    # LV-82: same tie-breaker as PermissionHistory/InsuranceHistory. `created_at`
    # alone cannot order two rows created moments apart -- on this machine
    # `timezone.now()` returns the identical value across rapid successive calls
    # and SQL gives no ordering guarantee for ties on a non-unique column, so a
    # record moved twice in one action could print its own history backwards.
    sequence = models.PositiveBigIntegerField(editable=False, default=0)
    record = models.ForeignKey(
        MaintenanceRecord, on_delete=models.PROTECT, related_name="history"
    )
    # LV-91: `changed_at` removed. It was a second `auto_now_add` beside the
    # `created_at` this model already inherits from BaseModel -- two columns that
    # always held the same value, so the next person had to work out which one
    # was the real one, and an `ORDER BY` on the wrong one raises no error.
    # `PermissionHistory` dropped its own in `operations/0003`; this is the same
    # cleanup, four months late.
    # LV-82: `choices` added. This is the R2.5 defect, still open here after it
    # was fixed for the permit: without them Django never generates
    # `get_new_status_display`, so the history table on the maintenance fiche
    # printed the raw stored codes ("at_workshop", "in_transit") inside an
    # otherwise Spanish page.
    previous_status = models.CharField(
        max_length=20, choices=MaintenanceRecord.STATUSES
    )
    new_status = models.CharField(max_length=20, choices=MaintenanceRecord.STATUSES)
    changed_by = models.CharField(max_length=150)
    changed_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="maintenance_history_events",
    )

    class Meta:
        verbose_name = _("maintenance history")
        verbose_name_plural = _("maintenance histories")
        ordering = ["-sequence"]

    def __str__(self):
        return f"{self.record_id}: {self.previous_status} → {self.new_status}"

    def save(self, *args, **kwargs):
        if self._state.adding:
            latest = MaintenanceHistory.objects.order_by("-sequence").first()
            self.sequence = (latest.sequence if latest else 0) + 1
        return super().save(*args, **kwargs)


def normalize_workshop_name(value):
    """Lowercase, accents stripped, whitespace collapsed: the duplicate-guard key."""
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).strip().lower()


def normalize_workshop_order(value):
    """Upper case with every whitespace character removed."""
    return re.sub(r"\s+", "", value or "").upper()


class WorkshopIntake(BaseModel):
    """What was received when an aircraft entered a workshop (service intake).

    One per maintenance record. `delivered_by` is personal data: it lives only
    in the database, never in `__str__`, logs or messages.
    """

    SENT_BY_COST_CENTER = "cost_center"
    SENT_BY_CHOICES = [
        (SENT_BY_COST_CENTER, _("A cost center")),
        ("head_office", _("Head office")),
        ("unknown", _("Unknown")),
    ]

    record = models.OneToOneField(
        MaintenanceRecord, on_delete=models.PROTECT, related_name="workshop_intake"
    )
    workshop_name = models.CharField(_("workshop"), max_length=150)
    # Derived from `workshop_name` in save(); the duplicate guard compares it.
    workshop_key = models.CharField(max_length=150, editable=False)
    workshop_order = models.CharField(_("workshop order"), max_length=60, blank=True)
    # Optional since PR 2b: a team that goes straight to the workshop first
    # produces a quote, with no reception document and so no reception date.
    received_at = models.DateTimeField(_("received at"), null=True, blank=True)
    sent_by = models.CharField(
        _("sent by"), max_length=20, choices=SENT_BY_CHOICES, default="unknown"
    )
    sender_cost_center = models.ForeignKey(
        "registry.CostCenter",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("sending cost center"),
    )
    delivered_by = models.CharField(_("delivered by"), max_length=150, blank=True)
    accessories = models.TextField(_("accessories"), blank=True)
    findings = models.TextField(_("findings"), blank=True)
    reader = models.CharField(_("reader"), max_length=30, blank=True)
    # Quote of the workshop (all optional). Amounts are Chilean pesos, no decimals.
    quote_date = models.DateField(_("quote date"), null=True, blank=True)
    quote_valid_until = models.DateField(_("quote valid until"), null=True, blank=True)
    quote_net = models.DecimalField(
        _("quote net amount"), max_digits=12, decimal_places=0, null=True, blank=True
    )
    quote_vat = models.DecimalField(
        _("quote VAT"), max_digits=12, decimal_places=0, null=True, blank=True
    )
    quote_total = models.DecimalField(
        _("quote total"), max_digits=12, decimal_places=0, null=True, blank=True
    )
    quote_lead_time = models.CharField(_("quote lead time"), max_length=120, blank=True)
    quote_warranty = models.CharField(_("quote warranty"), max_length=60, blank=True)
    diagnosis = models.TextField(_("diagnosis"), blank=True)
    quote_document = models.ForeignKey(
        "compliance.Document",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("quote document"),
    )
    source_document = models.ForeignKey(
        "compliance.Document",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("source document"),
    )

    class Meta:
        verbose_name = _("workshop intake")
        verbose_name_plural = _("workshop intakes")
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(sent_by="cost_center", sender_cost_center__isnull=False)
                    | (
                        ~models.Q(sent_by="cost_center")
                        & models.Q(sender_cost_center__isnull=True)
                    )
                ),
                name="workshop_intake_cc_matches_sent_by",
            ),
            models.UniqueConstraint(
                fields=["workshop_key", "workshop_order"],
                condition=models.Q(is_active=True) & ~models.Q(workshop_order=""),
                name="workshop_intake_unique_order",
            ),
        ]

    def __str__(self):
        # Deliberately without `delivered_by` (personal data).
        return f"{self.workshop_name} · {self.record_id}"

    @property
    def was_sent_without_head_office_notice(self):
        """LV-383 PR 4: a cost center sent the unit on its own, so head office
        was not told. `head_office` and `unknown` do not count: the second one
        is "nobody knows", which is not the same as "nobody was told"."""
        return self.is_active and self.sent_by == self.SENT_BY_COST_CENTER

    # Fields `merge_proposal` may fill; `sent_by`/`sender_cost_center` go together.
    MERGEABLE_FIELDS = (
        "delivered_by",
        "accessories",
        "findings",
        "reader",
        "received_at",
        "source_document",
        "quote_date",
        "quote_valid_until",
        "quote_net",
        "quote_vat",
        "quote_total",
        "quote_lead_time",
        "quote_warranty",
        "diagnosis",
        "quote_document",
    )

    @classmethod
    def find_by_order(cls, workshop_name, workshop_order):
        """The active intake of this (workshop, order), or `None` without an order."""
        order = normalize_workshop_order(workshop_order)
        if not order:
            return None
        return (
            cls.objects.select_for_update()
            .filter(
                workshop_key=normalize_workshop_name(workshop_name),
                workshop_order=order,
                is_active=True,
            )
            .first()
        )

    def merge_proposal(self, **data):
        """Fill the EMPTY fields from `data`; never overwrite what is already there.

        A second document of the same job (the quote after the reception, or the
        other way round) completes the intake. Empty means `None` or `""`; the
        origin (`sent_by` + cost center) is only taken while it is `unknown`.
        Returns the names of the fields that changed (not saved: the caller
        validates and saves).
        """
        changed = []
        for name in self.MERGEABLE_FIELDS:
            value = data.get(name)
            if value in (None, ""):
                continue
            if getattr(self, name) in (None, ""):
                setattr(self, name, value)
                changed.append(name)
        new_origin = data.get("sent_by", "unknown")
        if self.sent_by == "unknown" and new_origin != "unknown":
            self.sent_by = new_origin
            self.sender_cost_center = data.get("sender_cost_center")
            changed += ["sent_by", "sender_cost_center"]
        return changed

    def _normalize(self):
        self.workshop_key = normalize_workshop_name(self.workshop_name)
        self.workshop_order = normalize_workshop_order(self.workshop_order)

    def clean(self):
        super().clean()
        self._normalize()
        errors = {}
        if self.sent_by == "cost_center" and self.sender_cost_center_id is None:
            errors["sender_cost_center"] = _(
                "Choose the cost center that sent the equipment."
            )
        elif self.sent_by != "cost_center" and self.sender_cost_center_id is not None:
            errors["sender_cost_center"] = _(
                "A cost center only applies when the equipment was sent by one."
            )
        if self.workshop_order and self.is_active:
            clash = WorkshopIntake.objects.filter(
                workshop_key=self.workshop_key,
                workshop_order=self.workshop_order,
                is_active=True,
            ).exclude(pk=self.pk)
            if clash.exists():
                errors["workshop_order"] = _(
                    "An intake with this workshop and order number is already "
                    "registered."
                )
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self._normalize()
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            kwargs["update_fields"] = {*update_fields, "workshop_key", "workshop_order"}
        return super().save(*args, **kwargs)
