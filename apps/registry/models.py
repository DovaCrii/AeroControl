from django.db import models
from apps.core.models import BaseModel


class CostCenter(BaseModel):
    code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=150)

    def __str__(self):
        return f"{self.code} - {self.name}"


class Aircraft(BaseModel):
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
    cost_center = models.ForeignKey(
        CostCenter, on_delete=models.PROTECT, related_name="aircraft"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")

    def __str__(self):
        return self.registration


class Operator(BaseModel):
    employee_id = models.CharField(max_length=50, unique=True)
    full_name = models.CharField(max_length=150)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    cost_center = models.ForeignKey(
        CostCenter, on_delete=models.PROTECT, related_name="operators"
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
