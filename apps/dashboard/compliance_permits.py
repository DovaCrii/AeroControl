"""La tabla «Permisos por faena» de la sección «Cumplimiento» (LV-359, fase 4; v4 en LV-376, fase 1b).

Se mudó del panel (donde vivía desde `LV-206`) a esta sección. **El cálculo sigue siendo uno**:
`kpis.permit_status_by_cost_center(hoy, usuario)` para las filas y `kpis.permit_band` para el tramo
(30/60 días); aquí sólo se ordena, se presenta y se agrega el detalle. Nada se recalcula.

- Orden (`?sort=&dir=`): lista PERMITIDA en Python (`SORT_KEYS`); cualquier otra clave se ignora, no
  se rechaza. Sin orden pedido manda la urgencia (v4): sin permiso, por empezar, esperando, ≤30 días,
  ≤60 días, al día. El vacío (`days` sin fecha) va al final en los dos sentidos, como `LV-288`.
- Resumen y filtro (v4): `?state=` con lista PERMITIDA (`STATE_FILTERS`) y `?q=` (código o nombre, sólo
  en la página completa). **Las cifras del resumen son siempre las totales**, con filtro o sin él, y por
  omisión salen TODAS las faenas (LV-374): el filtro es una decisión de quien mira, nunca el valor inicial.
- Detalle de cada faena (el `<details>` de su celda): UNA consulta `values()` con los permisos vivos
  de todas las faenas visibles, así que el costo es constante (no una consulta por fila). De la misma
  consulta salen la fecha de solicitud (`created_at`) y el permiso a renovar (`pk`): 0 consultas nuevas.
- Permiso de lectura: `view_flightpermission` (lo decide `compliance_section.blocks_for`), y las dos
  consultas van acotadas por el tenant de quien mira. Los enlaces «Nuevo permiso» y «Renovar» sólo
  existen con `add_flightpermission` (y `geo.add_geoplan` para renovar, como `_renewal_guard`).
"""

from django.db.models import Exists, F, OuterRef
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlencode
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from apps.compliance.kpis import (
    PERMIT_BAND_CRITICAL,
    PERMIT_BAND_NOMINAL,
    PERMIT_BAND_WARNING,
    PERMIT_CRITICAL_DAYS,
    PERMIT_WARNING_DAYS,
    permit_band,
    permit_status_by_cost_center,
)
from apps.operations.models import FlightPermission

PERMIT_PERMISSION = "operations.view_flightpermission"
ADD_PERMISSION = "operations.add_flightpermission"
RENEW_EXTRA_PERMISSION = "geo.add_geoplan"
SITE_PERMISSION = "registry.view_costcenter"
DETAIL_LIMIT = 8  # permisos que se listan por faena; el resto se dice con un enlace
METER_MAX_DAYS = (
    90  # la barra de días cubre el mismo horizonte de 90 días de la sección
)
QUERY_MAX_LENGTH = 60

# Símbolo + texto además del color. Aquí rige la escala de PERMISOS (30/60 días), no la de
# documentos (7/15/30): la guía lo explica. `BAND_*` queda por compatibilidad con quien lee el tramo.
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

# LV-376 (G1): el estado de cada faena. Un permiso vigente que vence en 30 días o menos es ámbar: el ROJO
# queda para «no se puede volar» (sin permiso), como el semáforo de la guía INS-096 («Cómo funciona»).
KINDS = ("none", "not_started", "awaiting", "renew_now", "renew_soon", "ok")
KIND_URGENCY = {kind: rank for rank, kind in enumerate(KINDS)}
# LV-412: el chip de un permiso vigente sale del tramo de `permit_band` (el mismo dato que colorea la barra
# de días): tramo -> (símbolo, tono, suave). Tres colores, los del semáforo: rojo (sin permiso), ámbar y
# verde. Los dos tramos ámbar se distinguen por forma (▲ / ◆), palabra y peso (sólido / suave), nunca
# sólo por el color. El cian de «Renovar pronto» se retiró: no era un nivel del semáforo y competía con verde.
BAND_CHIP = {
    PERMIT_BAND_CRITICAL: ("▲", "warning", False),
    PERMIT_BAND_WARNING: ("◆", "warning", True),
    PERMIT_BAND_NOMINAL: ("●", "ok", False),
}
KIND_BAND = {
    "renew_now": PERMIT_BAND_CRITICAL,
    "renew_soon": PERMIT_BAND_WARNING,
    "ok": PERMIT_BAND_NOMINAL,
}
# kind -> (símbolo, tono de `.id-cx-state--*`, suave). La espera no es un nivel del semáforo: lleva su tono.
KIND_CHIP = {
    "none": ("✕", "none", False),
    "not_started": ("◐", "wait", False),
    "awaiting": ("◐", "wait", False),
    **{kind: BAND_CHIP[band] for kind, band in KIND_BAND.items()},
}


def chip_css(kind):
    """Las clases del chip de un estado: tono y, si corresponde, la variante suave."""
    _symbol, tone, soft = KIND_CHIP[kind]
    return f"id-cx-state id-cx-state--{tone}" + (" id-cx-state--soft" if soft else "")


def band_tone(days):
    """El tono de la barra de días: el mismo de `BAND_CHIP` para el tramo de `permit_band(days)`."""
    band = permit_band(days)
    return BAND_CHIP[band][1] if band else ""


# Trozos del resumen y valores permitidos de `?state=` -> los `kind` que cubre cada uno.
STATE_FILTERS = {
    "none": ("none",),
    "waiting": ("awaiting", "not_started"),
    "renew": ("renew_now", "renew_soon"),
    "ok": ("ok",),
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


def requested_state(params):
    """El trozo del resumen pedido en `?state=`, o "" si no está en la lista permitida."""
    state = params.get("state", "")
    return state if state in STATE_FILTERS else ""


def requested_query(params):
    """El texto de `?q=` limpio (espacios colapsados, largo acotado). Nunca llega a una consulta."""
    return " ".join(params.get("q", "").split())[:QUERY_MAX_LENGTH]


def _urgency(row):
    kind = kind_of(row)
    days = row.get("days_remaining")
    return (KIND_URGENCY[kind], 0 if days is None else days, row["cost_center"].code)


def ordered_rows(rows, column, direction):
    """Las filas en el orden pedido; sin orden pedido, el de urgencia (v4).

    Estable: el código desempata siempre. Los vacíos van al final en los dos sentidos.
    """
    rows = sorted(rows, key=lambda row: row["cost_center"].code)
    if not column:
        return sorted(rows, key=_urgency)
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
    # `renewed` es lo que `active_renewal` mira (un sucesor vivo, sea cual sea su estado), sin consulta nueva.
    queryset = queryset.annotate(
        renewed=Exists(
            FlightPermission.objects.filter(renews=OuterRef("pk"), is_active=True)
        )
    )
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
        "created_at",
        "renewed",
    ):
        grouped.setdefault(item["cost_center_id"], []).append(
            {
                "pk": item["pk"],
                "url": reverse("permission-detail", kwargs={"pk": item["pk"]}),
                "folio": item["permission_number"] or item["internal_folio"],
                "purpose": purposes.get(item["purpose"], item["purpose"]),
                "status": statuses.get(item["status"], item["status"]),
                "awaiting": item["status"] == FlightPermission.STATUS_REQUESTED,
                "valid_from": item["valid_from"],
                "valid_until": item["valid_until"],
                "created_at": item["created_at"],
                "renewed": item["renewed"],
                # Igual que `FlightPermission.can_be_renewed`: autorizado alguna vez y sin sucesor vivo.
                "can_renew": (
                    item["status"] in FlightPermission.RENEWABLE_STATUSES
                    and not item["renewed"]
                ),
            }
        )
    return grouped


def has_problem(row):
    """Una faena «con problema»: sin permiso vigente, uno por empezar o esperando, o con el primero a 60 días o menos.

    LV-367 la usaba para truncar la tabla; LV-374 lo retiró (salen TODAS las faenas) y queda para el
    orden de atención y para decidir si la sección sale abierta. La escala es la de PERMISOS (30/60 días, `permit_band`), la misma de los chips; nada se recalcula.
    """
    if _state(row) != "in_force":
        return True
    return permit_band(row["days_remaining"]) in (
        PERMIT_BAND_CRITICAL,
        PERMIT_BAND_WARNING,
    )


def kind_of(row):
    """El estado de la faena en palabras de acción (`KINDS`), con la escala de PERMISOS (30/60 días)."""
    state = _state(row)
    if state != "in_force":
        return state
    band = permit_band(row.get("days_remaining"))
    if band == PERMIT_BAND_CRITICAL:
        return "renew_now"
    if band == PERMIT_BAND_WARNING:
        return "renew_soon"
    return "ok"


def _dm(day):
    return day.strftime("%d-%m")


def kind_label(kind, row=None):
    """La palabra del chip: el ESTADO, no la acción (la acción vive en «Qué hay que hacer»).

    Los días salen de las constantes de `kpis` (los cortes de `permit_band`), no de un texto tecleado.
    Sin `row` (la leyenda y la guía), «empieza» se dice sin fecha.
    """
    if kind == "none":
        return _("No permit")
    if kind == "awaiting":
        return _("Waiting for the DGAC")
    if kind == "not_started":
        if row and row.get("next_start"):
            return _("Starts %(date)s") % {"date": _dm(row["next_start"])}
        return _("Starts later")
    if kind == "renew_now":
        return _("Expires in ≤%(n)s days") % {"n": PERMIT_CRITICAL_DAYS}
    if kind == "renew_soon":
        return _("Expires in %(a)s–%(b)s days") % {
            "a": PERMIT_CRITICAL_DAYS + 1,
            "b": PERMIT_WARNING_DAYS,
        }
    return _("Up to date")


def legend():
    """La leyenda al pie: un chip por estado posible (`KINDS`), dibujado igual que en las filas."""
    hints = {"ok": _("over %(n)s days") % {"n": PERMIT_WARNING_DAYS}}
    return [
        {
            "kind": kind,
            "symbol": KIND_CHIP[kind][0],
            "css": chip_css(kind),
            "label": kind_label(kind),
            "hint": hints.get(kind, ""),
        }
        for kind in KINDS
    ]


def legend_note():
    return _(
        "The bar shows the days left of the first permit to expire (0 to 90), with marks at %(a)s and "
        "%(b)s, in the color of its status; the word and the date carry the meaning."
    ) % {"a": PERMIT_CRITICAL_DAYS, "b": PERMIT_WARNING_DAYS}


def _in_text(days):
    if days is None:
        return ""
    if days <= 0:
        return _("today")
    return ngettext("in %(n)s day", "in %(n)s days", days) % {"n": days}


def _counts_text(row):
    """LV-412: «4 permisos vigentes · 1 en trámite ante la DGAC», sólo con lo que hay.

    La espera se separa en sus dos casos reales (en trámite ante la DGAC / aprobado que aún no empieza);
    sin nada vivo, «Sin permiso vigente».
    """
    parts = []
    in_force, awaiting, later = row["in_force"], row["awaiting"], row["not_started"]
    if in_force:
        parts.append(
            ngettext("%(n)s permit in force", "%(n)s permits in force", in_force)
            % {"n": in_force}
        )
    if awaiting:
        parts.append(
            ngettext(
                "%(n)s in progress with the DGAC",
                "%(n)s in progress with the DGAC",
                awaiting,
            )
            % {"n": awaiting}
        )
    if later:
        parts.append(
            ngettext(
                "%(n)s approved, not started yet",
                "%(n)s approved, not started yet",
                later,
            )
            % {"n": later}
        )
    return " · ".join(parts) or _("No permit in force")


def _expiring_permit(row, listed, today):
    """El primer permiso aprobado y vigente cuya fecha final es el próximo vencimiento, o `None`."""
    for permit in listed:
        if (
            not permit["awaiting"]
            and permit["valid_until"] == row["next_expiry"]
            and permit["valid_from"]
            and permit["valid_from"] <= today
        ):
            return permit
    return None


def _renewal_pk(row, listed, today):
    """El permiso a renovar: el que vence primero, sólo si `can_be_renewed` (sin renovación en curso)."""
    permit = _expiring_permit(row, listed, today)
    return permit["pk"] if permit and permit["can_renew"] else None


def _awaiting_since(listed):
    """La fecha en que se registró el permiso solicitado más antiguo (`created_at`), o `None`."""
    stamps = [p["created_at"] for p in listed if p["awaiting"] and p["created_at"]]
    return timezone.localtime(min(stamps)).date() if stamps else None


def _action(kind, row, listed, today, flags):
    """La frase de «Qué hay que hacer» y su enlace, que existe sólo si la persona puede usarlo."""
    create = reverse("permission-create")
    site = urlencode({"cost_center": row["cost_center"].pk})
    days = row["days_remaining"]
    url = ""
    if kind == "none":
        text = _("Request a permit")
        if flags["can_add"]:
            url = f"{create}?{site}"
    elif kind == "awaiting":
        # LV-412: el chip ya dice «Esperando a la DGAC»; aquí va la acción y desde cuándo.
        since = _awaiting_since(listed)
        text = (
            _("Requested on %(date)s: follow up with the DGAC") % {"date": _dm(since)}
            if since
            else _("Follow up with the DGAC")
        )
    elif kind == "not_started":
        # El chip dice «Empieza dd-mm»; repetir la fecha no decía nada nuevo.
        text = _("Nothing to do until that date")
    elif kind == "renew_now":
        expiring = _expiring_permit(row, listed, today)
        if expiring and expiring["renewed"]:
            # Ya hay una renovación en curso: decir «renovar ahora» sería falso y el enlace
            # terminaría en «ya fue renovado».
            if days is not None and days <= 0:
                text = _("Expires today: the renewal is already requested")
            else:
                text = ngettext(
                    "Expires in %(n)s day: the renewal is already requested",
                    "Expires in %(n)s days: the renewal is already requested",
                    days or 0,
                ) % {"n": days}
        elif days is not None and days <= 0:
            text = _("Expires today: renew now")
        else:
            text = ngettext(
                "Expires in %(n)s day: renew now",
                "Expires in %(n)s days: renew now",
                days or 0,
            ) % {"n": days}
        pk = _renewal_pk(row, listed, today)
        if flags["can_renew"] and pk:
            url = f"{create}?{urlencode({'renueva': pk})}"
    elif kind == "renew_soon":
        text = ngettext(
            "Expires in %(n)s day: prepare the renewal",
            "Expires in %(n)s days: prepare the renewal",
            days,
        ) % {"n": days}
    else:
        # LV-412: el chip ya dice «Al día»; repetirlo aquí no decía qué hacer.
        text = _("Nothing to do")
    return {"text": text, "url": url}


def _past_text(past):
    if not past:
        return ""
    return ngettext(
        "%(n)s permit with a validity that has passed and is still open: review",
        "%(n)s permits with a validity that has passed and is still open: review",
        past,
    ) % {"n": past}


def _tally_label(key):
    return {
        "none": _("without a permit"),
        "waiting": _("waiting"),
        "renew": _("to renew"),
        "ok": _("Up to date"),
    }[key]


TALLY_SYMBOL = {"none": "✕", "waiting": "◐", "renew": "▲", "ok": "●"}
TALLY_TONE = {"none": "none", "waiting": "wait", "renew": "warning", "ok": "ok"}


def _link_params(cost_center, column, direction, **extra):
    """Los parámetros que se conservan al cambiar de filtro, todos de lista permitida o ya validados."""
    params = {}
    if cost_center:
        params["cost_center"] = cost_center.pk
    if column:
        params["sort"] = column
        params["dir"] = direction
    params.update({key: value for key, value in extra.items() if value})
    return params


def section_url(params):
    query = urlencode(params)
    return f"{reverse('dashboard-compliance')}{'?' + query if query else ''}#cx-permits"


def permit_table(
    user,
    cost_center,
    today,
    tenant_ids,
    column="",
    direction="",
    state="",
    query="",
):
    """La tabla lista para dibujar, o `None` sin `view_flightpermission`.

    `rows` ya viene ordenada y filtrada por `state`/`query`; cada fila lleva su estado (`kind` y chip),
    «qué hay que hacer», el próximo vencimiento y su detalle. `total`, `problems`, `without_permit` y
    `tally` son SIEMPRE los de todas las faenas visibles (con una faena elegida, sólo esa): filtrar no
    mueve ninguna cifra.
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
    kinds = {id(row): kind_of(row) for row in rows}
    counts = {
        key: sum(1 for row in rows if kinds[id(row)] in covered)
        for key, covered in STATE_FILTERS.items()
    }
    shown = rows
    if state:
        shown = [row for row in shown if kinds[id(row)] in STATE_FILTERS[state]]
    if query:
        needle = query.casefold()
        shown = [
            row
            for row in shown
            if needle in row["cost_center"].code.casefold()
            or needle in row["cost_center"].name.casefold()
        ]
    flags = {
        "can_add": user.has_perm(ADD_PERMISSION),
        "can_view_site": user.has_perm(SITE_PERMISSION),
    }
    flags["can_renew"] = flags["can_add"] and user.has_perm(RENEW_EXTRA_PERMISSION)
    details = _details(tenant_ids, shown)
    create = reverse("permission-create")
    items = []
    for row in shown:
        days = row["days_remaining"]
        band = permit_band(days)
        kind = kinds[id(row)]
        listed = details.get(row["cost_center"].pk, [])
        past = _past(row)
        symbol, tone, _soft = KIND_CHIP[kind]
        site_query = urlencode({"cost_center": row["cost_center"].pk})
        items.append(
            {
                **row,
                "past": past,
                "band": band,
                "band_symbol": BAND_SYMBOL.get(band, ""),
                "band_tone": BAND_TONE.get(band, ""),
                "band_label": _band_label(band),
                "kind": kind,
                "chip": {
                    "symbol": symbol,
                    "tone": tone,
                    "css": chip_css(kind),
                    "label": kind_label(kind, row),
                },
                "action": _action(kind, row, listed, today, flags),
                "past_text": _past_text(past),
                "counts_text": _counts_text(row),
                "in_text": _in_text(days),
                # La barra de días (0 a 90) es sólo una ayuda visual: la fecha y las palabras llevan el
                # significado.
                "days_bar": days,
                "state": _state(row),
                "problem": has_problem(row),
                "row_class": _row_class(row),
                "permits": listed[:DETAIL_LIMIT],
                "more": max(0, len(listed) - DETAIL_LIMIT),
                "url": f"{reverse('permission-list')}?{site_query}",
                "site_url": (
                    reverse("costcenter-detail", kwargs={"pk": row["cost_center"].pk})
                    if flags["can_view_site"]
                    else ""
                ),
                "new_url": f"{create}?{site_query}" if flags["can_add"] else "",
            }
        )
    tally = [
        {
            "key": key,
            "n": counts[key],
            "label": _tally_label(key),
            "symbol": TALLY_SYMBOL[key],
            "tone": TALLY_TONE[key],
            "active": state == key,
            "url": section_url(_link_params(cost_center, column, direction, state=key)),
        }
        for key in STATE_FILTERS
        if counts[key]
    ]
    filtered = bool(state or query)
    return {
        "rows": items,
        "total": total,
        "shown": len(items),
        "problems": problems,
        "without_permit": without_permit,
        "no_permit": counts["none"],
        "column": column,
        "direction": direction,
        "state": state,
        "query": query,
        "filtered": filtered,
        "tally": tally,
        "legend": legend(),
        "legend_note": legend_note(),
        "tally_total": ngettext("%(count)s site:", "%(count)s sites:", total)
        % {"count": total},
        "showing": _("Showing %(shown)s of %(total)s")
        % {"shown": len(items), "total": total},
        "show_all_url": section_url(_link_params(cost_center, column, direction)),
        "hidden_params": list(
            _link_params(cost_center, column, direction, state=state).items()
        ),
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
    a la DGAC o aprobado que aún no empieza (existe y habilita desde su fecha). Desde LV-376 la clase se
    conserva pero dentro de `.id-cx-permits` se dibuja como filete de 4 px, no como tinte entero."""
    if row["in_force"]:
        return ""
    return "row-awaiting" if row["awaiting"] or row["not_started"] else "row-critical"


def sort_context(request, cost_center, columns=tuple(SORT_KEYS), state="", query=""):
    """El contexto que `{% worktable_th %}` lee, con la ruta y el ancla propias del fragmento.

    Sin `url_prefix` el enlace sería un `?sort=` suelto y, dentro del panel, resolvería contra el
    panel; con él lleva a la página completa de la sección y vuelve a la tabla. El filtro vigente
    (`state`, `q`) viaja en los enlaces de orden para no perderse al ordenar.
    """
    column, direction = requested_sort(request.GET)
    params = {}
    if cost_center:
        params["cost_center"] = cost_center.pk
    if state:
        params["state"] = state
    if query:
        params["q"] = query
    base = urlencode(params)
    return {
        "columns": {key: key for key in columns},
        "column": column,
        "direction": direction,
        "base_query": f"{base}&" if base else "",
        "url_prefix": reverse("dashboard-compliance"),
        "url_suffix": "#cx-permits",
    }
