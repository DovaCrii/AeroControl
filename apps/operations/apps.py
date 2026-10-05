from django.apps import AppConfig


class OperationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.operations"
    verbose_name = "Operations"

    def ready(self):
        from django.db.models.signals import pre_save
        from apps.core.signals import track_status_changes
        from .models import FlightRequest

        # T1.3: `FlightPermission` ya no pasa por acá. Su historial lo escribe
        # `StatusHistoryMixin` dentro del guardado; si siguiera conectada, cada
        # cambio de estado dejaría **dos** filas.
        pre_save.connect(
            track_status_changes,
            sender=FlightRequest,
            dispatch_uid="operations.track_request_status",
        )
