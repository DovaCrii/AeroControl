"""The models an AlertRule may watch, and which of their fields.

Before this, `entity_type` and `field_to_watch` were free text resolved at run
time by fuzzy-matching every installed model's name, so a typo produced a rule
that silently never fired, and two models sharing a name were
indistinguishable (AUDIT_CLAUDE.md A3). The registry below is the single source
of truth for the model's clean(), the form's choices and the command.
"""

from django.apps import apps as django_apps
from django.db import models
from django.utils.translation import gettext_lazy as _

# Keys are "app_label.modelname" (lowercase), which is unambiguous.
WATCHABLE_MODELS = {
    "registry.qualification": _("Qualification"),
    # LV-29: the DGAC vigencias. The only date field either model exposes is the
    # new expiry (Aircraft.status is a choices field, also offered), so the rule
    # picker cannot point at an irrelevant timestamp.
    "registry.operator": _("Operator"),
    "registry.aircraft": _("Aircraft"),
    "compliance.document": _("Document"),
    "operations.flightpermission": _("Flight permission"),
    "maintenance.maintenancerecord": _("Maintenance record"),
}

# Timestamps every model inherits from BaseModel: watching them is never what
# an operator means by "expiry".
EXCLUDED_FIELDS = frozenset({"created_at", "updated_at"})

# Legacy free-text values seen in the data, mapped to canonical keys so the
# data migration can normalise instead of discarding usable rules.
LEGACY_ENTITY_TYPES = {
    "qualification": "registry.qualification",
    "qualifications": "registry.qualification",
    "document": "compliance.document",
    "documents": "compliance.document",
    "flightpermission": "operations.flightpermission",
    "flight_permission": "operations.flightpermission",
    "permission": "operations.flightpermission",
    "maintenancerecord": "maintenance.maintenancerecord",
    "maintenance_record": "maintenance.maintenancerecord",
    "maintenance": "maintenance.maintenancerecord",
}


def canonical_entity_type(value):
    """Map a stored entity_type to a registry key, or None if unknown."""
    if not value:
        return None
    raw = str(value).strip()
    lowered = raw.lower()
    if lowered in WATCHABLE_MODELS:
        return lowered
    return LEGACY_ENTITY_TYPES.get(lowered.replace("-", "_"))


def resolve_model(entity_type):
    """Return the model for an entity_type, or None when it is not watchable."""
    key = canonical_entity_type(entity_type)
    if key is None:
        return None
    app_label, model_name = key.split(".", 1)
    try:
        return django_apps.get_model(app_label, model_name)
    except LookupError:
        return None


def watchable_fields(model):
    """Date fields (plus a `status` with choices) that a rule may watch."""
    if model is None:
        return []
    names = []
    for field in model._meta.fields:
        if field.name in EXCLUDED_FIELDS:
            continue
        if isinstance(field, models.DateField):
            names.append(field.name)
        elif field.name == "status" and field.choices:
            names.append(field.name)
    return names


def entity_type_choices():
    return [(key, label) for key, label in WATCHABLE_MODELS.items()]


def field_choices_for(entity_type):
    return [(name, name) for name in watchable_fields(resolve_model(entity_type))]
