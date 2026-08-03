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
