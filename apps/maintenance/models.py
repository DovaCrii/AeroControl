from django.db import models
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from apps.core.models import BaseModel
from apps.registry.models import Aircraft


class MaintenanceRecord(BaseModel):
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

    @property
    def is_incomplete(self):
        """LV-8e: needs planning -- flagged as 'to be defined' or missing a
        scheduled date, and not already finished."""
        return self.status != "completed" and (
            self.maintenance_type == "to_be_defined" or self.scheduled_date is None
        )

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
    changed_at = models.DateTimeField(auto_now_add=True)
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
