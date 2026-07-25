from django.db import models
from django.conf import settings
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

    class Meta:
        verbose_name = _("maintenance record")
        verbose_name_plural = _("maintenance records")
        # The calendar filters (scheduled_date, is_active) on every feed request.
        indexes = [
            models.Index(
                fields=["scheduled_date", "is_active"], name="maint_record_date_idx"
            )
        ]

    def __str__(self):
        return f"{self.get_maintenance_type_display()} · {self.aircraft}"

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("maintenance-detail", kwargs={"pk": self.pk})


class MaintenanceHistory(BaseModel):
    record = models.ForeignKey(
        MaintenanceRecord, on_delete=models.PROTECT, related_name="history"
    )
    changed_at = models.DateTimeField(auto_now_add=True)
    previous_status = models.CharField(max_length=20)
    new_status = models.CharField(max_length=20)
    changed_by = models.CharField(max_length=150)
    changed_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="maintenance_history_events",
    )
