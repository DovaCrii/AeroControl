"""LV-265: lo que hay que mirar **antes de emitir** el informe.

Una revisión del PDF de producción (2026-10-05) encontró cuatro cosas que el
informe no le dijo a nadie: un permiso vigente cuya faena no sale en la tabla de
cobertura, una faena nombrada en un hallazgo que no está registrada, la
observación del período sin redactar y el total de faenas que bajó de un mes a
otro. Ninguna es un error de cálculo: son **desacuerdos entre partes del mismo
informe** (los permisos se listan de todas las faenas; la cobertura sólo de las
que operan), y un lector externo los ve antes que quien lo emite.

Todo sale del payload y de los textos escritos, igual que la hoja ejecutiva:
nada recalcula contra la base, así que un informe congelado se revisa con lo
que congeló. Son avisos de pantalla: no bloquean aprobar, porque el motivo
puede ser legítimo — por eso dicen qué pasó y no deciden.
"""

import re

from django.utils.translation import gettext as _

# «CC 741» con espacio también: así lo escribió el hallazgo del informe de
# septiembre, y una comprobación que sólo ve «CC741» no habría visto el error.
CODE = re.compile(r"\bCC\s?(\d+)\b")


def _codes(payload):
    return {row["code"] for row in payload.get("cost_centres", [])}


def permits_outside_coverage(payload):
    """Permisos vigentes de faenas que la tabla de cobertura no lista.

    `permit_status_by_cost_center` sólo trae faenas activas, que operan vuelos y
    con contrato vigente; los permisos se listan de **todas**. Una faena
    excluida con un permiso vivo es o un dato mal cargado (operación o contrato)
    o una faena que sí opera y no se está contando: la cifra «X de N» que va
    firmada a la DGAC no la incluye en ninguno de los dos casos.
    """
    listed = _codes(payload)
    found = {}
    for row in payload.get("permits", []):
        if row.get("in_force") and row["cost_centre"] not in listed:
            found.setdefault(row["cost_centre"], []).append(row["folio"])
    return [{"code": code, "folios": folios} for code, folios in sorted(found.items())]


def unknown_codes_in_text(payload, run):
    """Faenas nombradas en los hallazgos o en la observación que no existen acá."""
    if run is None:
        return []
    known = _codes(payload) | {row["cost_centre"] for row in payload.get("permits", [])}
    text = " ".join(
        [run.period_note or ""]
        + [f"{f.get('title', '')} {f.get('text', '')}" for f in run.findings or []]
    )
    return sorted({f"CC{number}" for number in CODE.findall(text)} - known)


def previous_total_change(payload, previous):
    """(antes, ahora) si el total de faenas con operación cambió contra el mes anterior."""
    if previous is None:
        return None
    before = previous.payload.get("kpis", {}).get("cost_centres_with_operation")
    now = payload.get("kpis", {}).get("cost_centres_with_operation")
    if not before or not now or before.get("value") == now.get("value"):
        return None
    return before.get("value"), now.get("value")


def pre_issue_warnings(payload, run, previous=None):
    """Los avisos, ya redactados. Lista vacía si no hay nada que mirar."""
    warnings = []
    for item in permits_outside_coverage(payload):
        warnings.append(
            _(
                "%(code)s has a permit in force (%(folios)s) but is not in the "
                "coverage table: it is closed, inactive or marked as not flying. "
                "The “X of N cost centres” figure does not count it."
            )
            % {"code": item["code"], "folios": ", ".join(item["folios"])}
        )
    for code in unknown_codes_in_text(payload, run):
        warnings.append(
            _(
                "The written text names %(code)s, which is not a cost centre of "
                "this report."
            )
            % {"code": code}
        )
    if run is not None and run.is_editable:
        if not run.period_note:
            warnings.append(
                _("The period observation (section 2) is still not written.")
            )
        if not run.findings:
            warnings.append(_("The findings of the period are still not written."))
    change = previous_total_change(payload, previous)
    if change:
        warnings.append(
            _(
                "The total of cost centres went from %(before)s to %(now)s since "
                "the previous report. Closed cost centres stopped counting on "
                "2026-09-14; if that is not the reason, review the registry."
            )
            % {"before": change[0], "now": change[1]}
        )
    return warnings
