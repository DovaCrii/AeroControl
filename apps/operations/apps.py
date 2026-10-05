from django.apps import AppConfig


class OperationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.operations"
    verbose_name = "Operations"

    # T1.3: esta app ya no conecta ninguna señal. El historial de estados de
    # `FlightPermission` y de `FlightRequest` lo escribe `StatusHistoryMixin`
    # dentro del guardado; si alguna siguiera conectada a `track_status_changes`,
    # cada cambio de estado dejaría **dos** filas.
