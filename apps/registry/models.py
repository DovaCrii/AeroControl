import zlib
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from apps.core.choices import PURPOSE_CHOICES
from apps.core.models import BaseModel, OperationalTenant
from apps.core.tenancy import get_default_tenant


class CostCenter(BaseModel):
    tenant = models.ForeignKey(
        OperationalTenant,
        on_delete=models.PROTECT,
        default=get_default_tenant,
        related_name="cost_centers",
    )
    # T3.2 Fase 3: unique per tenant, not globally -- two organizations may
    # reuse a cost-center code. (Global unique dropped; see Meta.constraints.)
    code = models.CharField(max_length=30)
    # LV-16: optional -- the code plus the contract administrator identify the
    # cost center; a free-text name is no longer required on the form.
    name = models.CharField(max_length=150, blank=True)
    # R3.3(b): a separate axis from `is_active` (which is this project's soft
    # delete, AGENTS.md -- never remove operative rows). A cost center whose
    # client contract ended is not an error/duplicate to archive away; it
    # should keep showing (greyed, grouped after the operative ones) so its
    # history stays reachable from the normal list, not just from "archived".
    CONTRACT_STATUS_CHOICES = [
        ("active", _("Active")),
        ("closed", _("Closed")),
    ]
    # blank=True: unlike R2.6's area_type, closing a contract is an
    # occasional action on an existing record, not a fact every cost center
    # needs on creation -- forcing a choice on every form would be friction
    # for no benefit when "active" is already the right default.
    contract_status = models.CharField(
        max_length=20, choices=CONTRACT_STATUS_CHOICES, default="active", blank=True
    )
    # Free-text name kept from the Chapter 1 import. It cannot be used to reach
    # anyone (the imported values do not match operator names), so notifications
    # use responsible_operator; this stays as the historical record.
    responsible = models.CharField(max_length=150, blank=True)
    responsible_operator = models.ForeignKey(
        "registry.Operator",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cost_centers_in_charge",
        help_text=_("Recipient of expiry digests for this cost center."),
    )
    # The responsible person is not always in the operator roster: it can be an
    # administrator, a secretary, or a safety officer instead of a registered
    # pilot -- and the same person may end up responsible for several cost
    # centers where staffing is thin. Forcing them into Operator would mean
    # inventing a DGAC credential and employee ID for someone who does not
    # fly, and would leak into every other view that assumes the roster is
    # flight crew. Plain contact info instead, used only when no operator is
    # reachable (see notification_email).
    # verbose_name matches the form's labels (registry/forms.py CostCenterForm)
    # so the detail page and the edit form read the same -- Django's
    # auto-derived label ("Responsible contact name") has no catalog entry and
    # rendered in English on the detail page otherwise. Case must match the
    # catalog msgid exactly ("External contact name"/"...email", already used
    # by the form) -- translate_field_label() only re-cases+relooks-up a miss,
    # so a source literal that only near-matches (wrong case) passes the
    # detail page by accident but fails test_translations' exact-match guard.
    responsible_contact_name = models.CharField(
        max_length=150, blank=True, verbose_name=_("External contact name")
    )
    responsible_contact_email = models.EmailField(
        blank=True, verbose_name=_("External contact email")
    )
    # R7.4 (ISO 9001 8.6): the acceptance criteria for a survey belong to the
    # contract, not to each deliverable. If someone types the threshold on
    # every row it is not an agreed criterion, it is an opinion per record --
    # so `Deliverable` compares against these and derives "meets / does not"
    # instead of storing a declared verdict.
    #
    # All nullable, and that is the design, not a gap: **a contract with no
    # thresholds set simply has no quality gate**, and the deliverable records
    # its metrics without a pass/fail claim. That is what makes this shippable
    # before the real contract numbers are known -- they are loaded per
    # contract, by the people who negotiated them, with no code change. An
    # invented global threshold would be worse than none: a gate the operation
    # cannot meet is a gate somebody switches off.
    required_gsd_cm = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        verbose_name=_("Required GSD (cm)"),
    )
    max_rmse_xy_cm = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        verbose_name=_("Maximum horizontal RMSE (cm)"),
    )
    max_rmse_z_cm = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        verbose_name=_("Maximum vertical RMSE (cm)"),
    )

    @property
    def has_quality_thresholds(self):
        """Whether this contract defines acceptance criteria at all."""
        return any(
            value is not None
            for value in (
                self.required_gsd_cm,
                self.max_rmse_xy_cm,
                self.max_rmse_z_cm,
            )
        )

    def __str__(self):
        # name is optional (LV-16): fall back to the code alone when blank.
        label = f"{self.code} - {self.name}" if self.name else self.code
        return f"{label} · {self.responsible}" if self.responsible else label

    class Meta:
        # Translated names: user-facing messages interpolate verbose_name
        # ("%(name)s archived"), and without this they said "Operator" inside
        # a Spanish sentence.
        verbose_name = _("cost center")
        verbose_name_plural = _("cost centers")
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "code"], name="registry_costcenter_tenant_code_uniq"
            )
        ]

    @property
    def day_to_day_contact(self):
        """Who to reach day-to-day, when it is not the contract administrator
        above (LV-34/LV-56): an operator from the roster, or an external
        contact. Empty when the administrator already covers it -- callers
        show this only as a supplement, not a replacement."""
        if self.responsible_operator_id:
            return self.responsible_operator.full_name
        return self.responsible_contact_name

    @property
    def notification_email(self):
        """Email to notify for this cost center, or "" when unreachable.

        An archived responsible operator does not count as reachable: mailing
        someone who left looks like the notification worked when nobody who
        can act on it will read it. Falls back to the external contact when
        the responsible person is not in the operator roster, or when the
        operator on file left and nobody replaced them there yet.
        """
        operator = self.responsible_operator
        if operator and operator.is_active and operator.email:
            return operator.email
        return self.responsible_contact_email


class Aircraft(BaseModel):
    tenant = models.ForeignKey(
        OperationalTenant,
        on_delete=models.PROTECT,
        default=get_default_tenant,
        related_name="aircraft",
    )
    STATUS_CHOICES = [
        ("active", _("Active")),
        # LV-46: an accident/incident just happened and the aircraft has not
        # yet been formally sent to maintenance -- distinct from "maintenance"
        # (already in the workflow) so the fleet list flags it at a glance.
        ("damaged", _("Damaged")),
        ("maintenance", _("Maintenance")),
        ("retired", _("Retired")),
    ]
    registration = models.CharField(max_length=30, unique=True)
    type = models.CharField(max_length=100)
    model = models.CharField(max_length=100)
    manufacturer = models.CharField(max_length=100)
    year = models.PositiveIntegerField(null=True, blank=True)
    # X.1: the only key present in all three worlds (DJI, the Z: folder
    # names, the DGAC registry) -- unique now that the 4 known production
    # discrepancies are resolved (see save() and migration 0028). `null=True`
    # (not just blank) so aircraft without a serial on file yet do not
    # collide on the unique index, same pattern as
    # FlightPermission.permission_number.
    serial_number = models.CharField(max_length=100, blank=True, null=True, unique=True)
    max_takeoff_weight_kg = models.DecimalField(
        max_digits=8, decimal_places=3, null=True, blank=True
    )
    basic_weight_kg = models.DecimalField(
        max_digits=8, decimal_places=3, null=True, blank=True
    )
    vlos = models.CharField(max_length=20, blank=True, verbose_name=_("VLOS"))
    parachute = models.CharField(max_length=20, blank=True)
    # LV-29: the JAC insurance validity from the SIGO screen, as a first-class
    # field (the user enters it from the DGAC capture). This is the canonical
    # source for the list column and the alert/calendar/dashboard wiring; an
    # insurance document may still be attached as the supporting file, but the
    # date lives here (before LV-29 it was derived from an is_insurance
    # Document, which meant no expiry until a file was uploaded).
    insurance_expiry = models.DateField(
        null=True, blank=True, verbose_name=_("JAC insurance expiry")
    )
    # R5.7: a newly-registered aircraft with the JAC policy already
    # requested looked identical to one with no insurance requested at all
    # -- both showed "-" on the list, since insurance_expiry was null either
    # way. This tracks the filing itself, a separate axis from
    # insurance_expiry (same pattern as CostCenter.contract_status, R3.3b).
    # clean() below forces "active" once a real expiry date exists, so this
    # cannot go stale and claim "pending" after the policy has arrived.
    INSURANCE_STATUS_CHOICES = [
        ("pending", _("Filing in progress")),
        ("active", _("Active")),
    ]
    insurance_status = models.CharField(
        max_length=20,
        choices=INSURANCE_STATUS_CHOICES,
        default="active",
        blank=True,
        verbose_name=_("Insurance status"),
    )
    authorized_services = models.TextField(blank=True)
    cost_center = models.ForeignKey(
        CostCenter,
        on_delete=models.PROTECT,
        related_name="aircraft",
        null=True,
        blank=True,
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")

    # OPS-3: physical whereabouts, a different axis from `status` (condition).
    # An active aircraft can be at headquarters, deployed on a site, or in for
    # maintenance; tracked separately so "where is it" and "is it flyable" don't
    # get conflated into one field.
    LOCATION_CHOICES = [
        ("headquarters", _("Headquarters")),
        ("on_site", _("On site")),
        ("maintenance", _("In maintenance")),
    ]
    current_location = models.CharField(
        max_length=20, choices=LOCATION_CHOICES, default="headquarters"
    )
    current_site = models.ForeignKey(
        CostCenter,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text=_("The site this aircraft is deployed to, when on site."),
    )

    class Meta:
        verbose_name = _("aircraft")
        verbose_name_plural = _("aircraft")

    def __str__(self):
        return self.registration

    @property
    def selector_label(self):
        """R5.5: `registration` alone does not distinguish "which M300 is
        this" in a dropdown with several of the same model. Deliberately
        not folded into `__str__` -- other places (movement logs, the
        assignment tables) depend on that staying just the registration.
        Used via `label_from_instance` in every form that lets someone pick
        an aircraft (AssignmentForm, AircraftAssignmentForm,
        AircraftBulkAssignForm, FlightRecordForm,
        FlightPermissionForm.aircraft_fleet, MaintenanceRecordForm)."""
        parts = [self.registration, self.model]
        if self.serial_number:
            parts.append(f"S/N {self.serial_number}")
        return " · ".join(parts)

    @property
    def insurance_is_overdue(self):
        """LV-29: the JAC insurance lapsed (past its expiry). ``None`` expiry --
        no date on file -- is not overdue, it is simply unknown."""
        from django.utils import timezone

        return (
            self.insurance_expiry is not None
            and self.insurance_expiry < timezone.localdate()
        )

    def clean(self):
        errors = {}
        if self.current_location == "on_site" and not self.current_site_id:
            errors["current_site"] = _("Select the site the aircraft is deployed to.")
        if self.current_location != "on_site" and self.current_site_id:
            errors["current_site"] = _(
                "A site only applies when the aircraft is on site."
            )
        if errors:
            raise ValidationError(errors)
        # R5.7: a real expiry date means the JAC policy already arrived --
        # "pending" would be stale and contradict insurance_expiry, the
        # field that actually drives the vigente/atrasado column. Same
        # normalize-on-clean idiom as CostCenter.contract_status (R3.3b).
        if self.insurance_expiry is not None:
            self.insurance_status = "active"
        elif not self.insurance_status:
            self.insurance_status = "active"

    def save(self, *args, **kwargs):
        # X.1: the DJI serial never contains whitespace -- production has 2
        # aircraft with a stray internal space typed into this field
        # (confirmed against the Z: folder names, which carry the real
        # serial). `.split()`+`"".join` removes internal as well as leading/
        # trailing whitespace, unlike `.strip()`. An empty result becomes
        # `None`, not `""`, so several aircraft without a serial on file
        # do not collide on the unique index.
        self.serial_number = "".join((self.serial_number or "").split()) or None
        super().save(*args, **kwargs)


class Battery(BaseModel):
    """LiPo battery inventory and cycle count (R7.2, ISO 7.1.3).

    **A mirror, not a master.** ADR-0002 assigns battery inventory to AeroLink,
    because DJI reports cycles and health natively and a hand-kept count drifts
    from reality immediately. This table exists so the ISO 7.1.3 evidence lives
    where the auditor already looks -- next to the aircraft, the maintenance
    history and the flight hours -- while the numbers themselves come from
    AeroLink once `X.4` lands. Until then it stays empty on purpose; there is
    no create/edit form (the plan's own wording: "diseñar la forma, no llenarla
    a mano").

    That mirror role is what shapes the fields:

    - `serial_number` is the join key and is unique, exactly like
      `Aircraft.serial_number` (X.1) -- it is what DJI reports, so it is the
      only value both systems can agree on. Same whitespace normalization, so
      a serial typed by a human and one arriving from telemetry compare equal.
    - `cycle_count` / `health_percent` / `firmware_version` are the three
      things ISO 7.1.3 asks about that only the aircraft knows.
    - `synced_at` / `source` record **where a row came from and how stale it
      is**. Without them a zero cycle count is ambiguous: a new battery, or a
      sync that never ran? An auditor asking "is this current?" needs that
      answered on the record, not inferred.
    - `aircraft` is nullable and intentionally weak: batteries rotate between
      airframes, so this is "last seen on", not ownership.
    """

    SOURCE_MANUAL = "manual"
    SOURCE_AEROLINK = "aerolink"
    SOURCE_CHOICES = [
        (SOURCE_MANUAL, _("Entered by hand")),
        (SOURCE_AEROLINK, _("Synced from AeroLink")),
    ]
    STATUS_CHOICES = [
        ("active", _("Active")),
        # A LiPo past its cycle life is a safety item (ISO 45001 6.1.2), not
        # just an inventory one -- it needs to be visibly out of service.
        ("retired", _("Retired")),
    ]

    tenant = models.ForeignKey(
        OperationalTenant,
        on_delete=models.PROTECT,
        default=get_default_tenant,
        related_name="batteries",
    )
    serial_number = models.CharField(
        max_length=100, unique=True, verbose_name=_("Serial number")
    )
    manufacturer = models.CharField(max_length=100, blank=True)
    model = models.CharField(max_length=100, blank=True)
    aircraft = models.ForeignKey(
        Aircraft,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="batteries",
        verbose_name=_("Last seen on aircraft"),
    )
    cycle_count = models.PositiveIntegerField(default=0, verbose_name=_("Cycles"))
    health_percent = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name=_("Health (%)")
    )
    firmware_version = models.CharField(max_length=50, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    first_use_date = models.DateField(null=True, blank=True)
    source = models.CharField(
        max_length=20, choices=SOURCE_CHOICES, default=SOURCE_MANUAL
    )
    synced_at = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Last synced")
    )

    class Meta:
        verbose_name = _("battery")
        verbose_name_plural = _("batteries")
        ordering = ["serial_number"]
        indexes = [
            models.Index(fields=["status", "is_active"], name="reg_battery_status_idx"),
            # X.4 will resolve incoming telemetry by serial, one lookup per
            # battery per session.
            models.Index(fields=["serial_number"], name="reg_battery_serial_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(health_percent__isnull=True) | Q(health_percent__lte=100),
                name="reg_battery_health_pct_max",
            )
        ]

    def __str__(self):
        label = self.model or self.manufacturer or _("Battery")
        return f"{label} · {self.serial_number}"

    def save(self, *args, **kwargs):
        # Same normalization as Aircraft.serial_number (X.1): a serial from DJI
        # never contains whitespace, and a hand-typed one must compare equal to
        # it. Unlike Aircraft this field is required, so an empty result is a
        # validation problem rather than a legitimate NULL -- left to clean().
        self.serial_number = "".join((self.serial_number or "").split())
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if not "".join((self.serial_number or "").split()):
            raise ValidationError(
                {"serial_number": _("A battery needs its serial number.")}
            )


class Operator(BaseModel):
    tenant = models.ForeignKey(
        OperationalTenant,
        on_delete=models.PROTECT,
        default=get_default_tenant,
        related_name="operators",
    )
    # Acronyms are spelled out here so the label lookup matches the catalog;
    # Django's derived labels would be "Employee id"/"Dgac credential".
    # T3.2 Fase 3: unique per tenant (global unique dropped; see
    # Meta.constraints) -- an employee id is an organization-internal id.
    employee_id = models.CharField(max_length=50, verbose_name=_("Employee ID"))
    full_name = models.CharField(max_length=150)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    rut = models.CharField(max_length=20, blank=True, verbose_name=_("RUT"))
    dgac_credential = models.CharField(
        max_length=30, blank=True, verbose_name=_("DGAC credential")
    )
    # LV-29: the credential's validity (the *Vigencia* column on the SIGO
    # operator screen), entered by the user from the DGAC capture. Drives the
    # list column, the alert rule, the calendar feed and the operator notice.
    credential_expiry = models.DateField(
        null=True, blank=True, verbose_name=_("DGAC credential expiry")
    )
    operator_type = models.CharField(max_length=80, blank=True)
    address = models.TextField(blank=True)
    authorizations = models.TextField(blank=True)
    cost_center = models.ForeignKey(
        CostCenter,
        on_delete=models.PROTECT,
        related_name="operators",
        null=True,
        blank=True,
    )
    # B3.2: "My work" needs to resolve the operator for the logged-in user.
    # Explicit and admin/form-set on purpose -- matching by email (like the
    # CostCenter.responsible_operator precedent avoided) could silently link
    # the wrong person if an address is stale or shared.
    user = models.OneToOneField(
        get_user_model(),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="operator_profile",
        verbose_name=_("Linked user account"),
        help_text=_('Optional. Lets this person see "My work" filtered to them.'),
    )

    class Meta:
        verbose_name = _("operator")
        verbose_name_plural = _("operators")
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "employee_id"],
                name="registry_operator_tenant_employee_uniq",
            )
        ]

    def __str__(self):
        return self.full_name

    @property
    def credential_is_overdue(self):
        """LV-29: the DGAC credential lapsed. ``None`` -- no date on file -- is
        unknown, not overdue (mirrors Aircraft.insurance_is_overdue)."""
        from django.utils import timezone

        return (
            self.credential_expiry is not None
            and self.credential_expiry < timezone.localdate()
        )


class Assignment(BaseModel):
    STATUS_CHOICES = [
        ("planned", _("Planned")),
        ("confirmed", _("Confirmed")),
        ("completed", _("Completed")),
        ("cancelled", _("Cancelled")),
    ]
    operator = models.ForeignKey(
        Operator, on_delete=models.PROTECT, related_name="assignments"
    )
    aircraft = models.ForeignKey(
        Aircraft, on_delete=models.PROTECT, related_name="assignments"
    )
    cost_center = models.ForeignKey(
        CostCenter,
        on_delete=models.PROTECT,
        related_name="assignments",
        null=True,
        blank=True,
    )
    # R3.1: same closed vocabulary as FlightPermission (apps.core.choices) --
    # optional here (blank=True), unlike the flight permit: LV-17 already
    # decided this is a supplementary note on an assignment, not a fact
    # every assignment must carry.
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES, blank=True)
    purpose_detail = models.CharField(max_length=250, blank=True, default="")
    purpose_legacy = models.CharField(
        max_length=250, blank=True, default="", editable=False
    )
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="planned")

    class Meta:
        verbose_name = _("assignment")
        verbose_name_plural = _("assignments")
        # The calendar and the overlap validation both filter by date range.
        indexes = [
            models.Index(
                fields=["start_date", "end_date"], name="reg_assignment_range_idx"
            )
        ]
        constraints = [
            models.CheckConstraint(
                condition=~Q(purpose="other") | ~Q(purpose_detail=""),
                name="reg_assignment_other_purpose_requires_detail",
            )
        ]

    def __str__(self):
        return f"{self.operator} · {self.aircraft}"

    def clean(self):
        # English source strings with the Spanish in the catalog, like the rest
        # of the project: these were hardcoded Spanish, so the English UI
        # showed Spanish errors and makemessages could not see them.
        errors = {}
        if self.end_date and self.end_date < self.start_date:
            errors["end_date"] = _("The end date cannot be before the start date.")
        if self.purpose == "other" and not self.purpose_detail:
            errors["purpose_detail"] = _(
                "Describe the purpose when 'Other' is selected."
            )
        if self.operator_id and not self.operator.is_active:
            errors["operator"] = _("The selected operator is inactive.")
        if self.aircraft_id and (
            not self.aircraft.is_active or self.aircraft.status != "active"
        ):
            errors["aircraft"] = _("The selected aircraft is not available.")
        if (
            self.cost_center_id
            and self.operator_id
            and self.operator.cost_center_id not in (None, self.cost_center_id)
        ):
            errors["cost_center"] = _("The cost center does not match the operator's.")
        if (
            self.cost_center_id
            and self.aircraft_id
            and self.aircraft.cost_center_id not in (None, self.cost_center_id)
        ):
            errors["cost_center"] = _("The cost center does not match the aircraft's.")
        if errors:
            raise ValidationError(errors)


class QualificationType(BaseModel):
    """Catalog of operator qualifications (B4.3), e.g. a DGAC rating per
    aircraft family.

    Free text drifted the same way document titles did (LV-1/LV-2): "Serie
    Mavic" vs "Mavic series" vs "MAVIC" for the same rating. A catalog keeps it
    consistent and gives B4.4 a structured place to declare which aircraft a
    rating authorizes.
    """

    name = models.CharField(max_length=150)
    code = models.CharField(max_length=50, unique=True)
    # B4.4: comma-separated, case-insensitive fragments matched against
    # Aircraft.model (Aircraft.type is uniformly "RPA" in the real data and
    # carries no signal). "mavic,matrice" means this rating authorizes any
    # aircraft whose model contains "mavic" or "matrice". Blank = matches
    # nothing until configured, so B4.4 stays silent rather than guessing.
    model_keywords = models.CharField(
        max_length=250,
        blank=True,
        verbose_name=_("Aircraft model keywords"),
        help_text=_(
            "Comma-separated fragments matched against the aircraft model "
            "(e.g. 'mavic, matrice'). Used to check operator–aircraft fit."
        ),
    )

    # LV-15: theme-aware, accessible Bootstrap "subtle" pairs used to colour the
    # equipment chips so each family is visibly differentiable at a glance.
    # `bg-danger` is deliberately absent -- it is reserved for expired chips.
    CHIP_PALETTE = (
        "bg-primary-subtle text-primary-emphasis",
        "bg-success-subtle text-success-emphasis",
        "bg-info-subtle text-info-emphasis",
        "bg-warning-subtle text-warning-emphasis",
        "bg-secondary-subtle text-secondary-emphasis",
        "bg-dark-subtle text-dark-emphasis",
    )

    class Meta:
        verbose_name = _("qualification type")
        verbose_name_plural = _("qualification types")

    def __str__(self):
        return self.name

    @property
    def chip_class(self):
        """LV-15: a stable colour class for this type's chips.

        Derived from `code` with a deterministic hash (crc32, not Python's
        per-process salted `hash()`) so the colour never shifts between
        requests or restarts, and every type -- present or future -- gets one
        without a migration or manual configuration.
        """
        index = zlib.crc32(self.code.encode("utf-8")) % len(self.CHIP_PALETTE)
        return self.CHIP_PALETTE[index]

    def keyword_list(self):
        return [k.strip().lower() for k in self.model_keywords.split(",") if k.strip()]


class Qualification(BaseModel):
    operator = models.ForeignKey(
        Operator, on_delete=models.PROTECT, related_name="qualifications"
    )
    qualification_type = models.ForeignKey(
        QualificationType,
        on_delete=models.PROTECT,
        related_name="qualifications",
    )
    # LV-12a: issue date is optional -- the imported roster records what an
    # operator is rated for, not when each rating was issued. Expiry likewise
    # optional (many DGAC ratings do not expire).
    issue_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = _("qualification")
        verbose_name_plural = _("qualifications")
        # The digest, the dashboard and generate_alerts all scan expiries.
        indexes = [
            models.Index(
                fields=["expiry_date", "is_active"], name="reg_qualification_exp_idx"
            )
        ]

    def __str__(self):
        return f"{self.qualification_type} · {self.operator}"


# ── BLOQUE OPS (OPS-1): per-resource assignments + movement log ───────────────
# The old `Assignment` (operator+aircraft pair) stays for now; these anchor a
# single resource to a cost center over a period, so an operator can rotate
# contracts and a cost center can hold N aircraft without duplicating operators.
# `Operator.cost_center` / `Aircraft.cost_center` become a denormalization of the
# current assignment, maintained by the signal in apps/registry/signals.py.


class ResourceAssignment(BaseModel):
    """Shared base: a resource assigned to a cost center over a period."""

    STATUS_CHOICES = [
        ("planned", _("Planned")),
        ("active", _("Active")),
        ("ended", _("Ended")),
        ("cancelled", _("Cancelled")),
    ]
    # A resource "holds" a cost center while an assignment is in one of these.
    ACTIVE_STATUSES = frozenset({"planned", "active"})

    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    # R3.1: same closed vocabulary as FlightPermission/Assignment, optional
    # here too (blank=True) -- unchanged from before this field held free
    # text (LV-17's decision that this is a supplementary note, not a
    # mandatory classification, still holds).
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES, blank=True)
    purpose_detail = models.CharField(max_length=250, blank=True, default="")
    purpose_legacy = models.CharField(
        max_length=250, blank=True, default="", editable=False
    )

    class Meta:
        abstract = True

    def _resource_id(self):
        return getattr(self, f"{self.resource_field}_id")

    def _overlapping(self):
        """Other active assignments for the same resource whose period overlaps.

        Ranges overlap iff each starts on or before the other ends; a null
        end_date is an open-ended (still current) assignment.
        """
        queryset = type(self).objects.filter(
            is_active=True,
            status__in=self.ACTIVE_STATUSES,
            **{f"{self.resource_field}_id": self._resource_id()},
        )
        if self.pk:
            queryset = queryset.exclude(pk=self.pk)
        if self.end_date is not None:
            queryset = queryset.filter(start_date__lte=self.end_date)
        return queryset.filter(
            Q(end_date__isnull=True) | Q(end_date__gte=self.start_date)
        )

    def clean(self):
        errors = {}
        if self.end_date and self.end_date < self.start_date:
            errors["end_date"] = _("The end date cannot be before the start date.")
        if self.purpose == "other" and not self.purpose_detail:
            errors["purpose_detail"] = _(
                "Describe the purpose when 'Other' is selected."
            )
        resource = getattr(self, self.resource_field, None)
        if self._resource_id() and resource and not resource.is_active:
            errors[self.resource_field] = _("The selected resource is inactive.")
        if (
            self._resource_id()
            and self.status in self.ACTIVE_STATUSES
            and self._overlapping().exists()
        ):
            errors[self.resource_field] = _(
                "This resource already has an overlapping active assignment."
            )
        if errors:
            raise ValidationError(errors)


class OperatorAssignment(ResourceAssignment):
    resource_field = "operator"
    operator = models.ForeignKey(
        Operator, on_delete=models.PROTECT, related_name="cc_assignments"
    )
    cost_center = models.ForeignKey(
        CostCenter, on_delete=models.PROTECT, related_name="operator_assignments"
    )

    class Meta:
        verbose_name = _("operator assignment")
        verbose_name_plural = _("operator assignments")
        indexes = [
            models.Index(
                fields=["cost_center", "is_active"], name="reg_opassign_cc_idx"
            ),
            models.Index(fields=["operator", "end_date"], name="reg_opassign_op_idx"),
        ]
        # R3.1: declared here, not on the abstract ResourceAssignment --
        # this Meta does not subclass the parent's, so its constraints
        # would not otherwise be created (confirmed empirically:
        # makemigrations skipped it when it only lived on the abstract).
        constraints = [
            models.CheckConstraint(
                condition=~Q(purpose="other") | ~Q(purpose_detail=""),
                name="reg_opassign_other_purpose_requires_detail",
            )
        ]

    def __str__(self):
        return f"{self.operator} → {self.cost_center}"


class AircraftAssignment(ResourceAssignment):
    resource_field = "aircraft"
    aircraft = models.ForeignKey(
        Aircraft, on_delete=models.PROTECT, related_name="cc_assignments"
    )
    cost_center = models.ForeignKey(
        CostCenter, on_delete=models.PROTECT, related_name="aircraft_assignments"
    )

    class Meta:
        verbose_name = _("aircraft assignment")
        verbose_name_plural = _("aircraft assignments")
        indexes = [
            models.Index(
                fields=["cost_center", "is_active"], name="reg_acassign_cc_idx"
            ),
            models.Index(fields=["aircraft", "end_date"], name="reg_acassign_ac_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~Q(purpose="other") | ~Q(purpose_detail=""),
                name="reg_acassign_other_purpose_requires_detail",
            )
        ]

    def __str__(self):
        return f"{self.aircraft} → {self.cost_center}"


class AppendOnlyLogQuerySet(models.QuerySet):
    """Block bulk mutation so the movement log stays append-only (like AuditEvent)."""

    def update(self, **kwargs):
        raise ValidationError("ResourceMovementLog records are append-only.")

    def delete(self):
        raise ValidationError("ResourceMovementLog records are append-only.")

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError("ResourceMovementLog records are append-only.")


class ResourceMovementLog(BaseModel):
    """Immutable trail of resource↔cost-center movements (the OPS-1 headline).

    Written by the assignment signal whenever a resource's current cost center
    changes. Not deleted or edited; that is the whole point of the trail.
    """

    RESOURCE_CHOICES = [("operator", _("Operator")), ("aircraft", _("Aircraft"))]
    MOVEMENT_CHOICES = [
        ("assigned", _("Assigned")),
        ("reassigned", _("Reassigned")),
        ("released", _("Released")),
        ("location_changed", _("Location changed")),  # OPS-3
    ]

    # `created_at` alone cannot order two rows created moments apart: on this
    # machine `timezone.now()` returns the *identical* value across rapid
    # successive calls (coarse clock resolution), and SQL gives no ordering
    # guarantee for ties on a non-unique column -- confirmed by
    # test_changing_cost_center_logs_reassigned flipping order under load.
    # `sequence` is computed in save() as "latest + 1" (same idiom as
    # GeoPlanVersion.version_number) instead of AutoField: Django requires an
    # AutoField to be the primary key, and BaseModel.id stays a UUID PK.
    sequence = models.PositiveBigIntegerField(editable=False)
    resource_kind = models.CharField(max_length=20, choices=RESOURCE_CHOICES)
    resource_id = models.UUIDField()
    movement = models.CharField(max_length=20, choices=MOVEMENT_CHOICES)
    from_cost_center = models.ForeignKey(
        CostCenter, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    to_cost_center = models.ForeignKey(
        CostCenter, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    detail = models.CharField(max_length=250, blank=True)
    changed_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    objects = AppendOnlyLogQuerySet.as_manager()

    class Meta:
        verbose_name = _("resource movement")
        verbose_name_plural = _("resource movements")
        ordering = ["-sequence"]
        indexes = [
            models.Index(fields=["-sequence"], name="reg_movement_seq_idx"),
            models.Index(
                fields=["resource_kind", "resource_id", "-sequence"],
                name="reg_movement_res_idx",
            ),
        ]

    def __str__(self):
        return f"{self.resource_kind}:{self.resource_id} {self.movement}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("ResourceMovementLog records are append-only.")
        # No uniqueness is enforced on this value: a rare race between two
        # concurrent writers computing the same "latest + 1" just means two
        # rows tie, no worse than the wall-clock collision this replaces, and
        # this app's write volume for movement events is low (docs/postgresql-
        # readiness.md: single-writer scale until real concurrency arrives).
        latest = ResourceMovementLog.objects.order_by("-sequence").first()
        self.sequence = (latest.sequence if latest else 0) + 1
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("ResourceMovementLog records are append-only.")
