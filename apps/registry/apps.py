from django.apps import AppConfig


class RegistryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.registry"
    verbose_name = "Registry"

    def ready(self):
        from django.db.models.signals import post_delete, post_save

        from .models import AircraftAssignment, OperatorAssignment
        from .signals import sync_aircraft_assignment, sync_operator_assignment

        # Keep Operator/Aircraft.cost_center and the movement log in sync with
        # per-resource assignments (OPS-1).
        for signal in (post_save, post_delete):
            signal.connect(
                sync_operator_assignment,
                sender=OperatorAssignment,
                dispatch_uid="ops_sync_operator_assignment",
            )
            signal.connect(
                sync_aircraft_assignment,
                sender=AircraftAssignment,
                dispatch_uid="ops_sync_aircraft_assignment",
            )
