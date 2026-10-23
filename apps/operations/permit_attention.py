"""LV-368 fase 1: lo que la ficha del permiso pone arriba (y lo que deja plegado).

La ficha llegó a ser una sola tabla con todo a la misma altura: el folio, el aviso
del seguro, el expediente y el historial pesaban igual, y lo que **pide una
acción** no se distinguía de lo que sólo informa. Este módulo arma, **en Python y
con lo que la vista ya calculó** (`suggested_folio`, `insurance_limit`,
`dossier`, `has_lapsed`), tres cosas:

- `attention_items`: la franja «Qué falta», de **tres ítems como máximo**;
- `open_sections`: qué secciones `<details>` se dibujan abiertas;
- `validity_line`: la geometría de la línea de tiempo de la vigencia (SVG de
  servidor: los números van en atributos, nunca en `style=""`).

Nada de esto consulta la base: si una regla necesita un dato nuevo, se calcula en
la vista y se pasa. Y ninguna regla de negocio vive en la plantilla.
"""

from datetime import date

from django.utils import timezone
from django.utils.translation import gettext as _

from .models import FlightPermission

# Gravedad -> (símbolo, clase de tono). Símbolo + palabra + color, nunca sólo
# color (sistema visual v3). ⚠ crítico sólo para lo vencido o lo que excede el
# seguro; ▲ falta algo; ◆ un límite que todavía no se excede.
CRITICAL, WARNING, CAUTION = "critical", "warning", "caution"
SYMBOLS = {CRITICAL: "⚠", WARNING: "▲", CAUTION: "◆"}

# El orden de la franja, **en un solo lugar**: la persona decidió «vencido >
# seguro > folio > expediente» (decisión 3.2 del diseño). Para cambiarlo basta
# reordenar esta tupla. La ubicación sin región va al final: es un dato a
# completar, no un bloqueo.
ATTENTION_ORDER = ("lapsed", "insurance", "folio", "dossier", "region")
MAX_ATTENTION_ITEMS = 3

# Cuántos días antes del fin la sección de vigencia se abre sola (decisión 3.1).
VALIDITY_OPEN_DAYS = 30


def _item(kind, tone, text):
    return {"kind": kind, "tone": tone, "symbol": SYMBOLS[tone], "text": text}


def attention_items(
    permission, *, suggested_folio, insurance_limit, dossier, derived_location
):
    """La franja «Qué falta»: lista de ítems ordenados, de 0 a 3.

    Lista vacía significa «nada pendiente» (la plantilla dice ✓ Nada pendiente).
    Un permiso rechazado o cerrado no pide folio, región ni expediente: ya no hay
    nada que tramitar (el expediente sigue a la vista en su sección), y un aviso que
    no pide una acción es ruido.
    """
    open_for_work = permission.status in (
        FlightPermission.STATUS_REQUESTED,
        FlightPermission.STATUS_APPROVED,
    )
    found = {}
    if permission.has_lapsed:
        found["lapsed"] = _item("lapsed", CRITICAL, _("The validity window has ended."))
    if insurance_limit:
        text = _(
            "Insurance of %(aircraft)s until %(expiry)s: this request can end on "
            "%(limit)s at the latest."
        ) % {
            "aircraft": insurance_limit["aircraft"],
            "expiry": insurance_limit["expiry"],
            "limit": insurance_limit["limit"],
        }
        tone = CRITICAL if insurance_limit["exceeded"] else CAUTION
        found["insurance"] = _item("insurance", tone, text)
    if open_for_work and not (permission.permission_number or "").strip():
        found["folio"] = _item("folio", WARNING, _("DGAC folio pending."))
    missing = dossier["missing_count"] if dossier else 0
    if open_for_work and missing:
        found["dossier"] = _item(
            "dossier",
            WARNING,
            _("Operational dossier incomplete (missing: %(count)s).")
            % {"count": missing},
        )
    if (
        open_for_work
        and not (permission.region or permission.commune)
        and not derived_location
    ):
        found["region"] = _item("region", WARNING, _("Region not recorded."))
    ordered = [found[key] for key in ATTENTION_ORDER if key in found]
    return ordered[:MAX_ATTENTION_ITEMS]


def _days_left(permission, today):
    if permission.valid_until is None:
        return None
    return (permission.valid_until - today).days


def open_sections(
    permission,
    *,
    dossier,
    derived_location,
    preflight_checks,
    today=None,
):
    """Qué secciones `<details>` van abiertas: las que tienen algo que atender.

    «Operación» siempre. «Ubicación» si falta región o coordenadas. «Vigencia y
    documentos» con 30 días o menos, vencido, o sin la autorización firmada.
    «Prevuelo y vuelos» si hay un chequeo sin firmar. «Trazabilidad», nunca.
    El estado de un `<details>` se pierde si htmx reemplaza el bloque: por eso se
    decide acá y la ficha **no** se reemplaza por htmx.
    """
    today = today or timezone.localdate()
    days = _days_left(permission, today)
    window_closing = permission.has_lapsed or (
        permission.status
        in (FlightPermission.STATUS_REQUESTED, FlightPermission.STATUS_APPROVED)
        and days is not None
        and days <= VALIDITY_OPEN_DAYS
    )
    authorization_missing = any(
        item.key == "signed_authorization" and item.status == "missing"
        for item in (dossier["items"] if dossier else [])
    )
    location_gap = permission.latitude is None or not (
        permission.region or permission.commune or derived_location
    )
    return {
        "operation": True,
        "location": location_gap,
        "validity": window_closing or authorization_missing,
        "flights": any(not check.is_signed for check in preflight_checks),
        "trace": False,
    }


def validity_line(permission, today=None):
    """Geometría de la línea de tiempo de la vigencia, o `None` sin fechas.

    Sin las dos fechas no hay línea: la ficha dice «Esperando a la DGAC» y nada
    más (la vigencia la fija la DGAC al responder, LV-219; dibujar fechas
    inventadas sería avisar un vencimiento que no existe).

    El SVG mide 300 de ancho y la pista va de 10 a 290. `elapsed_w` es lo
    transcurrido y `today_x` la marca de hoy, recortada a los extremos.
    """
    start, end = permission.valid_from, permission.valid_until
    if not (isinstance(start, date) and isinstance(end, date)):
        return None
    today = today or timezone.localdate()
    left, width = 10, 280
    span = max((end - start).days, 1)
    fraction = min(max((today - start).days / span, 0), 1)
    days = (end - today).days
    if today < start:
        state, tone = "pending", "nominal"
        text = _("Starts on %(date)s.") % {"date": start.isoformat()}
    elif days < 0:
        state, tone = "ended", "critical"
        text = _("The window ended on %(date)s.") % {"date": end.isoformat()}
    else:
        state = "running"
        tone = "warning" if days <= VALIDITY_OPEN_DAYS else "nominal"
        text = _("Days left: %(days)s") % {"days": days}
    return {
        "left": left,
        "width": width,
        "elapsed_w": round(width * fraction, 1),
        "today_x": round(left + width * fraction, 1),
        "state": state,
        "tone": tone,
        "text": text,
        "start": start,
        "end": end,
    }


WAITING_LABELS = {
    FlightPermission.WAITING_DGAC: lambda: _("Waiting on the DGAC"),
    FlightPermission.WAITING_OPERATOR: lambda: _("Waiting on the operator"),
}


def waiting_label(permission):
    """«Espera a la DGAC» / «Espera al operador», o `""` si no espera a nadie."""
    make = WAITING_LABELS.get(permission.waiting_on())
    return make() if make else ""
