from django.apps import AppConfig


class MaintenanceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.maintenance"
    verbose_name = "Maintenance"

    def ready(self):
        from django.db.models.signals import pre_save
        from .models import MaintenanceRecord
        from .signals import sync_maintenance_status_transition

        # T1.3: el historial de estados ya no se conecta acá. Lo escribe
        # `StatusHistoryMixin` dentro del guardado; si siguiera conectado a
        # `track_status_changes`, cada cambio de estado dejaría **dos** filas.
        #
        # R5.1: esta señal sigue siendo `pre_save` (modifica `status_changed_at` de
        # la propia fila antes de guardarla, y la aeronave), pero como corre dentro
        # de `Model.save` ahora entra en la transacción del mixin: si el guardado
        # falla, la aeronave no queda en «mantención».
        pre_save.connect(
            sync_maintenance_status_transition,
            sender=MaintenanceRecord,
            dispatch_uid="maintenance.sync_status_transition",
        )
