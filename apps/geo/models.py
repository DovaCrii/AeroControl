"""Models for the KMZ/KML geo-editor block (BLOQUE GEO).

Design: docs/dev/geo-editor-plan.md. A plan holds an immutable chain of
versions; each version carries the whole canonical document as JSON (not rows
per feature). Versions are append-only, mirroring AuditEvent.
"""

import uuid
from datetime import date

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class GeoPlan(BaseModel):
    """A geospatial flight-planning document anchored to a cost center.

    Anchored to `cost_center` (the real scoping unit in this project) with an
    optional `flight_permission`: planning usually precedes the permit. The
    original KMZ/KML lives in `source_document` (a compliance.Document) and is
    never mutated; edits produce new GeoPlanVersion rows.
    """

    STATUS_CHOICES = [
        ("draft", _("Draft")),
        ("editing", _("Editing")),
        ("in_review", _("In review")),
        ("approved", _("Approved")),
        ("rejected", _("Rejected")),
    ]
    # Content can only change while the plan is in one of these states; the
    # commit API is the authoritative enforcement (see GEO-6).
    EDITABLE_STATUSES = frozenset({"draft", "editing"})

    title = models.CharField(max_length=200)
    cost_center = models.ForeignKey(
        "registry.CostCenter",
        on_delete=models.PROTECT,
        related_name="geo_plans",
    )
    flight_permission = models.ForeignKey(
        "operations.FlightPermission",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="geo_plans",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="geo_plans_created",
    )
    source_document = models.ForeignKey(
        "compliance.Document",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    current_version = models.ForeignKey(
        "GeoPlanVersion",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        verbose_name = _("geo plan")
        verbose_name_plural = _("geo plans")
        permissions = [("approve_geoplan", "Can approve geo plan")]
        indexes = [
            models.Index(fields=["status", "is_active"], name="geo_plan_status_idx"),
            models.Index(fields=["cost_center", "is_active"], name="geo_plan_cc_idx"),
        ]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("geo-plan-detail", kwargs={"pk": self.pk})

    @property
    def is_editable(self):
        return self.status in self.EDITABLE_STATUSES


class AppendOnlyVersionQuerySet(models.QuerySet):
    """Prevent application code from mutating or deleting plan versions."""

    def update(self, **kwargs):
        raise ValidationError("GeoPlanVersion records are append-only.")

    def delete(self):
        raise ValidationError("GeoPlanVersion records are append-only.")

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError("GeoPlanVersion records are append-only.")


class GeoPlanVersion(models.Model):
    """One immutable snapshot of a plan's canonical document.

    Not a BaseModel: it has no `updated_at`/`is_active` because it never
    changes. The full canonical "AeroKML JSON" lives in `content`; the derived
    columns (checksum, feature_count, bbox) exist so listing and dedupe do not
    have to deserialize the blob.
    """

    SOURCE_CHOICES = [
        ("import", _("Import")),
        ("editor", _("Editor")),
        ("restore", _("Restore")),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    plan = models.ForeignKey(GeoPlan, on_delete=models.PROTECT, related_name="versions")
    version_number = models.PositiveIntegerField()
    parent_version = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    restored_from = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    content = models.JSONField()
    content_checksum = models.CharField(max_length=64)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    summary = models.CharField(max_length=200, blank=True)
    feature_count = models.PositiveIntegerField(default=0)
    size_bytes = models.PositiveIntegerField(default=0)
    bbox_west = models.FloatField(null=True, blank=True)
    bbox_south = models.FloatField(null=True, blank=True)
    bbox_east = models.FloatField(null=True, blank=True)
    bbox_north = models.FloatField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="geo_versions_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = AppendOnlyVersionQuerySet.as_manager()

    class Meta:
        verbose_name = _("geo plan version")
        verbose_name_plural = _("geo plan versions")
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "version_number"],
                name="geo_version_unique_number",
            ),
            models.CheckConstraint(
                condition=Q(version_number__gte=1),
                name="geo_version_number_gte_1",
            ),
        ]
        indexes = [
            models.Index(
                fields=["plan", "-version_number"], name="geo_version_plan_num_idx"
            )
        ]

    def __str__(self):
        return f"{self.plan_id} v{self.version_number}"

    def clean(self):
        # Layer 2 of the approved-plan lock (the commit API is layer 1, the
        # read-only editor is layer 3). A version imported with the plan is
        # exempt: V1 is created while the plan is still draft, and import is not
        # a content edit by a user. Any editor/restore version, though, may only
        # land while the plan is in an editable state.
        super().clean()
        if self.source == "import":
            return
        if self.plan_id and self.plan.status not in GeoPlan.EDITABLE_STATUSES:
            raise ValidationError(
                {"plan": _("This plan cannot be edited in its current state.")}
            )

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("GeoPlanVersion records are append-only.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("GeoPlanVersion records are append-only.")


class GeoPlanHistory(BaseModel):
    """Append-only status history, mirroring operations.PermissionHistory.

    Written by the shared `track_status_changes` signal (apps/core/signals.py),
    which is why the field names match its expectations.
    """

    # `created_at` alone cannot order two rows created moments apart: on this
    # machine `timezone.now()` returns the *identical* value across rapid
    # successive calls, and SQL gives no ordering guarantee for ties on a
    # non-unique column. `sequence` is computed in save() as "latest + 1"
    # (same idiom as GeoPlanVersion.version_number / ResourceMovementLog).
    sequence = models.PositiveBigIntegerField(editable=False, default=0)
    plan = models.ForeignKey(GeoPlan, on_delete=models.CASCADE, related_name="history")
    previous_status = models.CharField(max_length=20)
    new_status = models.CharField(max_length=20)
    changed_by = models.CharField(max_length=150)
    changed_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="geo_plan_history_events",
    )

    class Meta:
        verbose_name = _("geo plan history entry")
        verbose_name_plural = _("geo plan history")
        ordering = ["-sequence"]

    def __str__(self):
        return f"{self.plan_id}: {self.previous_status} -> {self.new_status}"

    def save(self, *args, **kwargs):
        if self._state.adding:
            latest = GeoPlanHistory.objects.order_by("-sequence").first()
            self.sequence = (latest.sequence if latest else 0) + 1
        return super().save(*args, **kwargs)


class GeoPlanPermissionLink(BaseModel):
    """OPS-7: append-only log of when GeoPlan.flight_permission changes.

    That FK is a plain nullable link with no history of its own; this answers
    "when was this plan linked to a permit, and to which one before" without
    overloading GeoPlanHistory, which is specifically status transitions, not
    an arbitrary field's history. Written by
    apps/geo/signals.py:track_flight_permission_link (pre_save on GeoPlan).
    """

    sequence = models.PositiveBigIntegerField(editable=False, default=0)
    plan = models.ForeignKey(
        GeoPlan, on_delete=models.CASCADE, related_name="permission_links"
    )
    previous_permission = models.ForeignKey(
        "operations.FlightPermission",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    new_permission = models.ForeignKey(
        "operations.FlightPermission",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    changed_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        verbose_name = _("geo plan permission link")
        verbose_name_plural = _("geo plan permission links")
        ordering = ["-sequence"]

    def __str__(self):
        return (
            f"{self.plan_id}: {self.previous_permission_id} -> {self.new_permission_id}"
        )

    def save(self, *args, **kwargs):
        if self._state.adding:
            latest = GeoPlanPermissionLink.objects.order_by("-sequence").first()
            self.sequence = (latest.sequence if latest else 0) + 1
        return super().save(*args, **kwargs)


class WeatherReview(BaseModel):
    """R8.1: the meteorological review, on record (ISO 8.1).

    R8.1 already *shows* the forecast over a plan's area for the day it is
    flown, but showing is not evidence: the page recomputes it on every visit
    and keeps nothing, so after the flight there is no way to answer "was the
    weather reviewed beforehand, and what did it say" -- which is the actual
    audit question. A forecast is also **not reproducible after the fact**: ask
    the provider next month and it answers with a different model run, or
    refuses a past date entirely.

    So this stores the numbers **as they were read**, not a pointer to fetch
    them again. Append-only, like GeoPlanPermissionLink and
    ResourceMovementLog: a review is a statement about a moment, and editing it
    later would defeat the point.

    Recorded on an explicit action, never on page load. What the norm asks for
    is that a responsible person reviewed the conditions; a row written because
    someone happened to open a tab would attest to nobody having done so.
    """

    plan = models.ForeignKey(
        GeoPlan, on_delete=models.CASCADE, related_name="weather_reviews"
    )
    # The permit whose start date the forecast was for. SET_NULL rather than
    # PROTECT: losing the link must not erase the evidence that the review
    # happened, and target_date below preserves the day either way.
    flight_permission = models.ForeignKey(
        "operations.FlightPermission",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    target_date = models.DateField()
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    wind_speed_max = models.FloatField(null=True, blank=True)
    wind_gusts_max = models.FloatField(null=True, blank=True)
    precipitation_sum = models.FloatField(null=True, blank=True)
    precipitation_probability_max = models.FloatField(null=True, blank=True)
    # The provider states its units per response; a bare "12" is not evidence
    # of anything, and Open-Meteo can be asked in km/h or m/s.
    units = models.JSONField(default=dict, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        verbose_name = _("weather review")
        verbose_name_plural = _("weather reviews")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.plan_id} @ {self.target_date}"

    @classmethod
    def from_forecast(cls, *, plan, forecast, latitude, longitude, user=None):
        """Build (unsaved) a review from what `weather.forecast_for` returned.

        Kept next to the model rather than in the view so the mapping from the
        provider's field names to these columns lives in one place -- the view
        should not have to know that "wind_speed_10m_max" is this model's
        `wind_speed_max`.
        """
        return cls(
            plan=plan,
            flight_permission=plan.flight_permission,
            target_date=date.fromisoformat(forecast["date"]),
            latitude=latitude,
            longitude=longitude,
            wind_speed_max=forecast.get("wind_speed_10m_max"),
            wind_gusts_max=forecast.get("wind_gusts_10m_max"),
            precipitation_sum=forecast.get("precipitation_sum"),
            precipitation_probability_max=forecast.get("precipitation_probability_max"),
            units=forecast.get("units") or {},
            reviewed_by=user,
        )
