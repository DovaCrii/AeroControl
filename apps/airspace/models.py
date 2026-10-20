from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


KINDS = (
    "aerodrome",
    "airport",
    "airstrip",
    "prohibited",
    "restricted",
    "danger",
    "naval",
    "fir_boundary",
    "aux",
)


KINDS = (
    "aerodrome",
    "airport",
    "airstrip",
    "prohibited",
    "restricted",
    "danger",
    "naval",
    "fir_boundary",
    "aux",
)


class AirspaceSnapshot(BaseModel):
    """One imported copy of the airspace map (append-only record of an import).

    The data lives in the database, not in git: the map's authorship is
    confirmed (DGAC delivers it) but its license is not, and the repo is
    public. A snapshot says **which file** was read, when, and what changed
    against the previous one; it is never edited afterwards except to stop
    being the current one (`is_current`).
    """

    source_name = models.CharField(max_length=200)
    source_url = models.CharField(max_length=500, blank=True)
    fetched_at = models.DateTimeField()
    sha256 = models.CharField(max_length=64, db_index=True)
    feature_count = models.PositiveIntegerField(default=0)
    attribution = models.CharField(max_length=300)
    added = models.PositiveIntegerField(default=0)
    changed = models.PositiveIntegerField(default=0)
    archived = models.PositiveIntegerField(default=0)
    is_current = models.BooleanField(default=False)

    class Meta:
        ordering = ["-fetched_at"]
        verbose_name = _("airspace snapshot")
        verbose_name_plural = _("airspace snapshots")
        constraints = [
            models.UniqueConstraint(
                fields=["is_current"],
                condition=Q(is_current=True),
                name="airspace_one_current_snapshot",
            ),
        ]

    def __str__(self):
        return f"{self.source_name} {self.fetched_at:%Y-%m-%d} ({self.sha256[:8]})"


class AirspaceFeature(BaseModel):
    """One placemark of the map, classified. Global catalog (no tenant).

    `is_active=False` means **archived**: the placemark disappeared from the
    source, or its content changed and a newer row replaced it. Rows are never
    deleted. `snapshot` is the import that created the row; `archived_in` the
    one that retired it.

    `source_key` identifies the placemark across imports (folder + normalized
    name + ordinal among identical ones); `content_hash` detects that the same
    placemark changed (geometry, text, kind or code).

    `vertical_limits_text` and `schedule_text` are the source's own words,
    never converted to numbers: the paper chart decides, not this app.
    """

    KIND_AERODROME = "aerodrome"
    KIND_AIRPORT = "airport"
    KIND_AIRSTRIP = "airstrip"
    KIND_PROHIBITED = "prohibited"
    KIND_RESTRICTED = "restricted"
    KIND_DANGER = "danger"
    KIND_NAVAL = "naval"
    KIND_FIR_BOUNDARY = "fir_boundary"
    KIND_AUX = "aux"
    KIND_CHOICES = [
        (KIND_AERODROME, _("Aerodrome")),
        (KIND_AIRPORT, _("Airport")),
        (KIND_AIRSTRIP, _("Small airstrip (unofficial)")),
        (KIND_PROHIBITED, _("Prohibited zone")),
        (KIND_RESTRICTED, _("Restricted zone")),
        (KIND_DANGER, _("Danger zone")),
        (KIND_NAVAL, _("Naval restricted zone")),
        (KIND_FIR_BOUNDARY, _("FIR boundary")),
        (KIND_AUX, _("Drawing aid")),
    ]

    snapshot = models.ForeignKey(
        AirspaceSnapshot, on_delete=models.PROTECT, related_name="features"
    )
    archived_in = models.ForeignKey(
        AirspaceSnapshot,
        on_delete=models.PROTECT,
        related_name="archived_features",
        null=True,
        blank=True,
    )
    source_key = models.CharField(max_length=64)
    content_hash = models.CharField(max_length=64)
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    code = models.CharField(max_length=20, blank=True)
    name = models.CharField(max_length=300)
    raw_name = models.CharField(max_length=500)
    folder = models.CharField(max_length=200, blank=True)
    description_text = models.TextField(blank=True)
    vertical_limits_text = models.TextField(blank=True)
    schedule_text = models.TextField(blank=True)
    geometry = models.JSONField()
    min_lat = models.FloatField(
        validators=[MinValueValidator(-90), MaxValueValidator(90)]
    )
    max_lat = models.FloatField(
        validators=[MinValueValidator(-90), MaxValueValidator(90)]
    )
    min_lon = models.FloatField(
        validators=[MinValueValidator(-180), MaxValueValidator(180)]
    )
    max_lon = models.FloatField(
        validators=[MinValueValidator(-180), MaxValueValidator(180)]
    )
    center_lat = models.FloatField()
    center_lon = models.FloatField()
    region = models.CharField(max_length=120, blank=True)
    commune = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ["kind", "code", "name"]
        verbose_name = _("airspace feature")
        verbose_name_plural = _("airspace features")
        indexes = [
            models.Index(fields=["kind", "is_active"], name="airspace_kind_active_idx"),
            models.Index(fields=["code"], name="airspace_code_idx"),
            models.Index(fields=["source_key"], name="airspace_source_key_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["source_key"],
                condition=Q(is_active=True),
                name="airspace_active_source_key_unique",
            ),
            models.CheckConstraint(
                condition=Q(min_lat__lte=models.F("max_lat"))
                & Q(min_lon__lte=models.F("max_lon")),
                name="airspace_bbox_ordered",
            ),
            models.CheckConstraint(
                condition=Q(kind__in=KINDS),
                name="airspace_kind_valid",
            ),
        ]

    def __str__(self):
        return f"{self.code} {self.name}".strip()
