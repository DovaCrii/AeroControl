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
    # LV-30: a pending monthly review is a live alert (watched via `status`).
    "compliance.monthlycompliancereview": _("Monthly compliance review"),
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


def terminal_statuses(model):
    """The statuses that mean this record is closed, as the model declares them.

    LV-90. A rule watching a `status` field alerts while the record is still
    open, so "open" has to be defined somewhere -- and it used to be a literal
    tuple inside `generate_alerts` holding the vocabularies of three different
    models at once. Every new terminal status then depended on somebody
    remembering that line, and forgetting it fails **silently**: alerts that
    keep firing for something already closed.

    Empty for a model that declares none, which is the honest reading of "no
    status of this model ends anything" -- `test_watchable_models_declare_their
    _terminal_statuses` is what stops that from silently meaning "nobody got
    round to it".
    """
    return frozenset(getattr(model, "TERMINAL_STATUSES", frozenset()))


def alert_subject_querysets():
    """One queryset per watchable model, with its foreign keys already joined.

    LV-106. `prefetch_related("content_object")` alone resolves the generic
    relation but hands back bare instances, and the alerts list renders each
    subject by calling `str()` on it -- and several of those `__str__` cross a
    relation (a qualification names its operator and its type). So the list went
    from one query per row to two, which is not the fix anybody wanted.

    The joins are **derived from each model**, not listed by hand: a hand list is
    the shape this project has already been bitten by (the literal terminal
    statuses of LV-90, the calendar's seven event types of R1.1). Every
    many-to-one field is joined -- a couple of extra columns per row, against one
    query per row.
    """
    querysets = []
    for key in WATCHABLE_MODELS:
        model = resolve_model(key)
        if model is None:
            continue
        related = [
            field.name
            for field in model._meta.fields
            if field.is_relation and field.many_to_one
        ]
        queryset = model._default_manager.all()
        querysets.append(queryset.select_related(*related) if related else queryset)
    return querysets


def entity_type_choices():
    return [(key, label) for key, label in WATCHABLE_MODELS.items()]


def field_choices_for(entity_type):
    return [(name, name) for name in watchable_fields(resolve_model(entity_type))]
