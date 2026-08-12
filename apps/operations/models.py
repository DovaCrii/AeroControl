from datetime import datetime, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.db.models import Q
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from apps.core.choices import PURPOSE_CHOICES
from apps.core.models import BaseModel, StatusFlowMixin
from apps.registry.models import Operator, Aircraft, CostCenter


class FlightPermission(StatusFlowMixin, BaseModel):
    """A flight authorization, mirroring the real DGAC document (OPS-4).

    A single authorization typically lists several operators and several
    aircraft over a validity range (docs/dev/ops-contract-tracking-plan.md),
    not one of each on one day -- the previous single-FK/single-date shape
    could not represent that. `cost_center` stays a single FK: the scoping
    unit is unambiguous even when the crew/fleet is a roster.
    """

    STATUS_REQUESTED = "requested"
    STATUS_APPROVED = "approved"
    STATUS_DENIED = "denied"
    STATUS_COMPLETED = "completed"
    STATUS_CHOICES = [
        (STATUS_REQUESTED, _("Requested")),
        (STATUS_APPROVED, _("Approved")),
        (STATUS_DENIED, _("Denied")),
        (STATUS_COMPLETED, _("Completed")),
    ]
    # LV-72: the order the statuses actually advance in, read by
    # StatusFlowMixin.status_steps(). Declared here, next to the choices it
    # draws from, and **never as a literal list in a template** -- that is
    # precisely the R1.1 defect (the calendar carried 7 hand-written event
    # types that drifted from the 9 real ones). `denied` is deliberately out of
    # the flow: it is not a step on the way anywhere, it is where it stops.
    STATUS_FLOW = [STATUS_REQUESTED, STATUS_APPROVED, STATUS_COMPLETED]
    STATUS_BLOCKED = STATUS_DENIED
    # R2.6: DAN 151 (populated area) vs DAN 91 (unpopulated) is a real
    # normative distinction (ISO 9001/45001 audit guide, clause 6.1.3), not
    # a boolean -- a single survey can cross both, which "mixed" exists to
    # record. Decided 2026-08-07: just the fact, no extra document
    # requirement yet (what DAN 151 demands beyond this is defined later,
    # once confirmed against the edition in force).
    AREA_TYPE_CHOICES = [
        ("populated", _("Populated area")),
        ("unpopulated", _("Unpopulated area")),
        ("mixed", _("Mixed (crosses both)")),
    ]
    # R2.2/R2.3: the identifier every screen actually needs is this one, not
    # the DGAC folio below -- a permit exists (and needs a title on the
    # calendar, the list, its geo plan) long before the DGAC ever assigns a
    # number. Annual correlative ("JEJ-2026-001") because the year is enough
    # to place it in time, same as the DGAC resoluciones the operation
    # already handles. Assigned once in save() below, never blank, never
    # user-editable (excluded from FlightPermissionForm).
    internal_folio = models.CharField(max_length=20, unique=True, editable=False)
    # LV-39: optional until the permit is approved, so a permit can be drafted
    # ("requested") or recorded as "denied" before the DGAC folio exists. null
    # (not "") so several folio-less permits don't collide on the unique index.
    permission_number = models.CharField(
        max_length=50, unique=True, null=True, blank=True
    )
    operators = models.ManyToManyField(Operator, related_name="flight_permissions")
    aircraft_fleet = models.ManyToManyField(Aircraft, related_name="flight_permissions")
    cost_center = models.ForeignKey(CostCenter, on_delete=models.PROTECT)
    # R3.1: closed vocabulary (the 2 SIGO procedures under DAN 137 Cap. J,
    # confirmed against real data + the user directly -- see
    # apps.core.choices) instead of free text, so a calendar/list title
    # built from `purpose` cannot drift into whatever wording someone typed
    # ("Audiovisual" told nobody which procedure it actually was).
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES)
    purpose_detail = models.CharField(max_length=250, blank=True, default="")
    # Immutable historical record of what this field held before R3.1 --
    # same criterion as CostCenter.responsible: never shown as the primary
    # value, never edited, kept only so the original SIGO wording is not
    # lost to a backfill's best-effort classification.
    purpose_legacy = models.CharField(
        max_length=250, blank=True, default="", editable=False
    )
    valid_from = models.DateField()
    valid_until = models.DateField()
    location = models.CharField(max_length=250)
    # OPS-4 structured location (docs/dev/ops-contract-tracking-plan.md §1.4),
    # deferred when the rest of OPS-4 landed and picked up here. It
    # *complements* `location` rather than replacing it: the free-text field
    # keeps the exact wording of the DGAC authorization, while these add the
    # administrative breakdown and, optionally, the point/area the flight
    # covers so it can later cross-reference the GEO plan for the same site.
    # All optional -- an older permit whose paperwork only ever said
    # "Chuquicamata" is not retroactively incomplete.
    region = models.CharField(max_length=100, blank=True)
    commune = models.CharField(max_length=100, blank=True)
    area_name = models.CharField(max_length=200, blank=True)
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        validators=[
            MinValueValidator(Decimal("-90")),
            MaxValueValidator(Decimal("90")),
        ],
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        validators=[
            MinValueValidator(Decimal("-180")),
            MaxValueValidator(Decimal("180")),
        ],
    )
    radius_km = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    max_altitude_ft = models.PositiveIntegerField(null=True, blank=True)
    # Nullable so the permissions created before this field existed are not
    # retroactively broken; the form requires it (blank=False, the default)
    # for anything created or edited from now on.
    area_type = models.CharField(max_length=20, choices=AREA_TYPE_CHOICES, null=True)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="requested"
    )

    class Meta:
        verbose_name = _("flight permission")
        verbose_name_plural = _("flight permissions")
        # The calendar filters (valid_from/valid_until, is_active) on every
        # feed request, as a range-overlap query.
        indexes = [
            models.Index(
                fields=["valid_from", "valid_until", "is_active"],
                name="ops_permission_range_idx",
            )
        ]
        # R3.1: enforced at the DB level, not just the form -- the admin,
        # a script or a future import must not be able to save "other"
        # without a detail either.
        constraints = [
            models.CheckConstraint(
                condition=~Q(purpose="other") | ~Q(purpose_detail=""),
                name="ops_flightpermission_other_purpose_requires_detail",
            )
        ]

    def __str__(self):
        # R2.3: was `permission_number or f"{status} · {purpose[:30]}"` --
        # purpose leaked into the list/calendar/geo-plan titles as a
        # de-facto identifier for any permit without a DGAC folio yet.
        # internal_folio is assigned at creation and never blank, so
        # purpose goes back to being plain data.
        return self.internal_folio

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("permission-detail", kwargs={"pk": self.pk})

    @staticmethod
    def _next_internal_folio():
        """Annual correlative, safe under concurrent creation.

        `select_for_update()` locks the current-year rows within this
        transaction so two permits created at the same moment cannot both
        compute the same next number -- the second blocks until the first
        commits. The one gap this does not close is the very first permit
        of a new year (nothing to lock yet); the `unique` constraint turns
        that rare race into a failed save instead of a silent duplicate.
        """
        prefix = f"JEJ-{timezone.now().year}-"
        last = (
            FlightPermission.objects.select_for_update()
            .filter(internal_folio__startswith=prefix)
            .order_by("-internal_folio")
            .first()
        )
        next_seq = int(last.internal_folio[len(prefix) :]) + 1 if last else 1
        return f"{prefix}{next_seq:03d}"

    def save(self, *args, **kwargs):
        if self._state.adding and not self.internal_folio:
            with transaction.atomic():
                self.internal_folio = self._next_internal_folio()
                return super().save(*args, **kwargs)
        return super().save(*args, **kwargs)

    def clean(self):
        errors = {}
        if self.valid_until and self.valid_from and self.valid_until < self.valid_from:
            errors["valid_until"] = _("The end date cannot be before the start date.")
        if self.purpose == "other" and not self.purpose_detail:
            errors["purpose_detail"] = _(
                "Describe the purpose when 'Other' is selected."
            )
        # A lone coordinate cannot be plotted; require the pair together so a
        # half-entered point does not silently fail to show on a future map.
        if (self.latitude is None) != (self.longitude is None):
            message = _("Latitude and longitude must be entered together.")
            errors["latitude"] = message
            errors["longitude"] = message
        if self.radius_km is not None and self.latitude is None:
            errors["radius_km"] = _("A radius requires a coordinate pair.")
        if errors:
            raise ValidationError(errors)


class FlightRecord(BaseModel):
    permission = models.ForeignKey(
        FlightPermission, on_delete=models.PROTECT, related_name="records"
    )
    actual_date = models.DateField()
    departure_time = models.TimeField()
    arrival_time = models.TimeField()
    pilot = models.ForeignKey(Operator, on_delete=models.PROTECT)
    aircraft = models.ForeignKey(
        Aircraft, on_delete=models.PROTECT, related_name="flight_records"
    )

    class Meta:
        # The table that grows per flight; the calendar scans it by date.
        indexes = [
            models.Index(
                fields=["actual_date", "is_active"], name="ops_record_date_idx"
            )
        ]

    def __str__(self):
        return f"{self.aircraft} · {self.actual_date}"

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("record-detail", kwargs={"pk": self.pk})

    @property
    def duration(self):
        """LV-59: departure/arrival are stored but nothing ever computed the
        flight's actual length from them. `FlightRecordForm.clean()` rejects
        arrival <= departure at the form, but that is not a model-level
        constraint (a record created via the admin or a fixture has no such
        guard) -- an arrival not later than departure is treated as a flight
        that crossed midnight, not a negative duration."""
        anchor = datetime.combine(self.actual_date, self.departure_time)
        end = datetime.combine(self.actual_date, self.arrival_time)
        if end <= anchor:
            end += timedelta(days=1)
        return end - anchor

    @property
    def duration_display(self):
        """`duration` as "1h 05min" (or "05min" under an hour) for the list
        and detail pages -- a raw timedelta renders as "1:05:00" in a
        template, which reads as a clock, not a length."""
        from .selectors import format_duration

        return format_duration(self.duration)


class PermissionHistory(BaseModel):
    # `created_at` alone cannot order two rows created moments apart: on this
    # machine `timezone.now()` returns the *identical* value across rapid
    # successive calls, and SQL gives no ordering guarantee for ties on a
    # non-unique column. `sequence` is computed in save() as "latest + 1"
    # (same idiom as GeoPlanVersion.version_number / ResourceMovementLog).
    sequence = models.PositiveBigIntegerField(editable=False, default=0)
    permission = models.ForeignKey(
        FlightPermission, on_delete=models.PROTECT, related_name="history"
    )
    # R2.5: found while verifying the status-history table -- neither field
    # declared `choices`, so `get_previous_status_display`/
    # `get_new_status_display` were never generated by Django at all. The
    # template's `{{ h.get_previous_status_display|default:h.previous_status }}`
    # silently fell through to the raw stored value every time ("requested",
    # "denied"), which is why the history table showed English status codes
    # in an otherwise all-Spanish page.
    previous_status = models.CharField(
        max_length=20, choices=FlightPermission.STATUS_CHOICES
    )
    new_status = models.CharField(
        max_length=20, choices=FlightPermission.STATUS_CHOICES
    )
    changed_by = models.CharField(max_length=150)
    changed_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="permission_history_events",
    )
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = "Permission histories"
        ordering = ["-sequence"]

    def __str__(self):
        return f"{self.permission}: {self.previous_status} → {self.new_status}"

    def save(self, *args, **kwargs):
        if self._state.adding:
            latest = PermissionHistory.objects.order_by("-sequence").first()
            self.sequence = (latest.sequence if latest else 0) + 1
        return super().save(*args, **kwargs)
