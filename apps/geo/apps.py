from django.apps import AppConfig


class GeoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.geo"
    verbose_name = "Geospatial planning"

    def ready(self):
        from django.db.models.signals import pre_save
        from apps.core.signals import track_status_changes
        from .models import GeoPlan

        pre_save.connect(
            track_status_changes,
            sender=GeoPlan,
            dispatch_uid="geo.track_plan_status",
        )
