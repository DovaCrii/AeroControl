"""Explicit request-to-record audit context helpers."""


def set_audit_context(request, instance, action=None, metadata=None):
    if instance is None:
        return
    # DRF wraps the Django HttpRequest in a rest_framework.request.Request; the
    # audit middleware reads _audit_context off the underlying HttpRequest, so
    # unwrap once here to reach it. No-op for plain Django requests.
    request = getattr(request, "_request", request)
    request._audit_context = {
        "model_label": instance._meta.label,
        "object_id": str(instance.pk),
    }
    if action:
        request._audit_context["action"] = action
    if metadata:
        request._audit_context["metadata"] = dict(metadata)


def add_audit_sibling(request, instance, action=None):
    """Otra fila mutada en la **misma** petición, con su propia entrada.

    LV-176: el middleware escribe una entrada por petición, y hasta ahora eso
    alcanzaba porque cada vista tocaba un registro. Archivar un plan junto con
    sus permisos ligados son N+1 mutaciones en un POST, y llamar
    `set_audit_context` N+1 veces **no** las registra: cada llamada pisa a la
    anterior y sólo sobrevive la última.

    La alternativa era escribir las filas a mano desde la vista, y se descartó:
    ahí no se conoce todavía el código de estado de la respuesta ni el
    `request_id`, así que las entradas hermanas saldrían peores que la principal
    justo en los campos con los que se rastrea una petición. Con esto el
    middleware sigue siendo el único que escribe, y todas comparten `request_id`
    — que es lo que después permite ver que fue **un solo acto**.

    Lo que se gana en concreto: quien pregunte por qué se cerró ese permiso
    encuentra la respuesta **en el permiso**, no sólo en el plan que lo arrastró.
    """
    if instance is None:
        return
    request = getattr(request, "_request", request)
    siblings = request.__dict__.setdefault("_audit_siblings", [])
    siblings.append(
        {
            "model_label": instance._meta.label,
            "object_id": str(instance.pk),
            "action": action,
        }
    )
