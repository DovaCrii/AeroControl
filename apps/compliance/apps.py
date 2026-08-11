from django.apps import AppConfig


class ComplianceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.compliance"
    verbose_name = "Compliance"

    def ready(self):
        """LV-71: renewing a watched date closes its own alert.

        Connected to every watchable model that exposes a date rule
        (`watchables.WATCHABLE_MODELS`), skipping the two whose rules watch
        `status` instead -- MaintenanceRecord and MonthlyComplianceReview
        already close their alerts through `resolve_open_alerts_for`, so wiring
        them here would only duplicate a path that works.

        Resolved by label rather than importing the models, because this runs
        inside `ready()` and importing another app's models at that point is
        how AppRegistryNotReady happens.
        """
        from django.apps import apps as django_apps
        from django.db.models.signals import post_save

        from .signals import resolve_alerts_when_watched_date_is_renewed

        for label in (
            "registry.Aircraft",
            "registry.Operator",
            "registry.Qualification",
            "operations.FlightPermission",
            "compliance.Document",
        ):
            post_save.connect(
                resolve_alerts_when_watched_date_is_renewed,
                sender=django_apps.get_model(label),
                dispatch_uid=f"compliance.autoclose.{label}",
            )
