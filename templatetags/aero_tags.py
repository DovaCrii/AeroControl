from django import template
from django.db import models

register = template.Library()


@register.filter
def fields_detail(obj):
    """Return a list of dicts with label/value/type info for each model field."""
    if not obj:
        return []
    result = []
    for field in obj._meta.fields:
        raw = getattr(obj, field.name)
        is_boolean = isinstance(field, (models.BooleanField, models.NullBooleanField))
        is_choice = bool(getattr(field, 'choices', None))
        is_date = isinstance(field, (models.DateField, models.DateTimeField))
        is_url = isinstance(field, models.URLField) if hasattr(models, 'URLField') else False

        value_display = raw
        choice_value = None
        if is_choice and raw is not None:
            choice_value = dict(field.choices).get(raw, raw)

        result.append({
            'label': field.verbose_name.title(),
            'value': raw if raw is not None else '',
            'is_boolean': is_boolean,
            'is_choice': is_choice,
            'choice_value': choice_value,
            'is_date': is_date,
            'is_url': is_url,
        })
    return result


@register.filter
def model_verbose_name(obj):
    """Return the verbose name for a model instance or class."""
    if hasattr(obj, '_meta'):
        return obj._meta.verbose_name.title()
    return ''


@register.simple_tag
def model_verbose_name_plural(model):
    """Return the verbose name plural for a model class."""
    if hasattr(model, '_meta'):
        return model._meta.verbose_name_plural.title()
    return ''


@register.inclusion_tag('generic/_pagination.html')
def render_pagination(page_obj):
    """Render pagination controls for a page object."""
    return {'page_obj': page_obj}
