"""LV-260: la hoja ejecutiva del informe, armada **sólo** desde el payload.

Pedido del usuario el 2026-09-25: el informe *"aún no convence, no está bien
diseñado"*, y al preguntarle qué fallaba eligió **«demasiado largo»** y la
dirección **«hoja ejecutiva + detalle»**. La hoja de resumen abría con dos
párrafos que eran los mismos todos los meses y siete indicadores con el mismo
peso: la conclusión la tenía que armar quien leía.

Esto la arma: qué faenas no pueden volar, qué permiso vence primero, qué espera
a la DGAC. **Todo sale del payload y nada de la base**, por la regla que
sostiene al documento entero: un informe congelado tiene que decir lo mismo el
día que se reabra, y leer la base al dibujar haría que agosto, reimpreso en
diciembre, cambiara de conclusión.

Devuelve datos y no frases: las palabras las pone la plantilla, en español y
sin `{% translate %}`, igual que el resto del documento (es el papel que se
firma, no interfaz).
"""

#: Cuántos permisos lista «Lo próximo que vence». Cinco alcanzan para que se vea
#: el primero en caer y lo que viene detrás sin convertir el resumen en la tabla
#: de la hoja siguiente, que es donde está el detalle completo.
NEXT_TO_EXPIRE = 5

#: El largo de la barra de días se satura acá: 60 días es el horizonte del
#: indicador «vencen en 60 días», así que una barra llena dice «fuera del
#: horizonte» y una corta, «ya». Más allá no aporta.
HORIZON_DAYS = 60


def _value(payload, key):
    """El valor de una hoja de `kpis`, o `None` si el payload no la trae."""
    leaf = (payload.get("kpis") or {}).get(key) or {}
    return leaf.get("value")


def _tone_for_expiring(within_30, within_60):
    if within_30:
        return "critical"
    if within_60:
        return "warning"
    return "good"


def executive_summary(payload):
    """Lo que la hoja ejecutiva dibuja, calculado una sola vez.

    - `without_permit`: las faenas que no pueden volar, con su código. Es la
      primera línea de la conclusión porque es lo único del informe que significa
      *no se puede operar*.
    - `next_to_expire`: los primeros permisos vigentes en caer, con el ancho de
      su barra ya calculado (la plantilla no hace aritmética).
    - `kpis`: los cuatro indicadores de la hoja, cada uno con su **tono según el
      valor**. Antes el color iba fijo por tarjeta, y en agosto «0 permisos
      vigentes» salía en verde.
    """
    centres = payload.get("cost_centres") or []
    without = [row["code"] for row in centres if not row.get("permits_in_force")]
    total = len(centres)

    permits = payload.get("permits") or []
    in_force = sorted(
        (row for row in permits if row.get("in_force")),
        key=lambda row: (row.get("days_remaining") is None, row.get("days_remaining")),
    )
    next_to_expire = [
        {
            "folio": row.get("folio"),
            "cost_centre": row.get("cost_centre"),
            "valid_until": row.get("valid_until"),
            "days_remaining": row.get("days_remaining"),
            "band": row.get("band"),
            "bar_pct": _bar_pct(row.get("days_remaining")),
        }
        for row in in_force[:NEXT_TO_EXPIRE]
    ]

    permits_in_force = _value(payload, "permits_in_force")
    within_30 = _value(payload, "permits_expiring_30d") or 0
    within_60 = _value(payload, "permits_expiring_60d") or 0
    awaiting = _value(payload, "permits_awaiting") or 0

    return {
        "cost_centres_total": total,
        "without_permit": without,
        "enabled": total - len(without),
        "next_to_expire": next_to_expire,
        "first_to_expire": next_to_expire[0] if next_to_expire else None,
        "in_force_total": len(in_force),
        "more_to_expire": max(len(in_force) - NEXT_TO_EXPIRE, 0),
        "awaiting": awaiting,
        "lapsed": _value(payload, "permits_lapsed") or 0,
        "incidents": _value(payload, "incidents") or 0,
        "incidents_open": _value(payload, "incidents_open") or 0,
        "kpis": {
            "enabled": "critical" if without else "good",
            "in_force": "critical" if not permits_in_force else "neutral",
            "expiring": _tone_for_expiring(within_30, within_60),
            "awaiting": "info" if awaiting else "neutral",
        },
        "within_30": within_30,
        "within_60": within_60,
    }


def _bar_pct(days):
    """El ancho de la barra, de 4 a 100. Nunca cero: una barra vacía se lee como
    «no hay dato», y un permiso que vence hoy sí lo tiene."""
    if days is None:
        return 100
    return max(4, min(100, round(100 * max(days, 0) / HORIZON_DAYS)))


# == LV-378 · La hoja ejecutiva del diseño 2 ===================================
#
# Lo que cambia contra `executive_summary` (que sigue dibujando los informes ya
# emitidos): **lo que mide renovación cuenta sólo las faenas con operación** y el
# resto se dice aparte. Un permiso vigente de una faena terminada es un hecho legal
# —SIGO lo tiene, y la hoja dice «15 vigentes»—, pero no se renueva, así que no pinta de
# rojo «vencen en 60 días» ni es «el primero en vencer».
#
# Todo sale del payload, como el resto de este módulo.

#: Cuántas faenas lista «Lo próximo que vence». Una fila por **faena**, no por
#: permiso: siete permisos de la misma fecha son una fila, y con una por permiso el
#: resumen repetía cuatro veces la misma fecha.
NEXT_CENTRES = 6


def _rows_in_force(payload):
    return [row for row in (payload.get("permits") or []) if row.get("in_force")]


def executive_summary_v2(payload):
    """La hoja ejecutiva del diseño 2, calculada una sola vez desde el payload."""
    from .groups import permit_groups

    groups = permit_groups(payload)
    centres = payload.get("cost_centres") or []
    without = [row["code"] for row in centres if not row.get("permits_in_force")]
    total = _value(payload, "cost_centres_with_operation")
    if total is None:
        total = len(centres)

    in_operation = [row for row in _rows_in_force(payload) if row.get("in_operation")]
    first = min(
        in_operation,
        key=lambda row: (row["days_remaining"], row["folio"]),
        default=None,
    )
    within_30 = _value(payload, "permits_expiring_30d_operating") or 0
    within_60 = _value(payload, "permits_expiring_60d_operating") or 0
    awaiting = _value(payload, "permits_awaiting") or 0

    next_rows = []
    for group in groups["operating"][:NEXT_CENTRES]:
        first_line = min(group["lines"], key=lambda line: line["days"])
        others = [line for line in group["lines"] if line is not first_line]
        next_rows.append(
            {
                "code": group["code"],
                "count": group["count"],
                "valid_until": group["next_expiry"],
                "days": group["days"],
                "band": group["band"],
                "bar_pct": _bar_pct(group["days"]),
                # «(+1 hasta 13-01)»: los permisos de la faena que vencen después.
                "later_count": sum(line["count"] for line in others),
                "later_until": max(
                    (line["valid_until"] for line in others), default=None
                ),
            }
        )

    outside = [
        {
            "code": group["code"],
            "reason": group.get("reason"),
            "count": group["count"],
            "folios": group["folios"],
            "valid_until": group["next_expiry"],
        }
        for group in groups["outside"]
    ]
    return {
        "cost_centres_total": total,
        "without_permit": without,
        "enabled": total - len(without),
        "in_force_total": _value(payload, "permits_in_force") or 0,
        "in_force_operating": _value(payload, "permits_in_force_operating") or 0,
        "in_force_outside": _value(payload, "permits_in_force_outside") or 0,
        "first_to_expire": first,
        "within_30": within_30,
        "within_60": within_60,
        "awaiting": awaiting,
        "lapsed": _value(payload, "permits_lapsed") or 0,
        "incidents": _value(payload, "incidents") or 0,
        "incidents_open": _value(payload, "incidents_open") or 0,
        "next_centres": next_rows,
        "more_centres": max(len(groups["operating"]) - NEXT_CENTRES, 0),
        "outside": outside,
        "kpis": {
            "enabled": "critical" if without else "good",
            "in_force": (
                "critical"
                if not (_value(payload, "permits_in_force") or 0)
                else "neutral"
            ),
            "expiring": _tone_for_expiring(within_30, within_60),
            "awaiting": "info" if awaiting else "neutral",
        },
        "changes": changes_view(payload),
    }


def changes_view(payload):
    """«Cambios desde el informe anterior», desde `payload.changes` (congelado).

    `None` cuando el informe no trae comparación (no había informe del mes anterior):
    «sin cambios» y «no hay contra qué comparar» son afirmaciones distintas.
    """
    raw = payload.get("changes")
    if not raw:
        return None
    entered = raw["in_force"]["added"]
    left = raw["in_force"]["removed"]
    waiting_in = raw["awaiting"]["added"]
    waiting_out = raw["awaiting"]["removed"]
    without_in = raw["without_permit"]["added"]
    without_out = raw["without_permit"]["removed"]
    kpis = raw.get("kpis") or {}
    return {
        "against": raw["against"],
        "entered": entered,
        "left": left,
        "awaiting_in": waiting_in,
        "awaiting_out": waiting_out,
        "without_in": without_in,
        "without_out": without_out,
        "in_force": kpis.get("permits_in_force"),
        "awaiting": kpis.get("permits_awaiting"),
        "unchanged": not any(
            (entered, left, waiting_in, waiting_out, without_in, without_out)
        ),
    }
