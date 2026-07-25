from django.core.exceptions import ValidationError
from django.db import models
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

    def __str__(self):
        label = f"{self.code} - {self.name}"
        return f"{label} · {self.responsible}" if self.responsible else label

    @property
    def notification_email(self):
        """Email to notify for this cost center, or "" when unreachable."""
        operator = self.responsible_operator
        return operator.email if operator and operator.email else ""


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

    def __str__(self):
        return self.registration


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
            errors["cost_center"] = _(
                "The cost center does not match the operator's."
            )
        if (
            self.cost_center_id
            and self.aircraft_id
            and self.aircraft.cost_center_id not in (None, self.cost_center_id)
        ):
            errors["cost_center"] = _(
                "The cost center does not match the aircraft's."
            )
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
