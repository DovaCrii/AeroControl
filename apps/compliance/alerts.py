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


def resolve_expiry_alerts_for(obj, reason=""):
    """LV-325: cierra los avisos de vencimiento abiertos de `obj`, con motivo.

    Son los de las reglas que vigilan `valid_until` del permiso -- la de 30 días
    y la cadena de renovación de 45 (`LV-226`). Se cierran por el campo vigilado
    y no por el nombre ni por los días: el nombre de una regla se edita en la
    interfaz y los días también, pero lo que la hace «aviso de vencimiento» es
    el campo. Cualquier otra alerta del mismo permiso queda como estaba.

    Usa `Alert.resolve()`, el mismo cierre de siempre, así que la tarjeta del
    tablero enlazada se cierra también. Devuelve la cantidad cerrada.
    """
    content_type = ContentType.objects.get_for_model(obj)
    open_alerts = Alert.objects.filter(
        content_type=content_type,
        object_id=obj.pk,
        is_resolved=False,
        is_active=True,
        alert_rule__field_to_watch="valid_until",
    ).select_related("alert_rule")
    resolved = 0
    for alert in open_alerts:
        alert.resolve(reason=reason)
        resolved += 1
    return resolved
