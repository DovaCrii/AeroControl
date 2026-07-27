from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from apps.core.models import BaseModel, OperationalTenant


class CostCenter(BaseModel):
    tenant = models.ForeignKey(
        OperationalTenant,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cost_centers",
    )
    code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=150)
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
    responsible_contact_name = models.CharField(max_length=150, blank=True)
    responsible_contact_email = models.EmailField(blank=True)

    def __str__(self):
        label = f"{self.code} - {self.name}"
        return f"{label} · {self.responsible}" if self.responsible else label

    class Meta:
        # Translated names: user-facing messages interpolate verbose_name
        # ("%(name)s archived"), and without this they said "Operator" inside
        # a Spanish sentence.
        verbose_name = _("cost center")
        verbose_name_plural = _("cost centers")

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
        null=True,
        blank=True,
        related_name="aircraft",
    )
    STATUS_CHOICES = [
        ("active", _("Active")),
        ("maintenance", _("Maintenance")),
        ("retired", _("Retired")),
    ]
    registration = models.CharField(max_length=30, unique=True)
    type = models.CharField(max_length=100)
    model = models.CharField(max_length=100)
    manufacturer = models.CharField(max_length=100)
    year = models.PositiveIntegerField(null=True, blank=True)
    serial_number = models.CharField(max_length=100, blank=True)
    max_takeoff_weight_kg = models.DecimalField(
        max_digits=8, decimal_places=3, null=True, blank=True
    )
    basic_weight_kg = models.DecimalField(
        max_digits=8, decimal_places=3, null=True, blank=True
    )
    vlos = models.CharField(max_length=20, blank=True, verbose_name=_("VLOS"))
    parachute = models.CharField(max_length=20, blank=True)
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


class Operator(BaseModel):
    tenant = models.ForeignKey(
        OperationalTenant,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="operators",
    )
    # Acronyms are spelled out here so the label lookup matches the catalog;
    # Django's derived labels would be "Employee id"/"Dgac credential".
    employee_id = models.CharField(
        max_length=50, unique=True, verbose_name=_("Employee ID")
    )
    full_name = models.CharField(max_length=150)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    rut = models.CharField(max_length=20, blank=True, verbose_name=_("RUT"))
    dgac_credential = models.CharField(
        max_length=30, blank=True, verbose_name=_("DGAC credential")
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

    class Meta:
        verbose_name = _("operator")
        verbose_name_plural = _("operators")

    def __str__(self):
        return self.full_name


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
    purpose = models.CharField(max_length=250, blank=True)
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

    def __str__(self):
        return f"{self.operator} · {self.aircraft}"

    def clean(self):
        # English source strings with the Spanish in the catalog, like the rest
        # of the project: these were hardcoded Spanish, so the English UI
        # showed Spanish errors and makemessages could not see them.
        errors = {}
        if self.end_date and self.end_date < self.start_date:
            errors["end_date"] = _("The end date cannot be before the start date.")
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


class Qualification(BaseModel):
    operator = models.ForeignKey(
        Operator, on_delete=models.PROTECT, related_name="qualifications"
    )
    qualification_type = models.CharField(max_length=150)
    issue_date = models.DateField()
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
    purpose = models.CharField(max_length=250, blank=True)

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
