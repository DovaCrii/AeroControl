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
def fields_detail(obj, exclude=""):
    """Return a list of dicts with label/value/type info for each model field.

    `exclude` (comma-separated field names) is for a field that a detail page
    replaced with something better -- e.g. Operator.authorizations (R5.8),
    superseded on the ficha by a real Qualification section. Distinct from
    TECHNICAL_FIELDS, which hides bookkeeping columns on every model; this is
    a per-page opt-out for one specific business field.
    """
    if not obj:
        return []
    excluded = TECHNICAL_FIELDS | {
        name.strip() for name in exclude.split(",") if name.strip()
    }
    result = []
    for field in obj._meta.fields:
        if field.name in excluded:
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


@register.inclusion_tag("generic/_worktable_th.html", takes_context=True)
def worktable_th(context, label, column="", align="", css=""):
    """UX-07/UX-09: a column header, with whatever the view lets it do.

    `column` is **the column's name**, and it does two separate jobs:

    - identity, for hiding it (`UX-09`). The name travels to the browser as
      `data-col`, and `worktable.js` copies it onto every cell in the column, so
      hiding needs no change in any row partial.
    - the sort key, **only if the view listed it** in `sortable_columns`.

    Splitting the two is what lets a column be hideable without being sortable:
    "Entidad" in the alert list is a generic relation with nothing to order by,
    and it is still one of the columns somebody would want out of the way.

    The allow-list lives in the view and never in the template: `?sort=` lands in
    `order_by`, and an unvalidated one there is a way to order by -- and so probe
    -- a related table nobody meant to expose.

    Degrades to a plain `<th>` when the column is not sortable, rather than
    drawing a link that does nothing.
    """
    sort = context.get("worktable_sort") or {}
    columns = sort.get("columns") or {}
    if not column or column not in columns:
        return {"label": label, "align": align, "css": css, "column": column, "url": ""}
    state = sort.get("column") == column and sort.get("direction") or ""
    # Clicking the column you are already on flips it; a fresh column starts
    # ascending, which is what every table on the planet does.
    nxt = "desc" if state == "asc" else "asc"
    return {
        "label": label,
        "align": align,
        "css": css,
        "column": column,
        "state": state,
        "url": f"?{sort['base_query']}sort={column}&dir={nxt}",
    }
