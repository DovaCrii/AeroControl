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
        # LV-81: trace the insurance filing. A second pre_save receiver on the
        # same sender, like maintenance already does -- both re-fetch the
        # pre-save row independently and neither mutates the other's field, so
        # the order they run in does not matter.
        from apps.core.signals import track_status_changes

        pre_save.connect(
            track_status_changes,
            sender=Aircraft,
            dispatch_uid="registry.track_insurance_status",
        )
        # LV-159: la Resolución de la JAC pone la vigencia (y el estado) del
        # seguro en la aeronave de la que cuelga. Va por señal y no en cada vista
        # de carga porque hay **tres** caminos por los que un documento entra
        # —alta, "Subir varios" y reemplazo de versión— y una regla escrita tres
        # veces es una regla que uno de los tres deja de cumplir.
        #
        # El modelo se resuelve por etiqueta: importar los modelos de otra app
        # dentro de `ready()` es cómo aparece `AppRegistryNotReady` (mismo
        # cuidado que en `ComplianceConfig.ready`).
        from django.apps import apps as django_apps

        from .signals import sync_insurance_when_jac_resolution_lands

        post_save.connect(
            sync_insurance_when_jac_resolution_lands,
            sender=django_apps.get_model("compliance.Document"),
            dispatch_uid="registry.sync_insurance_from_jac_resolution",
        )
