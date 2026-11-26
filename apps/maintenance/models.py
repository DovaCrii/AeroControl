import calendar
import re
import unicodedata
from decimal import Decimal

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext
from apps.core.models import BaseModel
from apps.core.status_history import StatusHistoryMixin
from apps.registry.models import Aircraft

# Act. 19, Annex F: the three levels of the maintenance programme. The order is
# the rank: a higher level includes the lower ones (medium = basic + wear parts,
# advanced = medium + main components), so completing it restarts their clocks.
PROGRAM_LEVELS = [
    ("basic", _("Basic")),
    ("medium", _("Medium")),
    ("advanced", _("Advanced")),
]
# What a record can be classified as: the three programme levels plus two kinds
# of work that are not part of the programme and so never restart a clock.
RECORD_LEVELS = PROGRAM_LEVELS + [
    ("repair", _("Repair")),
    ("inspection", _("Inspection")),
]
LEVEL_RANK = {code: rank for rank, (code, _label) in enumerate(PROGRAM_LEVELS, 1)}


def add_months(day, months):
    """`day` plus `months` calendar months; the day is clamped to the month's end
    (31 Aug + 6 months is 28/29 Feb, not an error)."""
    index = day.year * 12 + (day.month - 1) + months
    year, month = divmod(index, 12)
    month += 1
    return day.replace(
        year=year, month=month, day=min(day.day, calendar.monthrange(year, month)[1])
    )


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
    # Act. 19 (LV-443): the level of the work, the aircraft's flight hours when it
    # was done (read from the maintenance certificate) and that certificate's number.
    # All optional: a record without a level is ordinary maintenance and stays
    # outside the programme.
    level = models.CharField(
        max_length=12, choices=RECORD_LEVELS, blank=True, verbose_name=_("Level")
    )
    hours_at = models.DecimalField(
        max_digits=8,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        verbose_name=_("Aircraft hours"),
    )
    certificate_number = models.CharField(
        max_length=60, blank=True, verbose_name=_("Certificate number")
    )

    @classmethod
    def last_completed_for_level(cls, aircraft, level):
        """The record that last restarted `level`'s clock, or `None`.

        A completed record of a **higher** level counts too (advanced includes
        medium includes basic), so the newest completed record whose rank is at
        least `level`'s is the one that matters. Archived records and the ones
        without a completion date do not count.
        """
        rank = LEVEL_RANK.get(level)
        if rank is None:
            return None
        levels = [code for code, value in LEVEL_RANK.items() if value >= rank]
        return (
            cls.objects.filter(
                aircraft=aircraft,
                is_active=True,
                status="completed",
                level__in=levels,
                completed_date__isnull=False,
            )
            .order_by("-completed_date", "-created_at")
            .first()
        )

    def schedule_next_in_level(self):
        """Open the next scheduled record of every level this completion restarts.

        Returns the records it created. The follow-up is an ordinary `scheduled`
        record dated `completed_date + interval_months`, so the existing alert
        rule on `scheduled_date` ("Mantenimiento programado") warns about it with
        no new engine. Per level:

        * an open record of the same level already exists -> nothing is created
          (completing twice never duplicates the plan);
        * a *lower* level (restarted by this one) has an open `pending` record
          dated sooner than the new due date -> it is moved to that date;
        * a level whose programme has no month interval (hours only) gets no
          dated record: its hours are only displayed.
        """
        rank = LEVEL_RANK.get(self.level)
        if rank is None or self.status != "completed" or self.completed_date is None:
            return []
        programs = MaintenanceProgram.for_aircraft(self.aircraft)
        created = []
        with transaction.atomic():
            for level, level_rank in LEVEL_RANK.items():
                program = programs.get(level)
                if level_rank > rank or program is None or not program.interval_months:
                    continue
                due = add_months(self.completed_date, program.interval_months)
                open_records = (
                    type(self)
                    .objects.filter(aircraft=self.aircraft, level=level, is_active=True)
                    .exclude(status="completed")
                )
                existing = open_records.first()
                if existing is None:
                    created.append(
                        type(self).objects.create(
                            aircraft=self.aircraft,
                            maintenance_type="scheduled",
                            level=level,
                            description=gettext(
                                "Scheduled %(level)s maintenance (maintenance programme)"
                            )
                            % {"level": dict(PROGRAM_LEVELS)[level]},
                            scheduled_date=due,
                            status="pending",
                        )
                    )
                elif (
                    level_rank < rank
                    and existing.status == "pending"
                    and existing.scheduled_date is not None
                    and existing.scheduled_date < due
                ):
                    existing.scheduled_date = due
                    existing.save(update_fields=["scheduled_date", "updated_at"])
        return created

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

    # LV-460: outcomes of `register_certificate`.
    CERTIFICATE_CLOSED = "closed"
    CERTIFICATE_CREATED = "created"
    CERTIFICATE_ALREADY = "already"

    @classmethod
    def find_certificate(cls, aircraft, certificate_number):
        """The active record of `aircraft` that already carries this certificate."""
        number = (certificate_number or "").strip()
        if not number:
            return None
        return (
            cls.objects.filter(
                aircraft=aircraft, is_active=True, certificate_number__iexact=number
            )
            .order_by("-created_at")
            .first()
        )

    @classmethod
    def register_certificate(cls, aircraft, data, user=None):
        """LV-460: record a workshop's maintenance certificate against `aircraft`.

        Returns `(record, outcome)`, one of the `CERTIFICATE_*` values:

        * `already`: an active record of this aircraft already carries the same
          certificate number. Nothing is changed (the same certificate uploaded
          twice must not complete two maintenances).
        * `closed`: an open record was completed. Which one, in this order: the
          one whose workshop intake has this (workshop, order) -- the workshop
          prints the same number on the intake and on the certificate --; else
          the aircraft's latest record in a workshop state; else, when `level`
          is given, its open `pending`/`in_progress` record of that level (the
          follow-up the programme scheduled, which this work fulfils). The record
          is walked to `completed` **one state per `save()`**, like
          `register_workshop_intake`: the signal only brings the aircraft back to
          headquarters on the real `in_transit -> completed` edge, and the history
          mixin writes one row per step.
        * `created`: there was nothing open, so a new record is created already
          completed. It does not move the aircraft (it never left on paper).

        `data` holds `completed_date` (the certificate's issue date),
        `certificate_number`, `performed_by`, `hours_at`, `level`,
        `maintenance_type`, `notes` and `workshop_name`. A completed level then
        schedules the next one (`schedule_next_in_level`) and the record's open
        alerts are resolved, exactly as closing by hand does.
        """
        from apps.compliance.alerts import resolve_open_alerts_for

        number = (data.get("certificate_number") or "").strip()
        completed_date = data.get("completed_date")
        if not number:
            raise ValidationError(_("The certificate number is required."))
        if completed_date is None:
            raise ValidationError(_("The issue date is required."))
        if completed_date > timezone.localdate():
            raise ValidationError(_("The issue date cannot be in the future."))
        hours = data.get("hours_at")
        if hours is not None and hours < 0:
            raise ValidationError(_("The aircraft hours cannot be negative."))

        with transaction.atomic():
            # Serializes two confirmations of the same certificate.
            type(aircraft).objects.select_for_update().filter(pk=aircraft.pk).first()
            existing = cls.find_certificate(aircraft, number)
            if existing is not None:
                return existing, cls.CERTIFICATE_ALREADY
            record = cls._record_for_certificate(aircraft, data, number)
            notes = (data.get("notes") or "").strip()
            if record is None:
                record = cls.objects.create(
                    aircraft=aircraft,
                    maintenance_type=data.get("maintenance_type") or "scheduled",
                    description=gettext(
                        "Maintenance certified by %(workshop)s (certificate %(number)s)"
                    )
                    % {
                        "workshop": data.get("performed_by") or "—",
                        "number": number,
                    },
                    status="completed",
                    completed_date=completed_date,
                    performed_by=data.get("performed_by") or "",
                    level=data.get("level") or "",
                    hours_at=hours,
                    certificate_number=number,
                    notes=notes,
                )
                outcome = cls.CERTIFICATE_CREATED
            else:
                record._complete_with_certificate(data, number, notes, user)
                outcome = cls.CERTIFICATE_CLOSED
            record.schedule_next_in_level()
            resolve_open_alerts_for(record)
        return record, outcome

    @classmethod
    def _record_for_certificate(cls, aircraft, data, number):
        open_records = cls.objects.select_for_update().filter(
            aircraft=aircraft, is_active=True
        )
        intake = WorkshopIntake.find_by_order(data.get("workshop_name", ""), number)
        if intake is not None:
            record = open_records.filter(pk=intake.record_id).first()
            if record is not None and record.status not in cls.TERMINAL_STATUSES:
                return record
        record = (
            open_records.filter(status__in=cls.WORKSHOP_STATUSES)
            .order_by("-status_changed_at", "-created_at")
            .first()
        )
        if record is not None:
            return record
        level = data.get("level")
        if level in LEVEL_RANK:
            return (
                open_records.filter(level=level, status__in=["pending", "in_progress"])
                .order_by("scheduled_date", "created_at")
                .first()
            )
        return None

    def _complete_with_certificate(self, data, number, notes, user):
        flow = (
            self.WORKSHOP_FLOW
            if self.status in self.WORKSHOP_STATUSES
            else self.IN_HOUSE_FLOW
        )
        remaining = flow[flow.index(self.status) + 1 :]
        actor = user.get_username() if user is not None else "system"
        for status in remaining:
            self._changed_by = actor
            self._changed_by_user = user
            self._transition_notes = ""
            self.status = status
            if status == "completed":
                self.completed_date = data["completed_date"]
                self.performed_by = (data.get("performed_by") or "")[:150] or (
                    self.performed_by
                )
                self.level = data.get("level") or self.level
                self.hours_at = data.get("hours_at")
                self.certificate_number = number
                if notes:
                    self.notes = (
                        f"{self.notes}\n{notes}".strip() if self.notes else notes
                    )
            self.save()

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
        # LV-403: read the last sequence and insert it in one write transaction,
        # or two writers read the same value and the sequence repeats.
        with transaction.atomic():
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


class MaintenanceProgram(BaseModel):
    """Act. 19, Annex F: how often a model needs each level of maintenance.

    The Manual is **not uniform**: the DJI models are 200 h / 6 months (basic),
    400 h / 12 months (medium) and 600 h / 18 months (advanced), while the
    Flyability Elios 3 and the Wingtra One go "according to the manufacturer,
    reviewed at an authorised workshop at least every 12 months" -- months only,
    no hours. So each interval is optional (at least one is required) and a level
    the Manual leaves to the manufacturer is simply **not seeded**: it is
    configured by hand when somebody has the figure, never invented.

    Matched like `PreflightChecklist` / `QualificationType`: comma-separated
    `model_keywords` against `Aircraft.model` (not `Aircraft.type`, which is
    "RPA" for the whole fleet). Whichever interval is reached **first** (hours or
    months) makes the level due.
    """

    name = models.CharField(max_length=150, verbose_name=_("Name"))
    model_keywords = models.CharField(
        max_length=250,
        blank=True,
        verbose_name=_("Model keywords"),
        help_text=_(
            "Comma-separated words matched against the aircraft model. "
            "Leave it empty for a programme that applies to every aircraft."
        ),
    )
    level = models.CharField(
        max_length=12, choices=PROGRAM_LEVELS, verbose_name=_("Level")
    )
    interval_hours = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        verbose_name=_("Interval (flight hours)"),
        help_text=_("Leave it empty when the level is not measured in hours."),
    )
    interval_months = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        verbose_name=_("Interval (months)"),
    )

    class Meta:
        verbose_name = _("maintenance programme")
        verbose_name_plural = _("maintenance programmes")
        ordering = ["name", "level"]
        constraints = [
            models.UniqueConstraint(
                fields=["name", "level"], name="maint_program_name_level_uniq"
            ),
            models.CheckConstraint(
                condition=models.Q(interval_hours__isnull=False)
                | models.Q(interval_months__isnull=False),
                name="maint_program_has_interval",
            ),
        ]

    def __str__(self):
        return f"{self.name} · {self.get_level_display()}"

    def keyword_list(self):
        return [
            word.strip().lower()
            for word in self.model_keywords.split(",")
            if word.strip()
        ]

    def applies_to(self, aircraft):
        keywords = self.keyword_list()
        if not keywords:
            return True
        model = (aircraft.model or "").lower()
        return any(keyword in model for keyword in keywords)

    @classmethod
    def for_aircraft(cls, aircraft):
        """`{level: programme}` that applies to `aircraft`.

        When several programmes cover the same level, **the one that names the
        model wins** over a keyword-less (general) one, and ties break by name:
        the answer must not depend on which row the database returns first.
        """
        chosen = {}
        for program in cls.objects.filter(is_active=True).order_by("name"):
            if not program.applies_to(aircraft):
                continue
            current = chosen.get(program.level)
            if current is None or (
                program.keyword_list() and not current.keyword_list()
            ):
                chosen[program.level] = program
        return chosen

    @classmethod
    def level_for_interval(cls, aircraft, interval_months):
        """LV-460: the programme level whose month interval is `interval_months`.

        Only a **proposal** for a person to confirm: a workshop certifies its own
        interval ("150 horas de vuelo o 6 meses") and that is not the Manual's
        definition of a level, so the hours are deliberately not compared. Returns
        the level only when exactly one of the aircraft's programmes has that
        month interval; otherwise `None` -- never a guess between two.
        """
        if not interval_months:
            return None
        levels = [
            level
            for level, program in cls.for_aircraft(aircraft).items()
            if program.interval_months == interval_months
        ]
        return levels[0] if len(levels) == 1 else None


class AircraftLogbook(BaseModel):
    """Accumulated flight hours of one aircraft (the hours side of REG-020).

    `hours_baseline` is the total the aircraft had on `baseline_on`, read by a
    person from the last maintenance certificate; from then on the hours are the
    baseline plus the duration of every flight record **after** that date. It
    lives here and not in `registry` so this block adds no migration to that app.
    An aircraft with no logbook has **no hours data** (`None`), which is not the
    same as zero hours.
    """

    aircraft = models.OneToOneField(
        Aircraft, on_delete=models.PROTECT, related_name="logbook"
    )
    hours_baseline = models.DecimalField(
        max_digits=8,
        decimal_places=1,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
        verbose_name=_("Hours at baseline date"),
    )
    baseline_on = models.DateField(
        null=True, blank=True, verbose_name=_("Baseline date")
    )

    class Meta:
        verbose_name = _("aircraft logbook")
        verbose_name_plural = _("aircraft logbooks")

    def __str__(self):
        return f"{self.aircraft} · {self.hours_baseline} h"

    def flight_hours(self):
        """Baseline plus the flights after `baseline_on`, in hours (1 decimal)."""
        from apps.operations.models import FlightRecord

        flights = FlightRecord.objects.filter(aircraft=self.aircraft, is_active=True)
        if self.baseline_on is not None:
            flights = flights.filter(actual_date__gt=self.baseline_on)
        seconds = sum(
            record.duration.total_seconds()
            for record in flights.only("actual_date", "departure_time", "arrival_time")
        )
        return self.hours_baseline + (Decimal(seconds) / Decimal(3600)).quantize(
            Decimal("0.1")
        )

    @classmethod
    def hours_for(cls, aircraft):
        """The aircraft's accumulated hours, or `None` when it has no logbook."""
        logbook = cls.objects.filter(aircraft=aircraft).first()
        return logbook.flight_hours() if logbook is not None else None
