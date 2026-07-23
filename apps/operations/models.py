from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from apps.core.models import BaseModel
from apps.registry.models import Operator, Aircraft, CostCenter


class FlightPermission(BaseModel):
    STATUS_CHOICES = [
        ("requested", _("Requested")),
        ("approved", _("Approved")),
        ("denied", _("Denied")),
        ("completed", _("Completed")),
    ]
    permission_number = models.CharField(max_length=50, unique=True)
    operator = models.ForeignKey(Operator, on_delete=models.PROTECT)
    aircraft = models.ForeignKey(Aircraft, on_delete=models.PROTECT)
    cost_center = models.ForeignKey(CostCenter, on_delete=models.PROTECT)
    purpose = models.CharField(max_length=250)
    flight_date = models.DateField()
    location = models.CharField(max_length=250)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="requested"
    )

    def __str__(self):
        return self.permission_number

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("permission-detail", kwargs={"pk": self.pk})


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

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("record-detail", kwargs={"pk": self.pk})


class PermissionHistory(BaseModel):
    permission = models.ForeignKey(
        FlightPermission, on_delete=models.CASCADE, related_name="history"
    )
    previous_status = models.CharField(max_length=20)
    new_status = models.CharField(max_length=20)
    changed_by = models.CharField(max_length=150)
    changed_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="permission_history_events",
    )
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = "Permission histories"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.permission}: {self.previous_status} → {self.new_status}"
