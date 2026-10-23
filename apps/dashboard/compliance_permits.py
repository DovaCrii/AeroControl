"""La tabla «Permisos por faena» de la sección «Cumplimiento» (LV-359, fase 4).

Se mudó del panel (donde vivía desde `LV-206`) a esta sección. **El cálculo sigue siendo uno**:
`kpis.permit_status_by_cost_center(hoy, usuario)` para las filas y `kpis.permit_band` para el tramo
(30/60 días); aquí sólo se ordena, se presenta y se agrega el detalle. Nada se recalcula.

- Orden (`?sort=&dir=`): lista PERMITIDA en Python (`SORT_KEYS`); cualquier otra clave se ignora, no
  se rechaza. Sin orden pedido manda el de `LV-246`: primero las faenas sin permiso vigente, después
  por código. El vacío (`days` sin fecha) va al final en los dos sentidos, como `LV-288`.
- Detalle de cada faena (el `<details>` de su celda): UNA consulta `values()` con los permisos vivos
  de todas las faenas visibles, así que el costo es constante (no una consulta por fila).
- Permiso de lectura: `view_flightpermission` (lo decide `compliance_section.blocks_for`), y las dos
  consultas van acotadas por el tenant de quien mira.
"""

from django.db.models import F
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from apps.compliance.kpis import (
    PERMIT_BAND_CRITICAL,
    PERMIT_BAND_NOMINAL,
    PERMIT_BAND_WARNING,
    permit_band,
    permit_status_by_cost_center,
)
from apps.operations.models import FlightPermission

PERMIT_PERMISSION = "operations.view_flightpermission"
DETAIL_LIMIT = 8  # permisos que se listan por faena; el resto se dice con un enlace
METER_MAX_DAYS = 90  # el medidor cubre el mismo horizonte de 90 días de la sección

# Símbolo + texto además del color. Aquí rige la escala de PERMISOS (30/60 días), no la de
# documentos (7/15/30): la guía lo explica. Tono = variante de `.id-chip--*`.
BAND_SYMBOL = {
    PERMIT_BAND_CRITICAL: "✕",
    PERMIT_BAND_WARNING: "▲",
    PERMIT_BAND_NOMINAL: "●",
}
BAND_TONE = {
    PERMIT_BAND_CRITICAL: "critical",
    PERMIT_BAND_WARNING: "warning",
    PERMIT_BAND_NOMINAL: "ok",
}


def _past(row):
    """Vigencia pasada: los aprobados que nadie cerró más los caducados del mes (`LV-241`)."""
    return row["lapsed"] + row["expired_this_month"]


# Orden de «estado» para la columna Estado: primero lo que hay que atender (sin permiso, luego el que
# aún no empieza, luego el que espera a la DGAC, al final el vigente).
STATE_RANK = {"none": 0, "not_started": 1, "awaiting": 2, "in_force": 3}

# Clave que viaja en `?sort=` -> valor por el que se ordena. Es la lista permitida: no se pasa
# nada del URL a ninguna consulta ni a `getattr`.
SORT_KEYS = {
    "code": lambda row: row["cost_center"].code,
    "status": lambda row: STATE_RANK[_state(row)],
    "days": lambda row: row["days_remaining"],
    "in_force": lambda row: row["in_force"],
    "soon": lambda row: row["soon"],
    "awaiting": lambda row: row["awaiting"],
    "past": _past,
}


def requested_sort(params):
    """(columna, sentido) pedidos, o ("", "") si la clave no está en la lista permitida."""
    column = params.get("sort", "")
    if column not in SORT_KEYS:
        return "", ""
    return column, "desc" if params.get("dir") == "desc" else "asc"


def ordered_rows(rows, column, direction):
    """Las filas en el orden pedido; sin orden pedido, el de `LV-246`.

    Estable: el código desempata siempre. Los vacíos van al final en los dos sentidos.
    """
    rows = sorted(rows, key=lambda row: row["cost_center"].code)
    if not column:
        return sorted(rows, key=lambda row: bool(row["in_force"]))
    key = SORT_KEYS[column]
    filled = [row for row in rows if key(row) is not None]
    empty = [row for row in rows if key(row) is None]
    filled.sort(key=key, reverse=direction == "desc")
    return filled + empty


def _details(tenant_ids, rows):
    """Los permisos vivos de las faenas de `rows` en UNA consulta, agrupados por faena.

    `tenant_ids` (`visible_tenant_ids(user)`, `None` = todos) ya viene resuelto por quien arma la
    sección: acotar con `scope_queryset_to_tenant` repetiría su consulta de membresía.
    """
    ids = [row["cost_center"].pk for row in rows]
    if not ids:
        return {}
    queryset = FlightPermission.objects.filter(
        is_active=True,
        cost_center__in=ids,
        status__in=(
            FlightPermission.STATUS_REQUESTED,
            FlightPermission.STATUS_APPROVED,
        ),
    )
    if tenant_ids is not None:
        queryset = queryset.filter(cost_center__tenant_id__in=tenant_ids)
    purposes = dict(FlightPermission._meta.get_field("purpose").flatchoices)
    statuses = dict(FlightPermission.STATUS_CHOICES)
    grouped = {}
    values = queryset.order_by(F("valid_until").asc(nulls_last=True), "internal_folio")
    for item in values.values(
        "pk",
        "cost_center_id",
        "internal_folio",
        "permission_number",
        "purpose",
        "status",
        "valid_from",
        "valid_until",
    ):
        grouped.setdefault(item["cost_center_id"], []).append(
            {
                "url": reverse("permission-detail", kwargs={"pk": item["pk"]}),
                "folio": item["permission_number"] or item["internal_folio"],
                "purpose": purposes.get(item["purpose"], item["purpose"]),
                "status": statuses.get(item["status"], item["status"]),
                "awaiting": item["status"] == FlightPermission.STATUS_REQUESTED,
                "valid_from": item["valid_from"],
                "valid_until": item["valid_until"],
            }
        )
    return grouped


def requested_all(params):
    """¿Se pidió ver TODAS las faenas (`?all=1`)? Por omisión sólo las que tienen un problema."""
    return params.get("all") == "1"


def has_problem(row):
    """Una faena «con problema»: sin permiso vigente, uno por empezar o esperando, o con el primero a 60 días o menos.

    LV-367: la tabla simple muestra sólo estas por omisión; el resto se ve con «Ver todas». La escala es la
    de PERMISOS (30/60 días, `permit_band`), la misma de los chips; nada se recalcula.
    """
    if _state(row) != "in_force":
        return True
    return permit_band(row["days_remaining"]) in (
        PERMIT_BAND_CRITICAL,
        PERMIT_BAND_WARNING,
    )


def permit_table(
    user, cost_center, today, tenant_ids, column="", direction="", show_all=False
):
    """La tabla lista para dibujar, o `None` sin `view_flightpermission`.

    `rows` ya viene ordenada; cada fila lleva su tramo (`band`, símbolo y tono), el valor del
    medidor, el texto de días y su detalle. Con una faena elegida sólo queda esa fila.
    """
    if not user.has_perm(PERMIT_PERMISSION):
        return None
    rows = permit_status_by_cost_center(today, user)
    if cost_center:
        rows = [row for row in rows if row["cost_center"].pk == cost_center.pk]
    rows = ordered_rows(rows, column, direction)
    total = len(rows)
    without_permit = sum(1 for row in rows if not row["in_force"])
    problems = sum(1 for row in rows if has_problem(row))
    if not show_all:
        rows = [row for row in rows if has_problem(row)]
    details = _details(tenant_ids, rows)
    items = []
    for row in rows:
        days = row["days_remaining"]
        band = permit_band(days)
        listed = details.get(row["cost_center"].pk, [])
        past = _past(row)
        items.append(
            {
                **row,
                "past": past,
                "band": band,
                "band_symbol": BAND_SYMBOL.get(band, ""),
                "band_tone": BAND_TONE.get(band, ""),
                "band_label": _band_label(band),
                "meter": None if days is None else min(max(days, 0), METER_MAX_DAYS),
                "days_text": None if days is None else _("%(n)s d") % {"n": days},
                # Estado de la celda «Vigentes»: con permiso vigente, la cifra; sin él, qué hay.
                "state": _state(row),
                "problem": has_problem(row),
                "row_class": _row_class(row),
                "permits": listed[:DETAIL_LIMIT],
                "more": max(0, len(listed) - DETAIL_LIMIT),
                "url": f"{reverse('permission-list')}?cost_center={row['cost_center'].pk}",
            }
        )
    return {
        "rows": items,
        "total": total,
        "problems": problems,
        "hidden": total - len(items),
        "show_all": show_all,
        "without_permit": without_permit,
        "column": column,
        "direction": direction,
        "title": ngettext(
            "%(count)s site, of which %(without)s without a permit in force",
            "%(count)s sites, of which %(without)s without a permit in force",
            total,
        )
        % {"count": total, "without": without_permit},
    }


def _band_label(band):
    return {
        PERMIT_BAND_CRITICAL: _("≤30 days"),
        PERMIT_BAND_WARNING: _("≤60 days"),
        PERMIT_BAND_NOMINAL: _("Over 60 days"),
    }.get(band, "")


def _state(row):
    if row["in_force"]:
        return "in_force"
    if row["awaiting"]:
        return "awaiting"
    if row["not_started"]:
        return "not_started"
    return "none"


def _row_class(row):
    """`LV-246`/`LV-284`/`LV-296`: sin permiso vigente la fila es roja; ámbar si hay uno esperando
    a la DGAC o aprobado que aún no empieza (existe y habilita desde su fecha)."""
    if row["in_force"]:
        return ""
    return "row-awaiting" if row["awaiting"] or row["not_started"] else "row-critical"


def sort_context(request, cost_center, columns=tuple(SORT_KEYS)):
    """El contexto que `{% worktable_th %}` lee, con la ruta y el ancla propias del fragmento.

    Sin `url_prefix` el enlace sería un `?sort=` suelto y, dentro del panel, resolvería contra el
    panel; con él lleva a la página completa de la sección y vuelve a la tabla.
    """
    column, direction = requested_sort(request.GET)
    query = f"cost_center={cost_center.pk}&" if cost_center else ""
    if requested_all(request.GET):
        query += "all=1&"
    return {
        "columns": {key: key for key in columns},
        "column": column,
        "direction": direction,
        "base_query": query,
        "url_prefix": reverse("dashboard-compliance"),
        "url_suffix": "#cx-permits",
    }
