from django.conf import settings
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

SOURCE_AIP_ENR51 = "aip_enr51"
SOURCE_AIP_ENR55 = "aip_enr55"
SOURCE_AIP_FIR_JSON = "aip_fir_json"
SOURCE_GOOGLE = "google_mymaps"
SOURCE_KINDS = (SOURCE_AIP_ENR51, SOURCE_AIP_ENR55, SOURCE_AIP_FIR_JSON, SOURCE_GOOGLE)
SOURCE_CHOICES = [
    (SOURCE_AIP_ENR51, _("AIP-Chile ENR 5.1 (P, R, D zones)")),
    (SOURCE_AIP_ENR55, _("AIP-Chile ENR 5.5 (other activities)")),
    (SOURCE_AIP_FIR_JSON, _("AIP-Chile FIR boundaries (JSON)")),
    (SOURCE_GOOGLE, _("Google My Maps (DGAC sensitive zones)")),
]

STATUS_DRAFT = "draft"
STATUS_IN_REVIEW = "in_review"
STATUS_PUBLISHED = "published"
STATUS_REJECTED = "rejected"
SNAPSHOT_STATUSES = (STATUS_DRAFT, STATUS_IN_REVIEW, STATUS_PUBLISHED, STATUS_REJECTED)
SNAPSHOT_STATUS_CHOICES = [
    (STATUS_DRAFT, _("Draft")),
    (STATUS_IN_REVIEW, _("In review")),
    (STATUS_PUBLISHED, _("Published")),
    (STATUS_REJECTED, _("Rejected")),
]

REVIEW_PENDING = "pending"
REVIEW_APPROVED = "approved"
REVIEW_REJECTED = "rejected"
REVIEW_NEEDS_REVIEW = "needs_review"
REVIEW_STATUSES = (
    REVIEW_PENDING,
    REVIEW_APPROVED,
    REVIEW_REJECTED,
    REVIEW_NEEDS_REVIEW,
)
REVIEW_CHOICES = [
    (REVIEW_PENDING, _("Pending review")),
    (REVIEW_APPROVED, _("Approved")),
    (REVIEW_REJECTED, _("Rejected")),
    (REVIEW_NEEDS_REVIEW, _("Needs a closer look")),
]

GEOMETRY_METHODS = ("", "polygon", "circle", "arc", "sector")
GEOMETRY_METHOD_CHOICES = [
    ("polygon", _("Polygon (vertices)")),
    ("circle", _("Circle (centre and radius)")),
    ("arc", _("Arc")),
    ("sector", _("Radial sector")),
]


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
    # LV-361: where the copy comes from. The Google map stays the default so the
    # rows imported before this field existed read as what they are.
    source_kind = models.CharField(
        max_length=20, choices=SOURCE_CHOICES, default=SOURCE_GOOGLE
    )
    amdt_number = models.CharField(max_length=20, blank=True)
    effective_date = models.DateField(null=True, blank=True)
    pdf_sha256 = models.CharField(max_length=64, blank=True)
    status = models.CharField(
        max_length=20, choices=SNAPSHOT_STATUS_CHOICES, default=STATUS_PUBLISHED
    )

    class Meta:
        ordering = ["-fetched_at"]
        verbose_name = _("airspace snapshot")
        verbose_name_plural = _("airspace snapshots")
        # LV-361 phase 4: the person who reviews and publishes an AIP amendment. Not given to any
        # role by `bootstrap_roles` (only Administrator, which holds every permission): who reviews
        # each amendment is the person's decision.
        permissions = [
            (
                "review_airspacesnapshot",
                _("Can review, correct and publish AIP airspace snapshots"),
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["source_kind"],
                condition=Q(is_current=True),
                name="airspace_one_current_snapshot_per_source",
            ),
            models.CheckConstraint(
                condition=Q(source_kind__in=SOURCE_KINDS),
                name="airspace_snapshot_source_valid",
            ),
            models.CheckConstraint(
                condition=Q(status__in=SNAPSHOT_STATUSES),
                name="airspace_snapshot_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(is_current=False) | Q(status=STATUS_PUBLISHED),
                name="airspace_current_snapshot_published",
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
    # LV-361: provenance and human review. `lateral_text` is the source's own
    # words for the lateral limits (never personal data); the screen only draws
    # a feature whose `review_status` is approved.
    source_kind = models.CharField(
        max_length=20, choices=SOURCE_CHOICES, default=SOURCE_GOOGLE
    )
    lateral_text = models.TextField(blank=True)
    geometry_method = models.CharField(
        max_length=10, choices=GEOMETRY_METHOD_CHOICES, blank=True
    )
    parse_warnings = models.JSONField(default=list, blank=True)
    review_status = models.CharField(
        max_length=20, choices=REVIEW_CHOICES, default=REVIEW_PENDING
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

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
                fields=["source_kind", "source_key"],
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
            models.CheckConstraint(
                condition=Q(source_kind__in=SOURCE_KINDS),
                name="airspace_feature_source_valid",
            ),
            models.CheckConstraint(
                condition=Q(geometry_method__in=GEOMETRY_METHODS),
                name="airspace_geometry_method_valid",
            ),
            models.CheckConstraint(
                condition=Q(review_status__in=REVIEW_STATUSES),
                name="airspace_review_status_valid",
            ),
        ]

    def __str__(self):
        return f"{self.code} {self.name}".strip()


RESULTS_ALL = (
    "missing_in_google",
    "missing_in_aip",
    "match",
    "discrepancy",
    "google_only",
    "measured",
)


class AirspaceCrossCheck(BaseModel):
    """How one zone of the AIP compares with the same zone of the Google map.

    Computed, never edited: a row says which two features were compared and how
    far apart their vertices are (`max_vertex_m`, `median_m`, in metres). What
    counts as a discrepancy is a decision of the person, so `result` only
    records the structural outcome until a threshold exists.
    """

    RESULT_MISSING_IN_GOOGLE = "missing_in_google"
    RESULT_MISSING_IN_AIP = "missing_in_aip"
    RESULT_MATCH = "match"
    RESULT_DISCREPANCY = "discrepancy"
    RESULT_GOOGLE_ONLY = "google_only"
    # Both shapes exist and the distance was measured, but no threshold has been set yet: the
    # person decides what counts as a discrepancy (`AIRSPACE_CROSSCHECK_THRESHOLD_M`).
    RESULT_MEASURED = "measured"
    RESULTS = RESULTS_ALL
    RESULT_CHOICES = [
        (RESULT_MISSING_IN_GOOGLE, _("In the AIP, missing in Google")),
        (RESULT_MISSING_IN_AIP, _("In Google, missing in the AIP")),
        (RESULT_MATCH, _("Match")),
        (RESULT_DISCREPANCY, _("Discrepancy")),
        (RESULT_GOOGLE_ONLY, _("Google only (reference)")),
        (RESULT_MEASURED, _("Measured (no threshold set)")),
    ]

    # The AIP snapshot this comparison belongs to (also for the rows with no AIP feature: a zone
    # only the Google map has).
    snapshot = models.ForeignKey(
        AirspaceSnapshot,
        on_delete=models.PROTECT,
        related_name="cross_checks",
        null=True,
        blank=True,
    )
    code = models.CharField(max_length=20, blank=True)
    aip_feature = models.ForeignKey(
        AirspaceFeature,
        on_delete=models.PROTECT,
        related_name="cross_checks_as_aip",
        null=True,
        blank=True,
    )
    google_feature = models.ForeignKey(
        AirspaceFeature,
        on_delete=models.PROTECT,
        related_name="cross_checks_as_google",
        null=True,
        blank=True,
    )
    max_vertex_m = models.FloatField(null=True, blank=True)
    median_m = models.FloatField(null=True, blank=True)
    result = models.CharField(max_length=20, choices=RESULT_CHOICES)

    class Meta:
        ordering = ["code", "result"]
        verbose_name = _("airspace cross-check")
        verbose_name_plural = _("airspace cross-checks")
        constraints = [
            models.CheckConstraint(
                condition=Q(result__in=RESULTS_ALL),
                name="airspace_crosscheck_result_valid",
            ),
            models.CheckConstraint(
                condition=Q(aip_feature__isnull=False)
                | Q(google_feature__isnull=False),
                name="airspace_crosscheck_has_a_feature",
            ),
            models.CheckConstraint(
                condition=~Q(result="missing_in_google")
                | (Q(aip_feature__isnull=False) & Q(google_feature__isnull=True)),
                name="airspace_crosscheck_missing_in_google_shape",
            ),
            models.CheckConstraint(
                condition=~Q(result__in=("missing_in_aip", "google_only"))
                | (Q(aip_feature__isnull=True) & Q(google_feature__isnull=False)),
                name="airspace_crosscheck_google_side_shape",
            ),
            models.CheckConstraint(
                condition=~Q(result__in=("match", "discrepancy", "measured"))
                | (Q(aip_feature__isnull=False) & Q(google_feature__isnull=False)),
                name="airspace_crosscheck_compared_shape",
            ),
            models.CheckConstraint(
                condition=(Q(max_vertex_m__isnull=True) | Q(max_vertex_m__gte=0))
                & (Q(median_m__isnull=True) | Q(median_m__gte=0)),
                name="airspace_crosscheck_distances_non_negative",
            ),
        ]

    def __str__(self):
        return f"{self.code} {self.result}".strip()
