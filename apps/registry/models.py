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
    operator = models.ForeignKey(
        Operator, on_delete=models.PROTECT, related_name="assignments"
    )
    aircraft = models.ForeignKey(
        Aircraft, on_delete=models.PROTECT, related_name="assignments"
    )
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)


class Qualification(BaseModel):
    operator = models.ForeignKey(
        Operator, on_delete=models.PROTECT, related_name="qualifications"
    )
    qualification_type = models.CharField(max_length=150)
    issue_date = models.DateField()
    expiry_date = models.DateField(null=True, blank=True)
