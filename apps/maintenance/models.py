from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.core.models import BaseModel
from apps.registry.models import Aircraft


class MaintenanceRecord(BaseModel):
    TYPES = [
        ("scheduled", _("Scheduled")),
        ("unscheduled", _("Unscheduled")),
        ("emergency", _("Emergency")),
    ]
    STATUSES = [
        ("pending", _("Pending")),
        ("in_progress", _("In progress")),
        ("completed", _("Completed")),
    ]
    aircraft = models.ForeignKey(
        Aircraft, on_delete=models.PROTECT, related_name="maintenance_records"
    )
    maintenance_type = models.CharField(max_length=20, choices=TYPES)
    description = models.TextField()
    scheduled_date = models.DateField()
    completed_date = models.DateField(null=True, blank=True)
    performed_by = models.CharField(max_length=150)
    cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUSES, default="pending")

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("maintenance-detail", kwargs={"pk": self.pk})


class MaintenanceHistory(BaseModel):
    record = models.ForeignKey(
        MaintenanceRecord, on_delete=models.CASCADE, related_name="history"
    )
    changed_at = models.DateTimeField(auto_now_add=True)
    previous_status = models.CharField(max_length=20)
    new_status = models.CharField(max_length=20)
    changed_by = models.CharField(max_length=150)
