from django.apps import AppConfig


class OperationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.operations"
    verbose_name = "Operations"

    # T1.3: esta app ya no conecta ninguna señal. El historial de estados de
    # `FlightPermission` y de `FlightRequest` lo escribe `StatusHistoryMixin`
    # dentro del guardado; si alguna siguiera conectada a `track_status_changes`,
    # cada cambio de estado dejaría **dos** filas.

    def ready(self):
        # LV-427: analizar el log de vuelo al adjuntarlo. Es la única señal de esta app y no toca
        # el historial de estados (ver nota de arriba).
        from django.db.models.signals import post_save

        from apps.compliance.models import Document

        from .flightlog.service import on_document_saved

        post_save.connect(
            on_document_saved, sender=Document, dispatch_uid="lv427_flightlog"
        )
