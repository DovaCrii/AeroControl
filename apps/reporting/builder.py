"""R0/R2: construir el payload del informe mensual desde lo que ya existe.

**Ni un número se calcula acá.** Cada hoja del payload sale de una función del
dominio que ya estaba escrita y probada — `permit_counts`, `panel_readiness`,
`upcoming_expirations`, `permit_status_by_cost_center` —, y este módulo sólo las
llama y ordena el resultado. Es lo que `MAPPING.md` dejó dicho: la §6 del SPEC
proponía escribir colectores de cero y buena parte estaba hecha.

La regla que manda sobre todo lo demás, del propio SPEC: **el informe nunca
inventa un dato.** Cuando un valor no existe, la hoja vale `None` y su ruta entra
en `missing_fields` — no se rellena con cero, porque un cero es una afirmación
("hay cero") y `None` es la ausencia de una ("no se sabe"). Confundirlas es lo que
haría que el informe declarara cumplimiento donde sólo hay un hueco de carga.
"""

from datetime import date

FIRST_DAY = 1


def month_bounds(period):
    """El primer y el último día del mes de `period`.

    Sin `calendar.monthrange` ni `relativedelta`: sumar un mes y restar un día es
    la misma cuenta y no arrastra dependencia (mismo criterio que `LV-224`).
    """
    start = period.replace(day=FIRST_DAY)
    following = (
        date(start.year + 1, 1, FIRST_DAY)
        if start.month == 12
        else date(start.year, start.month + 1, FIRST_DAY)
    )
    return start, date.fromordinal(following.toordinal() - 1)


def leaf(value, source, cutoff):
    """Una hoja del payload: valor, procedencia y fecha de corte.

    El contrato del SPEC (§3) pide las tres cosas en cada hoja, y la procedencia
    no es adorno: el informe emitido cita "Fuente: AeroControl, corte al
    31-08-2026" al pie de cada página, y esa frase tiene que poder reconstruirse
    del dato y no escribirse a mano.
    """
    return {"value": value, "source": source, "cutoff": cutoff.isoformat()}


def collect_meta(period, cutoff):
    start, end = month_bounds(period)
    return {
        "period": f"{period:%Y-%m}",
        "code": f"JEJ-GTE-CT-INF-RPA-{period:%Y-%m}",
        "cutoff": cutoff.isoformat(),
        "covers": {"from": start.isoformat(), "to": end.isoformat()},
        # Del estándar, no de la base: son los cargos que firman.
        "issued_by": "Gerente de Operaciones Aéreas ante la DGAC",
        "jointly_with": "Jefe Seguridad Aérea ante la DGAC",
        "standard": "JEJ-GRI-SS-INS-096 Rev. 0",
        # R3: los tres campos que faltaban de la portada del informe emitido.
        # Van acá y no en la plantilla por la misma razón que los dos de arriba:
        # son texto del **documento**, y el documento se re-renderiza desde el
        # payload congelado. Escritos en la plantilla, un cambio de cargo
        # reescribiría en silencio los informes ya emitidos.
        "addressed_to": (
            "Gerencia General · Gerencia de Riesgo · "
            "Gerencia de Ingeniería · Administradores de Contrato"
        ),
        "scope": "Vigencia de permisos de vuelo ante la DGAC",
        "sources": "AeroControl · SIGO — DGAC",
    }


def collect_kpis(cutoff, cost_centres):
    """Los indicadores de portada, cada uno de su función de siempre.

    `cost_centres` llega ya calculado en vez de volver a consultarlo: la faena
    sin permiso vigente es el indicador **7 de 12** de la página 2, y su
    denominador tiene que ser exactamente el mismo universo que
    `cost_centres_with_operation` — dos recorridos separados es cómo el informe
    empieza a decir "7 de 12" en una página y "7 de 11" en la siguiente.
    """
    from apps.compliance.kpis import permit_counts
    from apps.dashboard.views import panel_readiness
    from apps.registry.models import CostCenter

    permits = permit_counts(cutoff)
    readiness = {card["key"]: card for card in panel_readiness(cutoff)["readiness"]}
    # `operates_flights`: `CC110` y `CC410` administran equipos y no vuelan
    # (`LV-205`), así que contarlas como faenas con operación las declararía
    # incumplidas por algo que no les toca — el mismo criterio que `LV-229`
    # aplicó al contador de seguros.
    flying = CostCenter.objects.filter(is_active=True, operates_flights=True)

    return {
        "cost_centres_with_operation": leaf(flying.count(), "registry", cutoff),
        # El hallazgo que abre el informe emitido: "solo 5 de 12 Centros de Costo
        # cuentan con permiso de vuelo vigente". Se cuenta sobre las filas ya
        # recolectadas, que salen de `permit_status_by_cost_center` — la consulta
        # que parte de las faenas justamente para que las que no tienen ningún
        # permiso existan como fila (`LV-206`).
        "cost_centres_without_permit": leaf(
            sum(1 for row in cost_centres if not row["permits_in_force"]),
            "operations",
            cutoff,
        ),
        "permits_in_force": leaf(permits["in_force"], "operations", cutoff),
        "permits_awaiting": leaf(permits["awaiting"], "operations", cutoff),
        "permits_lapsed": leaf(permits["lapsed"], "operations", cutoff),
        "permits_expiring_30d": leaf(permits["soon"], "operations", cutoff),
        "fleet_total": leaf(readiness["fleet"]["total"], "registry", cutoff),
        "fleet_flyable": leaf(readiness["fleet"]["count"], "registry", cutoff),
        "insurance_up_to_date": leaf(
            readiness["insurance"]["count"], "registry", cutoff
        ),
        "operators_total": leaf(readiness["credentials"]["total"], "registry", cutoff),
        "operators_credentialed": leaf(
            readiness["credentials"]["count"], "registry", cutoff
        ),
    }


def collect_cost_centres(cutoff):
    """Una fila por faena que vuela, **incluidas las que no tienen permiso**.

    Se apoya en `permit_status_by_cost_center` (`LV-206`), que ya parte de las
    faenas y no de los permisos precisamente para eso: un `GROUP BY` sobre
    permisos sólo devuelve las que tienen alguno, y las que interesan en un
    informe de cumplimiento son las que **no** tienen ninguno. La página 3 del
    informe de agosto lista 12 faenas y 7 sin habilitación; con el recorrido al
    revés esas 7 no existirían.
    """
    from apps.compliance.kpis import permit_status_by_cost_center

    return [
        {
            # La fila trae el objeto `cost_center`, no sus campos sueltos.
            "code": row["cost_center"].code,
            "name": row["cost_center"].name,
            "permits_in_force": row["in_force"],
            "permits_awaiting": row["awaiting"],
            "permits_lapsed": row["lapsed"],
            "permits_expiring_30d": row["soon"],
        }
        for row in permit_status_by_cost_center(cutoff)
    ]


def find_missing(node, path=""):
    """Las rutas del payload cuya hoja no tiene valor.

    Recorre el árbol buscando `{"value": None}`. Se calcula una vez al construir
    y se **guarda**: el informe tiene que seguir diciendo qué faltaba cuando se
    emitió, no qué falta hoy (ver el campo en el modelo).
    """
    missing = []
    if isinstance(node, dict):
        if "value" in node and "source" in node:
            if node["value"] is None:
                missing.append(path)
            return missing
        for key, value in node.items():
            missing.extend(find_missing(value, f"{path}.{key}" if path else key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            missing.extend(find_missing(value, f"{path}[{index}]"))
    return missing


def build(period, cutoff=None):
    """El payload del período, listo para congelar en un `ReportRun`.

    `cutoff` por defecto es el último día del mes: un informe mensual describe el
    mes cerrado, y usar "hoy" haría que el mismo período diera cifras distintas
    según cuándo se generara — que es justo lo que congelar el dato viene a
    evitar.
    """
    _start, end = month_bounds(period)
    cutoff = cutoff or end
    cost_centres = collect_cost_centres(cutoff)
    payload = {
        "meta": collect_meta(period, cutoff),
        "kpis": collect_kpis(cutoff, cost_centres),
        "cost_centres": cost_centres,
    }
    return payload, find_missing(payload)
