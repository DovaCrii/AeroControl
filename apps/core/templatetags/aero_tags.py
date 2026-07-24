from django import template
from django.db import models
from django.utils.translation import gettext as _

from apps.core.forms import translate_field_label

register = template.Library()

# Bookkeeping columns that mean nothing to an operator reading a record: the
# UUID, the audit timestamps, the archive flag and the tenancy key. They stay
# available in the Django admin.
TECHNICAL_FIELDS = frozenset({"id", "created_at", "updated_at", "is_active", "tenant"})


@register.filter
def fields_detail(obj):
    """Return a list of dicts with label/value/type info for each model field."""
    if not obj:
        return []
    result = []
    for field in obj._meta.fields:
        if field.name in TECHNICAL_FIELDS:
            continue
        raw = getattr(obj, field.name)
        is_boolean = isinstance(field, (models.BooleanField, models.NullBooleanField))
        is_choice = bool(getattr(field, "choices", None))
        is_date = isinstance(field, (models.DateField, models.DateTimeField))
        is_url = (
            isinstance(field, models.URLField) if hasattr(models, "URLField") else False
        )

        choice_value = None
        if is_choice and raw is not None:
            choice_value = dict(field.choices).get(raw, raw)

        result.append(
            {
                # Same normalise-then-translate path AeroModelForm uses for its
                # labels, so the detail page and the edit form agree instead of
                # showing English here and Spanish there.
                "label": _(translate_field_label(field.verbose_name)),
                "value": raw if raw is not None else "",
                "is_boolean": is_boolean,
                "is_choice": is_choice,
                "choice_value": choice_value,
                "is_date": is_date,
                "is_url": is_url,
            }
        )
    return result


@register.filter
def model_verbose_name(obj):
    """Return the verbose name for a model instance or class."""
    if hasattr(obj, "_meta"):
        return obj._meta.verbose_name.title()
    return ""


@register.simple_tag
def model_verbose_name_plural(model):
    """Return the verbose name plural for a model class."""
    if hasattr(model, "_meta"):
        return model._meta.verbose_name_plural.title()
    return ""


@register.inclusion_tag("generic/_pagination.html")
def render_pagination(page_obj):
    """Render pagination controls for a page object."""
    return {"page_obj": page_obj}
