from django.core.exceptions import ValidationError
from django.db import models
from apps.core.models import BaseModel, OperationalTenant


class CostCenter(BaseModel):
    tenant = models.ForeignKey(
        OperationalTenant, on_delete=models.PROTECT, null=True, blank=True,
        related_name="cost_centers",
    )
    code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=150)
    responsible = models.CharField(max_length=150, blank=True)

    def __str__(self):
        label = f"{self.code} - {self.name}"
        return f"{label} · {self.responsible}" if self.responsible else label


class Aircraft(BaseModel):
    tenant = models.ForeignKey(
        OperationalTenant, on_delete=models.PROTECT, null=True, blank=True,
        related_name="aircraft",
    )
    STATUS_CHOICES = [
        ("active", "Active"),
        ("maintenance", "Maintenance"),
        ("retired", "Retired"),
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
    vlos = models.CharField(max_length=20, blank=True)
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
        OperationalTenant, on_delete=models.PROTECT, null=True, blank=True,
        related_name="operators",
    )
    employee_id = models.CharField(max_length=50, unique=True)
    full_name = models.CharField(max_length=150)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    rut = models.CharField(max_length=20, blank=True)
    dgac_credential = models.CharField(max_length=30, blank=True)
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
        ("planned", "Planned"),
        ("confirmed", "Confirmed"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
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

    def __str__(self):
        return f"{self.operator} · {self.aircraft}"

    def clean(self):
        errors = {}
        if self.end_date and self.end_date < self.start_date:
            errors["end_date"] = "La fecha final no puede ser anterior a la fecha inicial."
        if self.operator_id and not self.operator.is_active:
            errors["operator"] = "El operador seleccionado está inactivo."
        if self.aircraft_id and (not self.aircraft.is_active or self.aircraft.status != "active"):
            errors["aircraft"] = "La aeronave seleccionada no está disponible."
        if self.cost_center_id and self.operator_id and self.operator.cost_center_id not in (None, self.cost_center_id):
            errors["cost_center"] = "El centro de costo no coincide con el del operador."
        if self.cost_center_id and self.aircraft_id and self.aircraft.cost_center_id not in (None, self.cost_center_id):
            errors["cost_center"] = "El centro de costo no coincide con el de la aeronave."
        if errors:
            raise ValidationError(errors)


class Qualification(BaseModel):
    operator = models.ForeignKey(
        Operator, on_delete=models.PROTECT, related_name="qualifications"
    )
    qualification_type = models.CharField(max_length=150)
    issue_date = models.DateField()
    expiry_date = models.DateField(null=True, blank=True)
