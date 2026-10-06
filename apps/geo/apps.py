from django.apps import AppConfig


class GeoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.geo"
    verbose_name = "Geospatial planning"

    def ready(self):
        from django.db.models.signals import pre_save
        from .models import GeoPlan
        from .signals import track_flight_permission_link

        # T1.3: el historial de estados ya no se conecta acá. Lo escribe
        # `StatusHistoryMixin` dentro del guardado; si siguiera conectado a
        # `track_status_changes`, cada cambio de estado dejaría **dos** filas.
        #
        # OPS-7: esta señal sigue siendo `pre_save`, pero como corre dentro de
        # `Model.save` ahora entra en la transacción del mixin: si el guardado
        # falla, el registro del enlace con el permiso se deshace con él.
        pre_save.connect(
            track_flight_permission_link,
            sender=GeoPlan,
            dispatch_uid="geo.track_flight_permission_link",
        )
