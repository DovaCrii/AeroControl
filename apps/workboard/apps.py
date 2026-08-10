from django.apps import AppConfig


class WorkboardConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.workboard"
    verbose_name = "Workboard"

    def ready(self):
        from django.db.models.signals import post_save
        from .models import KanbanTask
        from .signals import resolve_alert_when_task_completes

        post_save.connect(
            resolve_alert_when_task_completes,
            sender=KanbanTask,
            dispatch_uid="workboard.resolve_alert_when_task_completes",
        )
