import re

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


@register.filter
def as_datetime(value):
    """Una marca ISO como `datetime`, para poder darle formato.

    `UX-16`: el pronóstico guarda su hora de consulta en ISO porque viaja por la
    caché y por el payload de una revisión meteorológica, y la plantilla la
    dibuja en `Y-m-d H:i`. Sin esta conversión saldría el ISO crudo con su `T` y
    su zona, que en una tarjeta de una línea se lee como ruido.

    Vive acá y no en `report_leaf` —donde está su gemelo `as_date`— porque el
    clima no es parte del informe: ese módulo carga sólo en las cinco hojas.

    Devuelve el valor tal cual si no es una marca reconocible, en vez de
    reventar: quien llama está dibujando una tarjeta de contexto, y un
    pronóstico raro no puede tumbar la ficha del plan.
    """
    from datetime import datetime

    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return value


# LV-303: la ilustración de una aeronave según su serie.
#
# Pedido del usuario (2026-10-13): que los drones se vean bien, no como siluetas simples. Hay un
# dibujo propio por serie en `static/img/aircraft/` y, **si la persona deja una foto con derecho
# de uso** en `static/img/equipment/<serie>.(webp|jpg|jpeg|png)`, esa foto manda. Nada de fotos
# de terceros va en el repositorio: ver `static/img/illustrations/README.md`.
AIRCRAFT_ART_SERIES = ("mavic", "matrice", "phantom", "elios")
AIRCRAFT_PHOTO_EXTENSIONS = ("webp", "jpg", "jpeg", "png")


# Abreviaturas que el fabricante usa en el modelo y que no empiezan por el nombre de la serie
# («M3» es Mavic 3; «M300 RTK» es Matrice 300). Sólo las **inequívocas**: «M4» se deja fuera a
# propósito porque hay un Matrice 4 y un Mavic 4, y adivinar mostraría el dibujo equivocado.
# Esto vale **sólo para elegir el dibujo**; la comprobación de habilitaciones sigue usando
# `aircraft_series` tal cual, porque ahí un falso «cumple» es un riesgo y acá sólo un dibujo.
_SERIES_ABBREVIATIONS = (
    (re.compile(r"^m(2|3)(e|ea|t|m|p|c)?$"), "mavic"),
    (re.compile(r"^m(30|100|200|210|300|350|600)(t|e|rtk)?$"), "matrice"),
)


def _abbreviated_series(aircraft):
    words = re.split(r"[\s_-]+", (getattr(aircraft, "model", "") or "").strip().lower())
    first = words[0] if words else ""
    for pattern, series in _SERIES_ABBREVIATIONS:
        if pattern.match(first):
            return series
    return ""


@register.simple_tag
def aircraft_art(aircraft):
    """`{"url", "photo", "series"}` para dibujar la aeronave en su ficha.

    La serie sale de `aircraft_series` (la primera palabra del modelo), la misma definición
    que usa la comprobación de habilitaciones: una sola idea de «qué serie es». Una serie sin
    dibujo cae en el genérico, vista desde arriba, y **nunca** en el de otra serie: mostrar un
    Mavic para un equipo que no lo es sería informar mal.
    """
    from django.contrib.staticfiles import finders
    from django.contrib.staticfiles.storage import staticfiles_storage

    from apps.registry.selectors import aircraft_series

    series = aircraft_series(aircraft)
    if series not in AIRCRAFT_ART_SERIES:
        series = _abbreviated_series(aircraft)
    key = series if series in AIRCRAFT_ART_SERIES else "generic"
    for extension in AIRCRAFT_PHOTO_EXTENSIONS:
        path = f"img/equipment/{key}.{extension}"
        if finders.find(path) or staticfiles_storage.exists(path):
            try:
                return {
                    "url": staticfiles_storage.url(path),
                    "photo": True,
                    "series": key,
                }
            except ValueError:
                # Con estáticos de contenido con hash, una foto recién dejada y sin
                # `collectstatic` no tiene URL: se cae al dibujo en vez de romper la ficha.
                break
    return {
        "url": staticfiles_storage.url(f"img/aircraft/{key}.svg"),
        "photo": False,
        "series": key,
    }
