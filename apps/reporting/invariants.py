"""LV-378: el guardián de cifras del informe — que las partes del documento cuadren.

El informe de octubre salió con **un Total que decía 15 sobre filas que sumaban 14**,
una observación que hablaba de «permisos vigentes» de una faena con cero, y una
cobertura «5/11» que no incluía a la faena que el resumen sí contaba. Ninguna era un
error de cálculo: eran **desacuerdos entre partes del mismo payload**, porque las
cifras salían de fuentes distintas leyendo estados distintos (hoy y al corte).

Esto las cruza. Es una función **pura** sobre el payload congelado —no consulta la
base—, y la usan tres lugares: los tests (sobre un fixture con todos los casos
límite), `checks.pre_issue_warnings` (aviso en pantalla, no bloquea) y el test del
`build`, que la corre como `assert` para que un cambio que descuadre las fuentes
falle en el gate y no en la mesa de quien firma.

Sólo mira payloads de diseño 2 (`meta.layout == 2`): los anteriores no traen las
llaves nuevas y se emitieron con otras cuentas, que no se juzgan con las de ahora.

Cada violación es un código (`I1`…`I8`) y sus datos; el texto, traducido, lo pone
`check`.
"""

from django.utils.translation import gettext as _

from apps.reporting.groups import permit_groups

#: Número del diseño que declara las llaves que estas invariantes leen.
LAYOUT = 2


def _value(payload, key):
    leaf = (payload.get("kpis") or {}).get(key)
    return leaf.get("value") if isinstance(leaf, dict) else None


def _in_force(permits):
    return [row for row in permits if row.get("in_force")]


def violations(payload):
    """Las invariantes rotas, como `[(código, {datos})]`. Vacía si todo cuadra."""
    if ((payload.get("meta") or {}).get("layout") or 1) < LAYOUT:
        return []

    centres = payload.get("cost_centres") or []
    outside = payload.get("outside_centres") or []
    permits = payload.get("permits") or []
    in_force = _in_force(permits)
    awaiting = [row for row in permits if row.get("status") == "requested"]
    found = []

    def broken(name, **data):
        found.append((name, data))

    # I1: el denominador del «X de N» es exactamente la lista de faenas de la cobertura.
    total = _value(payload, "cost_centres_with_operation")
    if total != len(centres):
        broken("I1", kpi=total, rows=len(centres))

    # I2: «sin permiso vigente» son las filas de la cobertura que están en cero.
    zero = sum(1 for row in centres if not row.get("permits_in_force"))
    declared = _value(payload, "cost_centres_without_permit")
    if declared != zero:
        broken("I2", kpi=declared, rows=zero)

    # I3: los vigentes de la cobertura más los de las faenas sin operación son todos
    # los vigentes, y son los permisos marcados `in_force` (y su desglose cuadra).
    by_rows = sum(row.get("permits_in_force", 0) for row in centres)
    by_outside = sum(row.get("permits_in_force", 0) for row in outside)
    kpi = _value(payload, "permits_in_force")
    operating = sum(1 for row in in_force if row.get("in_operation"))
    if (
        not (by_rows + by_outside == kpi == len(in_force))
        or _value(payload, "permits_in_force_operating") != operating
        or _value(payload, "permits_in_force_outside") != len(in_force) - operating
        or operating != by_rows
    ):
        broken("I3", rows=by_rows, outside=by_outside, kpi=kpi, permits=len(in_force))

    # I4: lo mismo para los permisos en trámite.
    aw_rows = sum(row.get("permits_awaiting", 0) for row in centres)
    aw_out = sum(row.get("permits_awaiting", 0) for row in outside)
    aw_kpi = _value(payload, "permits_awaiting")
    if not (aw_rows + aw_out == aw_kpi == len(awaiting)):
        broken("I4", rows=aw_rows, outside=aw_out, kpi=aw_kpi, permits=len(awaiting))

    # I5: todo permiso pertenece a la cobertura o a un centro sin operación, y su
    # marca `in_operation` dice cuál. Ninguno huérfano.
    covered = {row["code"] for row in centres}
    outside_codes = {row["code"] for row in outside}
    orphans = sorted(
        {
            row["cost_centre"]
            for row in permits
            if row["cost_centre"] not in covered | outside_codes
            or bool(row.get("in_operation")) != (row["cost_centre"] in covered)
        }
    )
    if orphans:
        broken("I5", codes=", ".join(orphans))

    # I6: la fecha y los días de cada faena son el mínimo de sus permisos vigentes.
    for row in centres:
        own = [p for p in in_force if p["cost_centre"] == row["code"]]
        days = min((p["days_remaining"] for p in own), default=None)
        expiry = min((p["valid_until"] for p in own), default=None)
        if row.get("days_remaining") != days or row.get("next_expiry") != expiry:
            broken("I6", code=row["code"])

    # I7: la concentración nombra sólo faenas de la cobertura; y lo que mide
    # renovación (vencen en 30 y en 60 días) se recuenta igual desde las filas.
    concentration = payload.get("concentration") or {}
    named = set(concentration.get("cost_centres_on_one_person_operating") or [])
    for key, limit in (
        ("permits_expiring_30d_operating", 30),
        ("permits_expiring_60d_operating", 60),
    ):
        counted = sum(
            1
            for row in in_force
            if row.get("in_operation") and row["days_remaining"] <= limit
        )
        if _value(payload, key) != counted:
            broken("I7", key=key, kpi=_value(payload, key), rows=counted)
    if not named <= covered:
        broken(
            "I7", key="concentration", kpi=", ".join(sorted(named - covered)), rows=0
        )

    # I8: ninguna fila de más ni de menos. Cada permiso es vigente, está en trámite o es
    # un aprobado vencido sin cerrar (y el anexo «permiso a permiso» lista las tres
    # cosas); y la suma de los grupos de la sección 2 —vigentes de faenas con
    # operación más los de las sin operación, con **todos sus folios**— da el total.
    # Es la comprobación que contiene el recorte silencioso de una hoja: el cuerpo es
    # `overflow: hidden`, y el total declarado en el rótulo sólo sirve si es cierto.
    lapsed = [
        row
        for row in permits
        if not row.get("in_force") and row.get("status") == "approved"
    ]
    grouped = permit_groups(payload)
    folios = sum(len(group["folios"]) for group in grouped["operating"]) + sum(
        len(group["folios"]) for group in grouped["outside"]
    )
    if (
        len(in_force) + len(awaiting) + len(lapsed) != len(permits)
        or grouped["operating_in_force"] != operating
        or grouped["outside_in_force"] != len(in_force) - operating
        or folios != len(in_force)
    ):
        broken("I8", permits=len(permits))

    return found


def check(payload):
    """Las invariantes rotas, ya redactadas (para el aviso de pantalla)."""
    return [_message(code, data) for code, data in violations(payload)]


def _message(code, data):
    if code == "I1":
        return _(
            "The coverage figure says %(kpi)s cost centres with operation but the "
            "table lists %(rows)s."
        ) % {"kpi": data["kpi"], "rows": data["rows"]}
    if code == "I2":
        return _(
            "The figure “cost centres without a permit in force” (%(kpi)s) does "
            "not match the table (%(rows)s)."
        ) % {"kpi": data["kpi"], "rows": data["rows"]}
    if code == "I3":
        return (
            _(
                "The permits in force do not add up: %(rows)s in the coverage table "
                "plus %(outside)s outside it, against %(kpi)s in the figure and "
                "%(permits)s in the list."
            )
            % data
        )
    if code == "I4":
        return (
            _(
                "The permits awaiting the DGAC do not add up: %(rows)s in the coverage "
                "table plus %(outside)s outside it, against %(kpi)s in the figure and "
                "%(permits)s in the list."
            )
            % data
        )
    if code == "I5":
        return (
            _(
                "These cost centres have permits but are in neither the coverage table "
                "nor the block of centres without operation: %(codes)s."
            )
            % data
        )
    if code == "I6":
        return (
            _("The first expiry shown for %(code)s is not that of its earliest permit.")
            % data
        )
    if code == "I7":
        return (
            _(
                "The figure “%(key)s” (%(kpi)s) does not match what the rows give "
                "(%(rows)s)."
            )
            % data
        )
    return (
        _("The list of permits has rows that fit no block (%(permits)s in total).")
        % data
    )
