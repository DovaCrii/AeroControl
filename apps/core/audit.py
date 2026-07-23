"""Explicit request-to-record audit context helpers."""


def set_audit_context(request, instance, action=None):
    if instance is None:
        return
    request._audit_context = {
        "model_label": instance._meta.label,
        "object_id": str(instance.pk),
    }
    if action:
        request._audit_context["action"] = action
