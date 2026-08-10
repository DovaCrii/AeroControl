from django.apps import AppConfig


class MaintenanceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.maintenance"
    verbose_name = "Maintenance"

    def ready(self):
        from django.db.models.signals import pre_save
        from apps.core.signals import track_status_changes
        from .models import MaintenanceRecord
        from .signals import sync_maintenance_status_transition

        pre_save.connect(
            track_status_changes,
            sender=MaintenanceRecord,
            dispatch_uid="maintenance.track_record_status",
        )
        # R5.1: registered separately from track_status_changes above -- both
        # independently re-fetch the pre-save row to compare against, neither
        # mutates `.status` itself, so running in either order is safe.
        pre_save.connect(
            sync_maintenance_status_transition,
            sender=MaintenanceRecord,
            dispatch_uid="maintenance.sync_status_transition",
        )
