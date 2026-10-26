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
from datetime import date, timedelta

from django.utils.formats import date_format
from django.utils.translation import gettext as _, ngettext

from apps.reporting import invariants

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


#: LV-378: cuántos caracteres hacia atrás se mira una negación antes de «vigente».
#: «sin permiso vigente», «no tiene permisos vigentes», «ningún permiso vigente».
NEGATION_WINDOW = 40
NEGATION = re.compile(r"\b(sin|no|ning\w+|carece\w*)\b", re.IGNORECASE)
CURRENT = re.compile(r"\bvigentes?\b", re.IGNORECASE)
NO_PERMIT = re.compile(
    r"\b(?:sin|no\s+(?:tiene|cuenta\s+con|posee))\s+(?:ning\w+\s+)?permisos?\b",
    re.IGNORECASE,
)
SENTENCE = re.compile(r"(?<=[.;!?\n])\s+")


def _figures_by_centre(payload):
    """`{código: (vigentes, en trámite)}` de la cobertura y de las faenas sin operación."""
    found = {}
    for row in (payload.get("cost_centres") or []) + (
        payload.get("outside_centres") or []
    ):
        found[row["code"]] = (
            row.get("permits_in_force") or 0,
            row.get("permits_awaiting") or 0,
        )
    return found


def narrative_vs_figures(payload, run):
    """LV-378: las contradicciones entre lo escrito y las cifras, sólo en pantalla.

    El informe de octubre decía «permisos vigentes del CC 706» y CC706 tenía **cero**
    vigentes y uno en trámite al corte: lo detectó quien lo leyó, no el sistema. Se
    parte la observación y los hallazgos en oraciones; si una nombra una faena y
    dice «vigente(s)» **sin negación delante**, y esa faena tiene cero vigentes, se
    avisa. Y al revés: «sin permiso» sobre una faena que sí tiene vigentes.

    Es una heurística, no una prueba: no bloquea y dice qué vio. Una oración que
    nombra varias faenas se juzga por cada una, y un aviso de más cuesta una lectura;
    uno de menos, un papel firmado con una frase falsa.
    """
    if run is None:
        return []
    figures = _figures_by_centre(payload)
    texts = [run.period_note or ""] + [
        f"{f.get('title', '')}. {f.get('text', '')}" for f in run.findings or []
    ]
    found, seen = [], set()
    for text in texts:
        for sentence in SENTENCE.split(text):
            codes = {f"CC{n}" for n in CODE.findall(sentence)} & set(figures)
            if not codes:
                continue
            claims_current = any(
                not NEGATION.search(
                    sentence[max(0, m.start() - NEGATION_WINDOW) : m.start()]
                )
                for m in CURRENT.finditer(sentence)
            )
            claims_none = bool(NO_PERMIT.search(sentence))
            for code in sorted(codes):
                in_force, awaiting = figures[code]
                if claims_current and not in_force and (code, "current") not in seen:
                    seen.add((code, "current"))
                    found.append(
                        _(
                            "The text speaks of permits in force of %(code)s, which "
                            "has %(in_force)s in force and %(awaiting)s awaiting the "
                            "DGAC at the cutoff."
                        )
                        % {"code": code, "in_force": in_force, "awaiting": awaiting}
                    )
                if claims_none and in_force and (code, "none") not in seen:
                    seen.add((code, "none"))
                    found.append(
                        _(
                            "The text says %(code)s has no permit, but it has "
                            "%(in_force)s in force at the cutoff."
                        )
                        % {"code": code, "in_force": in_force}
                    )
    return found


def previous_total_change(payload, previous):
    """(antes, ahora) si el total de faenas con operación cambió contra el mes anterior."""
    if previous is None:
        return None
    before = previous.payload.get("kpis", {}).get("cost_centres_with_operation")
    now = payload.get("kpis", {}).get("cost_centres_with_operation")
    if not before or not now or before.get("value") == now.get("value"):
        return None
    return before.get("value"), now.get("value")


def _day_month(iso):
    try:
        return f"{date.fromisoformat(iso):%d-%m}"
    except (TypeError, ValueError):
        return str(iso)


def early_cutoff_warnings(payload):
    """LV-375: lo que dice el corte anticipado y su cierre, sólo en pantalla.

    Sin bloquear: emitir con el mes abierto es legítimo, pero hay que saber qué
    días quedaron fuera y que el cierre vendrá detrás.
    """
    meta = payload.get("meta") or {}
    found = []
    if meta.get("early_cutoff"):
        try:
            closing = date.fromisoformat(meta["covers"]["to"]) + timedelta(days=1)
            closing_text = date_format(closing, "DATE_FORMAT")
        except (KeyError, TypeError, ValueError):
            closing_text = "?"
        days = int(meta.get("days_remaining") or 0)
        found.append(
            ngettext(
                "Early cutoff on %(cutoff)s: %(days)d day of the month is not "
                "included; the closing revision will be issued on %(closing)s.",
                "Early cutoff on %(cutoff)s: %(days)d days of the month are not "
                "included; the closing revision will be issued on %(closing)s.",
                days,
            )
            % {
                "cutoff": _day_month(meta.get("cutoff")),
                "days": days,
                "closing": closing_text,
            }
        )
    if meta.get("replaces_early_cutoff"):
        found.append(
            _(
                "This revision replaces the early-cutoff one (%(cutoff)s); its "
                "narrative was copied: review it."
            )
            % {"cutoff": _day_month(meta["replaces_early_cutoff"])}
        )
    return found


def pre_issue_warnings(payload, run, previous=None):
    """Los avisos, ya redactados. Lista vacía si no hay nada que mirar."""
    warnings = []
    warnings.extend(early_cutoff_warnings(payload))
    # LV-378: que las cifras del documento cuadren entre sí, y que lo escrito no
    # las contradiga. Avisos, no bloqueos.
    warnings.extend(invariants.check(payload))
    warnings.extend(narrative_vs_figures(payload, run))
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
