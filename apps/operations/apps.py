from django.apps import AppConfig


class OperationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.operations"
    verbose_name = "Operations"

    def ready(self):
        from django.db.models.signals import pre_save
        from apps.core.signals import track_status_changes
        from .models import FlightPermission

        pre_save.connect(
            track_status_changes,
            sender=FlightPermission,
            dispatch_uid="operations.track_permission_status",
        )
