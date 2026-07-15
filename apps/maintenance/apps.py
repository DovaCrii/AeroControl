from django.apps import AppConfig


class MaintenanceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.maintenance"
    verbose_name = "Maintenance"

    def ready(self):
        from django.db.models.signals import pre_save
        from apps.core.signals import track_status_changes
        from .models import MaintenanceRecord

        pre_save.connect(
            track_status_changes,
            sender=MaintenanceRecord,
            dispatch_uid="maintenance.track_record_status",
        )
