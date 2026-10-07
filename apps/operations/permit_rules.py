"""LV-287: el permiso no puede correr más allá del seguro de sus aeronaves.

Pedido del usuario (2026-10-07, con la captura de una solicitud en el portal de SIGO:
operación hasta el 20/12/2026 y «Vigencia Seguro JAC» el 21/12/2026):

> *cuando el seguro de vuelo vence en cierta fecha no puede cumplir el límite de 3
> meses; cuando tiene seguro vigente puede optar hasta los 3 meses. […] restringir
> cuando incumpla y recomendar la fecha con un día de anticipación: si el seguro
> vence el 21 de diciembre, el permiso será hasta el 20 de diciembre.*

Así que el techo de una solicitud es el **menor** de dos: los tres meses que autoriza la
DGAC (`FlightPermission.latest_allowed_valid_until`) y **el día anterior al vencimiento
del seguro más próximo a vencer** entre las aeronaves del permiso. Un permiso que
termina el mismo día que el seguro deja un día de vuelo sin cobertura, y la
aeronave de esa solicitud no estaría autorizada a operar ese día.

**Sólo para permisos solicitados.** Un permiso aprobado refleja lo que la DGAC ya emitió:
no se le puede «restringir» una vigencia que ya existe, y los vencimientos de seguro ya
tienen sus alertas. La regla es de lo que **esta organización pide**.

Una aeronave sin fecha de seguro no restringe nada: no haber cargado la fecha es
«desconocido», no «vencido» (el criterio de `LV-29`). El motivo de excepción
(`validity_override_reason`) **no la salta**: ese campo existe para un plazo que la
DGAC concedió distinto, y el seguro no es un plazo de la DGAC.
"""

from datetime import timedelta

from django.utils.translation import gettext as _


def insurance_cutoff(aircraft):
    """El último día en que el permiso puede terminar por el seguro, o None.

    Devuelve `(fecha_límite, aeronave)`: la aeronave cuyo seguro vence primero, para
    poder nombrarla en el mensaje. `None` si ninguna tiene fecha de seguro.
    """
    dated = [item for item in aircraft if item.insurance_expiry is not None]
    if not dated:
        return None
    earliest = min(dated, key=lambda item: item.insurance_expiry)
    return earliest.insurance_expiry - timedelta(days=1), earliest


def insurance_window_errors(valid_from, valid_until, aircraft):
    """Los errores de la ventana del permiso contra el seguro, `{campo: mensaje}`.

    - Si el seguro vence **antes de que el permiso empiece**, el error va en la fecha
      de inicio: ninguna fecha de término lo arregla.
    - Si no, y el término pasa del límite, el error va en el término y **dice la
      fecha recomendada** (el día anterior al vencimiento).
    """
    cutoff = insurance_cutoff(aircraft)
    if cutoff is None:
        return {}
    limit, aircraft_item = cutoff
    context = {
        "aircraft": aircraft_item.registration,
        "expiry": aircraft_item.insurance_expiry.isoformat(),
        "limit": limit.isoformat(),
    }
    if valid_from is not None and valid_from > limit:
        return {
            "valid_from": _(
                "The insurance of %(aircraft)s expires on %(expiry)s, which is "
                "before this permit would start. Renew the insurance first."
            )
            % context
        }
    if valid_until is not None and valid_until > limit:
        return {
            "valid_until": _(
                "The insurance of %(aircraft)s expires on %(expiry)s, so the permit "
                "cannot run past the day before. Set the end date to %(limit)s "
                "or earlier."
            )
            % context
        }
    return {}
