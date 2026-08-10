"""R6.1 [bug]: the other half of Alert.resolve() -- moving a task into a
"completed" stage now resolves the alert that spawned it too, not just the
reverse. Before this, resolving the alert moved the task, but completing
the task by hand (drag-and-drop, the API) never resolved the alert, so the
"needs attention" alert lingered after the actual work was done.

post_save, not pre_save: Alert.resolve() re-fetches the task with its own
query and, if the task is not already on the board's *canonical* completed
stage (first by `order`), saves it there itself. Hooking this at pre_save
would race that inner save against this task's own not-yet-committed
change and lose -- whichever write lands last wins, and pre_save's own
outer save always lands after a signal handler it called returns. Firing
after the commit means Alert.resolve()'s own move (if any) is the last
write, so it sticks. The is_resolved=False filter below is what stops the
second post_save re-entry (from that inner save) from resolving twice.
"""

from django.contrib.contenttypes.models import ContentType


def resolve_alert_when_task_completes(sender, instance, **kwargs):
    if instance.stage_id is None or instance.stage.status_type != "completed":
        return
    if not instance.source_content_type_id:
        return

    from apps.compliance.models import Alert

    alert_ct = ContentType.objects.get_for_model(Alert)
    if instance.source_content_type_id != alert_ct.id:
        return
    try:
        alert = Alert.objects.get(
            pk=instance.source_object_id, is_active=True, is_resolved=False
        )
    except Alert.DoesNotExist:
        return
    alert.resolve()
