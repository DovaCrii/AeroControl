"""Resolve open alerts pointing at an arbitrary watched record.

`Document.resolve_related_alerts` closes a document's alerts when a new version
supersedes it; the same shape is needed when a maintenance record is completed
(LV-26) so its "open maintenance" alert clears without a manual step. This is
that logic, generic over the watched object.
"""

from django.contrib.contenttypes.models import ContentType

from .models import Alert


def resolve_open_alerts_for(obj):
    """Resolve every open alert whose subject is `obj`. Returns the count.

    Each is closed via Alert.resolve(), so any linked Kanban task closes too.
    """
    content_type = ContentType.objects.get_for_model(obj)
    open_alerts = Alert.objects.filter(
        content_type=content_type,
        object_id=obj.pk,
        is_resolved=False,
        is_active=True,
    )
    resolved = 0
    for alert in open_alerts:
        alert.resolve()
        resolved += 1
    return resolved
