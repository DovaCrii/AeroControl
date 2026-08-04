from django.core.exceptions import ValidationError
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from apps.core.models import BaseModel
from apps.registry.models import Operator, Aircraft, CostCenter


class FlightPermission(BaseModel):
    """A flight authorization, mirroring the real DGAC document (OPS-4).

    A single authorization typically lists several operators and several
    aircraft over a validity range (docs/dev/ops-contract-tracking-plan.md),
    not one of each on one day -- the previous single-FK/single-date shape
    could not represent that. `cost_center` stays a single FK: the scoping
    unit is unambiguous even when the crew/fleet is a roster.
    """

    STATUS_CHOICES = [
        ("requested", _("Requested")),
        ("approved", _("Approved")),
        ("denied", _("Denied")),
        ("completed", _("Completed")),
    ]
    # LV-39: optional until the permit is approved, so a permit can be drafted
    # ("requested") or recorded as "denied" before the DGAC folio exists. null
    # (not "") so several folio-less permits don't collide on the unique index.
    permission_number = models.CharField(
        max_length=50, unique=True, null=True, blank=True
    )
    operators = models.ManyToManyField(Operator, related_name="flight_permissions")
    aircraft_fleet = models.ManyToManyField(Aircraft, related_name="flight_permissions")
    cost_center = models.ForeignKey(CostCenter, on_delete=models.PROTECT)
    purpose = models.CharField(max_length=250)
    valid_from = models.DateField()
    valid_until = models.DateField()
    location = models.CharField(max_length=250)
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

    def __str__(self):
        # LV-39: a permit may not have its folio yet (still requested/denied).
        return self.permission_number or f"{self.get_status_display()} · {self.purpose[:30]}"

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("permission-detail", kwargs={"pk": self.pk})

    def clean(self):
        if self.valid_until and self.valid_from and self.valid_until < self.valid_from:
            raise ValidationError(
                {"valid_until": _("The end date cannot be before the start date.")}
            )


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
    previous_status = models.CharField(max_length=20)
    new_status = models.CharField(max_length=20)
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
