from django.apps import AppConfig


class RegistryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.registry"
    verbose_name = "Registry"

    def ready(self):
        from django.db.models.signals import post_delete, post_save, pre_save

        from .models import Aircraft, AircraftAssignment, OperatorAssignment
        from .signals import (
            sync_aircraft_assignment,
            sync_operator_assignment,
            track_aircraft_location,
        )

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
        # Log Aircraft.current_location/current_site changes (OPS-3).
        pre_save.connect(
            track_aircraft_location,
            sender=Aircraft,
            dispatch_uid="ops_track_aircraft_location",
        )
