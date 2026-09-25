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
