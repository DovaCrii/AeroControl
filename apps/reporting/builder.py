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

from datetime import date, timedelta

FIRST_DAY = 1

#: LV-378: la versión del diseño del documento. `collect_meta` escribe `2` **sólo en
#: los informes nuevos** (como `early_cutoff`): los payloads anteriores no traen la
#: llave y se siguen dibujando exactamente como se emitieron. Es lo que protege a
#: agosto y septiembre, que se vuelven a dibujar desde su payload con las
#: plantillas de hoy.
LAYOUT = 2


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


def collect_meta(period, cutoff, early=False, early_reason=""):
    start, end = month_bounds(period)
    return {
        "period": f"{period:%Y-%m}",
        "code": f"JEJ-GTE-CT-INF-RPA-{period:%Y-%m}",
        "cutoff": cutoff.isoformat(),
        "covers": {"from": start.isoformat(), "to": end.isoformat()},
        # LV-233: que el período siga abierto es un hecho **del documento**, así
        # que viaja en el payload congelado y no se recalcula al dibujar. Un
        # informe que se congeló a mitad de mes tiene que seguir diciendo que se
        # congeló a mitad de mes, aunque se lea en diciembre.
        "in_progress": cutoff < end,
        "days_remaining": max((end - cutoff).days, 0),
        # LV-375: un informe emitido **a propósito** con el mes abierto. Es distinto
        # de `in_progress`, que también es cierto para una vista previa: acá una
        # persona lo congeló y respondió por el motivo. Sólo se escribe la llave si
        # es anticipado, para que los informes cerrados no cambien ni un byte. El
        # motivo queda en el payload (auditoría) y **no se imprime**.
        **({"early_cutoff": True, "early_reason": early_reason} if early else {}),
        # LV-378: el diseño con el que se emite este informe. Un informe congelado
        # sin la llave es de diseño 1 y no se toca.
        "layout": LAYOUT,
        # LV-249: los textos de la portada salen de los **bloques editables**
        # (`ReportTemplate`) y no de literales de este archivo. Siguen yendo al
        # payload —no a la plantilla— por la razón que `R3` dejó escrita acá: el
        # documento se re-renderiza desde el payload congelado, así que editar un
        # cargo hoy no reescribe en silencio los informes ya emitidos.
        **_cover_texts(),
    }


#: LV-249: los textos de fábrica de la portada. Sólo se usan si la base no tiene
#: bloques sembrados (la migración `0005` los crea), para que un informe nunca deje
#: de generarse por falta de configuración.
FACTORY_COVER = {
    "issued_by": "Gerente de Operaciones Aéreas ante la DGAC",
    "jointly_with": "Jefe Seguridad Aérea ante la DGAC",
    "standard": "JEJ-GRI-SS-INS-096 Rev. 0",
    "addressed_to": (
        "Gerencia General · Gerencia de Riesgo · "
        "Gerencia de Ingeniería · Administradores de Contrato"
    ),
    "scope": "Vigencia de permisos de vuelo ante la DGAC",
    "sources": "AeroControl · SIGO — DGAC",
}


def _cover_texts():
    from apps.reporting.models import ReportTemplate

    template = ReportTemplate.current()
    if template is None:
        return dict(FACTORY_COVER)
    return {field: getattr(template, field) for field in FACTORY_COVER}


def collect_kpis(cutoff, cost_centres, permit_rows):
    """Los indicadores de portada, cada uno de su función de siempre.

    `cost_centres` llega ya calculado en vez de volver a consultarlo: la faena
    sin permiso vigente es el indicador **7 de 12** de la página 2, y su
    denominador tiene que ser exactamente el mismo universo que
    `cost_centres_with_operation` — dos recorridos separados es cómo el informe
    empieza a decir "7 de 12" en una página y "7 de 11" en la siguiente.

    `permit_rows` llega por lo mismo, y `LV-233` lo demostró en producción: los
    cuatro contadores del encabezado salían de `permit_counts`, que resuelve el
    estado de **hoy**, mientras la tabla de abajo se reconstruye **al corte**.
    Con eso el encabezado decía "0 en trámite" sobre una tabla que listaba tres.
    """
    from apps.compliance.kpis import PERMIT_CRITICAL_DAYS, PERMIT_WARNING_DAYS
    from apps.compliance.models import NonConformity
    from apps.dashboard.views import panel_readiness

    # El primer día del mes al que pertenece el corte: los incidentes se cuentan
    # **del período**, no acumulados, y sin esto un informe de agosto sumaría los
    # de todo el año.
    period_start = cutoff.replace(day=1)

    readiness = {card["key"]: card for card in panel_readiness(cutoff)["readiness"]}

    return {
        # ⚠️ **El denominador sale de las filas ya recolectadas, no de una
        # consulta propia**, y eso cerró un defecto real.
        #
        # Era `CostCenter.objects.filter(is_active=True, operates_flights=True)
        # .count()`: una segunda consulta que *debía* devolver el mismo universo
        # que `cost_centres`, con el docstring de esta función advirtiendo que
        # "dos recorridos separados es cómo el informe empieza a decir 7 de 12 en
        # una página y 7 de 11 en la siguiente". El 2026-09-14 se separaron de
        # verdad: `permit_status_by_cost_center` dejó fuera las faenas con
        # contrato cerrado —que ya no operan, así que declararlas sin permiso
        # vigente las acusa por algo que dejó de tocarles— y esta consulta las
        # seguía contando.
        #
        # Contar `len(cost_centres)` los vuelve el mismo número **por
        # construcción**: no hay dos criterios que mantener sincronizados.
        "cost_centres_with_operation": leaf(len(cost_centres), "registry", cutoff),
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
        # LV-233: los cuatro contadores del encabezado **se cuentan sobre las
        # filas ya recolectadas**, igual que la faena sin permiso de arriba y por
        # la misma razón. `permit_counts` resuelve el estado de *hoy*, así que
        # decía "0 en trámite" sobre una tabla que abajo listaba tres — el
        # contraste contra el papel emitido lo dejó a la vista: 11 vigentes y 3
        # en trámite en agosto, 14 y 0 en la app. Un encabezado que contradice a
        # su propia tabla es peor que un encabezado ausente.
        "permits_in_force": leaf(
            sum(1 for row in permit_rows if row["in_force"]), "operations", cutoff
        ),
        "permits_awaiting": leaf(
            sum(1 for row in permit_rows if row["status"] == "requested"),
            "operations",
            cutoff,
        ),
        # Aprobado al corte y con la vigencia ya pasada: nadie lo cerró.
        # Normalmente cero, porque `expire_permissions` los cierra cada noche --
        # y por eso mismo vale mirarlo.
        "permits_lapsed": leaf(
            sum(
                1
                for row in permit_rows
                if row["status"] == "approved"
                and row["days_remaining"] is not None
                and row["days_remaining"] < 0
            ),
            "operations",
            cutoff,
        ),
        "permits_expiring_30d": leaf(
            sum(
                1
                for row in permit_rows
                if row["in_force"] and row["days_remaining"] <= PERMIT_CRITICAL_DAYS
            ),
            "operations",
            cutoff,
        ),
        # R4: la ventana que cuenta el informe emitido. `R3` había dejado la
        # tarjeta rotulada por lo que medía —30 días— porque relabelar 30 como
        # 60 habría sido inventar el dato; ahora mide lo que dice.
        "permits_expiring_60d": leaf(
            sum(
                1
                for row in permit_rows
                if row["in_force"] and row["days_remaining"] <= PERMIT_WARNING_DAYS
            ),
            "operations",
            cutoff,
        ),
        # LV-378: **lo que mide RENOVACIÓN cuenta sólo los centros con operación.**
        # `permits_in_force` (arriba) sigue siendo todos los vigentes —es un hecho
        # legal: SIGO los tiene— y se desglosa en estas dos. Las llaves viejas no
        # cambian de significado porque el comparador y los informes ya emitidos
        # dependen de ellas; lo nuevo va en llaves nuevas.
        "permits_in_force_operating": leaf(
            sum(1 for row in permit_rows if row["in_force"] and row["in_operation"]),
            "operations",
            cutoff,
        ),
        "permits_in_force_outside": leaf(
            sum(
                1 for row in permit_rows if row["in_force"] and not row["in_operation"]
            ),
            "operations",
            cutoff,
        ),
        "permits_expiring_30d_operating": leaf(
            sum(
                1
                for row in permit_rows
                if row["in_force"]
                and row["in_operation"]
                and row["days_remaining"] <= PERMIT_CRITICAL_DAYS
            ),
            "operations",
            cutoff,
        ),
        "permits_expiring_60d_operating": leaf(
            sum(
                1
                for row in permit_rows
                if row["in_force"]
                and row["in_operation"]
                and row["days_remaining"] <= PERMIT_WARNING_DAYS
            ),
            "operations",
            cutoff,
        ),
        # LV-235: **incidentes del período**, el indicador que los dos documentos
        # de referencia piden y que el payload no producía. El informe emitido lo
        # llevaba escrito a mano ("0 Incidentes en el período") y la plantilla del
        # Dato Ejecutivo lo deja como raya.
        #
        # Se cuenta sobre `NonConformity` con `source="incident"` y no sobre todas
        # las no conformidades: un re-vuelo o un entregable rechazado son
        # hallazgos de calidad, no eventos operacionales notificables, y sumarlos
        # inflaría ante la DGAC una cifra que ella lee como incidentes de vuelo.
        #
        # Por **fecha de detección** y no de creación: un evento del 20 de agosto
        # cargado el 2 de septiembre pertenece a agosto, que es de lo que el
        # informe habla. Es la misma distinción que `NotamReview.target_date`.
        "incidents": leaf(
            NonConformity.objects.filter(
                is_active=True,
                source=NonConformity.SOURCE_INCIDENT,
                detected_on__gte=period_start,
                detected_on__lte=cutoff,
            ).count(),
            "compliance",
            cutoff,
        ),
        # Los que siguen abiertos al corte, que es la pregunta que sigue a la
        # anterior: cero incidentes y cero abiertos no son lo mismo que dos
        # incidentes ya cerrados.
        "incidents_open": leaf(
            NonConformity.objects.filter(
                is_active=True,
                source=NonConformity.SOURCE_INCIDENT,
                detected_on__lte=cutoff,
            )
            .exclude(status="closed")
            .count(),
            "compliance",
            cutoff,
        ),
        "fleet_total": leaf(readiness["fleet"]["total"], "registry", cutoff),
        "fleet_flyable": leaf(readiness["fleet"]["count"], "registry", cutoff),
        "insurance_up_to_date": leaf(
            readiness["insurance"]["count"], "registry", cutoff
        ),
        # **"Sin fecha" y "vencida" van separadas, y no es un detalle de
        # presentación.** El informe emitido decía "8 sin credencial vigente";
        # esos 8 eran **7 sin fecha cargada más 1 vencida**, y se arreglan
        # distinto: una es cargar un dato que nadie ingresó y la otra es renovar
        # ante la DGAC. Sumadas, la cifra no dice a quién llamar — y además no
        # conversa con el resto del documento, porque una fecha ausente no
        # genera alerta (`LV-29`: un nulo es "nunca se ingresó") ni aparece en
        # la lista de vencimientos. El panel ya hacía esta distinción desde
        # `LV-129`; el informe la heredaba sumada.
        "insurance_missing": leaf(
            readiness["insurance"]["missing"], "registry", cutoff
        ),
        "insurance_lapsed": leaf(readiness["insurance"]["lapsed"], "registry", cutoff),
        "operators_total": leaf(readiness["credentials"]["total"], "registry", cutoff),
        "operators_credentialed": leaf(
            readiness["credentials"]["count"], "registry", cutoff
        ),
        "credentials_missing": leaf(
            readiness["credentials"]["missing"], "registry", cutoff
        ),
        "credentials_lapsed": leaf(
            readiness["credentials"]["lapsed"], "registry", cutoff
        ),
    }


def operating_centres():
    """Las faenas con operación, ordenadas por código: **una sola definición**.

    Es `operating_cost_centers` (LV-266) y nada más. Se lee acá una vez y de la
    lista salen tanto las filas de la cobertura como el criterio `in_operation`
    de cada permiso.
    """
    from apps.registry.selectors import operating_cost_centers

    return list(operating_cost_centers().order_by("code"))


def collect_cost_centres(cutoff, permit_rows, centres=None):
    """Una fila por faena que vuela, **incluidas las que no tienen permiso**.

    Parte de las faenas y no de los permisos precisamente para eso: un `GROUP BY`
    sobre permisos sólo devuelve las que tienen alguno, y las que interesan en un
    informe de cumplimiento son las que **no** tienen ninguno. La página 3 del
    informe de agosto lista 12 faenas y 7 sin habilitación; con el recorrido al
    revés esas 7 no existirían.

    ⚠️ LV-378: **los conteos por faena se agregan desde las filas de `permit_rows`**
    y no con una segunda consulta (`permit_status_by_cost_center`), por el mismo
    principio que `collect_kpis`. Eran dos fuentes que leían estados distintos —la
    cobertura el estado de **hoy**, los permisos el reconstruido **al corte**— y por
    eso la fila Total de la sección 3 decía 15 mientras las filas sumaban 14. Con una
    sola fuente, la suma de las filas **es** el total por construcción
    (`invariants.py` lo comprueba igual).
    """
    from apps.compliance.kpis import PERMIT_CRITICAL_DAYS, permit_band

    centres = operating_centres() if centres is None else centres
    by_code = {}
    for row in permit_rows:
        by_code.setdefault(row["cost_centre"], []).append(row)

    rows = []
    for centre in centres:
        own = by_code.get(centre.code, [])
        in_force = [row for row in own if row["in_force"]]
        days = min((row["days_remaining"] for row in in_force), default=None)
        expiries = [row["valid_until"] for row in in_force]
        rows.append(
            {
                "code": centre.code,
                "name": centre.name,
                "permits_in_force": len(in_force),
                "permits_awaiting": sum(
                    1 for row in own if row["status"] == "requested"
                ),
                "permits_lapsed": sum(
                    1
                    for row in own
                    if row["status"] == "approved" and not row["in_force"]
                ),
                "permits_expiring_30d": sum(
                    1
                    for row in in_force
                    if row["days_remaining"] <= PERMIT_CRITICAL_DAYS
                ),
                # R4: el vencimiento que manda es el **primero** de la faena.
                "next_expiry": min(expiries) if expiries else None,
                "days_remaining": days,
                # Una faena sin ningún permiso vigente es `critical` y no "sin
                # banda": no poder volar es la peor situación de la escala, no la
                # ausencia de una. El semáforo de la faena es **el peor** de sus
                # habilitantes, nunca el promedio.
                "band": permit_band(days) if in_force else permit_band(0),
            }
        )
    return rows


#: LV-378: por qué una faena con permiso vivo no está en la cobertura.
OUTSIDE_REASONS = ("closed", "not_flying", "archived")


def outside_reason(centre):
    """El motivo por el que `centre` no entra en `operating_cost_centers`.

    El orden importa sólo para el rótulo: una faena cerrada que además está
    archivada se dice «terminada», que es lo que la persona reconoce.
    """
    from apps.registry.models import CostCenter

    if centre.contract_status == CostCenter.CONTRACT_CLOSED:
        return "closed"
    if not centre.operates_flights:
        return "not_flying"
    return "archived"


def collect_outside_centres(permit_rows):
    """LV-378: las faenas **sin operación** que todavía tienen algún permiso vivo.

    Regla (a'): la cobertura y el «X de N» siguen siendo sólo de las faenas con
    operación —«cerrada es cerrada», decisión del 2026-09-14—, pero un permiso
    vigente de una faena terminada **existe ante la DGAC**: callarlo en un papel
    firmado sería una omisión. Va en un bloque aparte, y se calcula **desde las
    filas de permisos** igual que el resto.

    Entra la faena con cualquier permiso vivo al corte (vigente, en trámite o
    vencido sin cerrar), para que ningún permiso quede huérfano (invariante I5).
    """
    from apps.compliance.kpis import permit_band

    found = {}
    for row in permit_rows:
        if row["in_operation"]:
            continue
        entry = found.setdefault(
            row["cost_centre"],
            {
                "code": row["cost_centre"],
                "name": row["cost_centre_name"],
                "reason": row["outside_reason"],
                "permits_in_force": 0,
                "permits_awaiting": 0,
                "permits_lapsed": 0,
                "next_expiry": None,
                "days_remaining": None,
                "band": None,
                "folios": [],
            },
        )
        if row["in_force"]:
            entry["permits_in_force"] += 1
            entry["folios"].append(row["folio"])
            if (
                entry["days_remaining"] is None
                or row["days_remaining"] < entry["days_remaining"]
            ):
                entry["days_remaining"] = row["days_remaining"]
                entry["next_expiry"] = row["valid_until"]
        elif row["status"] == "requested":
            entry["permits_awaiting"] += 1
        else:
            entry["permits_lapsed"] += 1
    for entry in found.values():
        entry["band"] = permit_band(entry["days_remaining"])
    return [found[code] for code in sorted(found)]


def status_at_cutoff(permits, cutoff):
    """`{pk: estado}` — el estado que cada permiso tenía **al corte**.

    ⚠️ **Lo que esto arregla**, y que el contraste contra el papel emitido dejó a
    la vista: el informe de agosto decía *11 vigentes y 3 en trámite*, y la app
    mostraba *14 vigentes y 0 en trámite*. Los mismos catorce permisos — los tres
    que en agosto esperaban a la DGAC ya fueron aprobados, y la tabla los listaba
    con su estado de hoy bajo un encabezado que dice "al corte".

    Se reconstruye desde `PermissionHistory`, que guarda estado anterior, estado
    nuevo y fecha desde `R2.5`. Tres casos, y el tercero es el que se olvida:

    1. hay movimientos hasta el corte → el `new_status` del último;
    2. hay movimientos, pero **todos posteriores** al corte → el
       `previous_status` del **primero**, que es literalmente lo que el permiso
       era antes de moverse;
    3. no hay ninguno → nunca cambió, así que su estado de hoy **es** el de
       entonces.

    **Una sola consulta para todos los permisos**, y por eso recibe la lista en
    vez de un permiso: catorce consultas sueltas acá se convierten en una por
    fila cuando la operación crezca, y este payload se arma también desde un
    trabajo nocturno donde nadie mira el reloj.
    """
    from apps.operations.models import PermissionHistory

    by_permit = {}
    for entry in PermissionHistory.objects.filter(
        permission__in=[permit.pk for permit in permits]
    ).order_by("permission_id", "sequence"):
        by_permit.setdefault(entry.permission_id, []).append(entry)

    resolved = {}
    for permit in permits:
        entries = by_permit.get(permit.pk, [])
        upto = [e for e in entries if e.created_at.date() <= cutoff]
        if upto:
            resolved[permit.pk] = upto[-1].new_status
        elif entries:
            resolved[permit.pk] = entries[0].previous_status
        else:
            resolved[permit.pk] = permit.status
    return resolved


def collect_permits(cutoff, operating_codes=None):
    """R4: una fila por permiso vivo, como la tabla de la página 3.

    **Vivos son los vigentes y los que esperan a la DGAC**, y van juntos en una
    consulta pero separados en la salida por `in_force`: el informe emitido los
    lista en dos bloques —"vigentes" y "solicitudes en trámite, sin habilitación
    hasta su aprobación"— y mezclarlos sugeriría que un trámite habilita a
    volar. Los caducados no entran: un permiso que terminó no es un permiso
    incumplido, es historia (mismo criterio que `permit_counts`).

    ⚠️ **LV-378: «vivo» es vivo AL CORTE, y el estado de hoy no lo dice.** La
    consulta filtraba por el estado ACTUAL (`requested`, `approved`), así que un
    permiso vigente hasta el 31-10 que `expire_permissions` pasa a `expired` el 1-11
    a las 05:30 **desaparecía** del cierre de las 06:30 aunque estaba vigente al
    corte. `status_at_cutoff` ya sabía reconstruirlo; la consulta lo descartaba
    antes. Ahora entran también los `expired` que **tienen un movimiento posterior
    al corte** (los que vencieron después de él) y la reconstrucción decide: lo que
    no estaba vivo al corte se descarta al final. Sin ese movimiento posterior, un
    caducado antiguo no entra —la historia no crece en cada informe—.

    `operating_codes` son los códigos de las faenas con operación (el mismo
    universo que la cobertura); sin él se leen de la base. Cada fila trae
    `in_operation` y, si no lo está, el nombre y el motivo de su faena.

    ⚠️ **Dos `prefetch_related` y no una consulta por fila.** Cada permiso nombra
    sus operadores y sus aeronaves, así que sin esto son 2N consultas para once
    permisos — y el payload se construye también desde un trabajo nocturno,
    donde nadie mira el reloj.
    """
    from django.db import models

    from apps.compliance.kpis import permit_band
    from apps.operations.models import FlightPermission, PermissionHistory

    if operating_codes is None:
        operating_codes = {centre.code for centre in operating_centres()}

    alive = (FlightPermission.STATUS_REQUESTED, FlightPermission.STATUS_APPROVED)
    moved_after_cutoff = models.Exists(
        PermissionHistory.objects.filter(
            permission=models.OuterRef("pk"), created_at__date__gt=cutoff
        )
    )
    permits = (
        FlightPermission.objects.filter(
            models.Q(status__in=alive)
            | models.Q(moved_after_cutoff, status=FlightPermission.STATUS_EXPIRED)
        )
        # LV-233, tercera parte: **vivo al corte**, no vivo hoy. Un permiso
        # archivado *después* del corte estaba vivo entonces y tiene que
        # aparecer; uno archivado antes, no.
        #
        # Es una omisión lo que se corrige, y por eso valía la columna: un estado
        # equivocado se ve en la fila, y una fila que falta no se ve en ninguna
        # parte.
        #
        # `archived_at` nulo en una fila archivada significa *no se sabe cuándo*
        # —se archivó antes de que existiera la columna— y entonces se la deja
        # fuera, que es lo que esta consulta hacía siempre. La limitación se
        # declara en el pie del informe y se achica sola: cada archivo nuevo trae
        # su fecha.
        .filter(
            models.Q(is_active=True)
            | models.Q(archived_at__isnull=False, archived_at__date__gt=cutoff)
        )
        # ⚠️ **LV-233: al corte, no a hoy.** Hasta acá `cutoff` sólo se usaba para
        # calcular la columna "Días" y **no filtraba nada**, así que la página 3
        # listaba todos los permisos vivos *hoy* bajo un encabezado que dice
        # "SITUACIÓN DE LOS PERMISOS AL CORTE". El usuario lo vio en el informe de
        # agosto: `JEJ-2026-012` y `013`, con vigencia 06-09 → 05-12, aparecían
        # ahí — permisos que el 31 de agosto no existían todavía.
        #
        # Dos condiciones, y son distintas:
        #
        # - `created_at__date <= cutoff`: no estaba en el sistema. Es el mismo
        #   corte de población que `panel_readiness` ya aplica, y arrastra su
        #   misma limitación honesta -- si una ficha se cargó a destiempo, su
        #   `created_at` es la fecha de carga.
        # - `valid_from <= cutoff`: existía, pero **todavía no habilitaba a
        #   volar**. Un permiso aprobado que empieza la semana siguiente al corte
        #   no era una autorización vigente ese día, y decir que sí es una
        #   afirmación falsa ante la DGAC.
        #
        # Un permiso **solicitado** no tiene vigencia (`LV-219`), así que
        # `valid_from` nulo pasa: lo que lo hace pertenecer al corte es haber
        # existido, y su bloque en el informe ya dice que no habilita.
        .filter(created_at__date__lte=cutoff)
        .filter(models.Q(valid_from__isnull=True) | models.Q(valid_from__lte=cutoff))
        .select_related("cost_center")
        .prefetch_related("operators", "aircraft_fleet")
        .order_by("valid_until", "internal_folio")
    )

    permits = list(permits)
    was = status_at_cutoff(permits, cutoff)

    rows = []
    for permit in permits:
        # LV-378: un caducado que entró por haberse movido después del corte sólo
        # se lista si al corte estaba vivo.
        if was[permit.pk] not in alive:
            continue
        approved = was[permit.pk] == FlightPermission.STATUS_APPROVED
        operating = permit.cost_center.code in operating_codes
        # Un permiso solicitado no tiene vigencia (`LV-219`), así que sus días
        # son `None` y no cero: cero afirmaría que vence hoy.
        days = (permit.valid_until - cutoff).days if permit.valid_until else None
        rows.append(
            {
                "folio": permit.internal_folio,
                # El número de la DGAC no existe hasta que la DGAC resuelve.
                "dgac_number": permit.permission_number or None,
                # El estado **al corte**, reconstruido, no el de hoy. Va al
                # payload y no sólo a `in_force` porque los contadores de la
                # página 3 se cuentan sobre estas filas: dos recorridos separados
                # es cómo el encabezado dice "0 en trámite" y la tabla de abajo
                # lista tres.
                "status": was[permit.pk],
                "cost_centre": permit.cost_center.code,
                "operators": [o.full_name for o in permit.operators.all()],
                "aircraft": [a.registration for a in permit.aircraft_fleet.all()],
                "valid_from": permit.valid_from.isoformat()
                if permit.valid_from
                else None,
                "valid_until": (
                    permit.valid_until.isoformat() if permit.valid_until else None
                ),
                "days_remaining": days,
                "band": permit_band(days),
                "in_force": bool(
                    approved and permit.valid_until and permit.valid_until >= cutoff
                ),
                # LV-378: ¿su faena está en la cobertura? Es el criterio que parte
                # lo que mide renovación (sólo con operación) de lo que es un hecho
                # legal (todos los vigentes). Una faena fuera trae su nombre y el
                # motivo, para el bloque «sin operación» (no se pregunta a la base
                # al dibujar: el informe congelado se explica con su payload).
                "in_operation": operating,
                "cost_centre_name": permit.cost_center.name,
                "outside_reason": (
                    None if operating else outside_reason(permit.cost_center)
                ),
            }
        )
    return rows


# LV-235: **el plan de normalización, como dato.**
#
# Textual del usuario mirando la página 5: *"el actual es estático, sólo cambia
# la fecha, lo cual lo vuelve inútil"*. Y era exacto para esta página y sólo para
# ésta: 124 líneas de plantilla con **dos** interpolaciones, y las dos eran la
# firma. Sus cuatro fases llevaban los meses escritos a mano, así que en enero de
# 2027 el informe iba a seguir diciendo *"FASE 0 · Sep 2026 · renovar los
# permisos que vencen"* — un plan vencido impreso como si fuera vigente.
#
# ⚠️ LV-249: acá estaba escrito que las fases **siguen viviendo en el código y no
# en la base**, porque *"una tabla de configuración para cuatro filas que nadie
# edita es una tabla que nadie mantiene"*. Era cierto mientras nadie las editaba.
# El usuario pidió poder modificarlas desde la aplicación, y la constante
# `PLAN_PHASES` —con los meses de 2026 escritos— se mudó a `PlanPhase`, sembrada
# por la migración `0005` con estos mismos cuatro textos. Lo que sigue saliendo de
# acá es **en qué fase se está**, que se calcula contra el período del informe.

MONTH_ABBR = [
    "",
    "Ene",
    "Feb",
    "Mar",
    "Abr",
    "May",
    "Jun",
    "Jul",
    "Ago",
    "Sep",
    "Oct",
    "Nov",
    "Dic",
]


def collect_plan(period):
    """Las fases del plan, cada una sabiendo si ya pasó, es la de ahora, o viene.

    **Es lo que vuelve variable la página 5.** El estado se calcula contra el
    período del informe y no contra hoy, por lo mismo que el corte: reimprimir el
    informe de agosto en diciembre tiene que devolver la página que agosto vio,
    no la de diciembre.

    Viaja en el payload, así que un informe congelado guarda **su** foto del
    plan. Si el plan cambia el año que viene, los informes ya emitidos siguen
    diciendo lo que dijeron — que es la razón de existir de `ReportRun`.

    `concluded` es el caso que el plan escrito a mano no tenía: pasado diciembre
    de 2026 no hay fase vigente, y decirlo es mejor que dejar la primera pintada
    como actual para siempre.
    """
    from apps.reporting.models import ReportTemplate

    template = ReportTemplate.current()
    phases = list(template.active_phases()) if template else []

    key = (period.year, period.month)
    rows = []
    for index, phase in enumerate(phases):
        when = (phase.month.year, phase.month.month)
        if when < key:
            state = "done"
        elif when == key:
            state = "current"
        else:
            state = "pending"
        rows.append(
            {
                "number": index,
                "month": f"{MONTH_ABBR[when[1]]} {when[0]}",
                "title": phase.title,
                "text": phase.text,
                "close": phase.close,
                "state": state,
            }
        )

    # LV-249: **la matriz de exigibilidad, como dato.** Estaba escrita en la
    # plantilla con SEP–DIC a mano. Ahora sus **columnas son las fases** —un mes por
    # fase, en el mismo orden— y cada fila trae su nivel por mes: agregar una fase
    # agrega una columna, y un mes sin nivel se dibuja «No aplica». Viaja en el
    # payload como el resto, así que un informe congelado guarda su matriz.
    matrix = None
    if template and phases:
        matrix = {
            "columns": [MONTH_ABBR[phase.month.month].upper() for phase in phases],
            "rows": [
                {
                    "label": row.label,
                    "emphasis": row.emphasis,
                    "cells": [row.level_for(phase.key) for phase in phases],
                }
                for row in template.active_matrix_rows()
            ],
        }

    first = (phases[0].month.year, phases[0].month.month) if phases else None
    last = (phases[-1].month.year, phases[-1].month.month) if phases else None
    return {
        "phases": rows,
        "lede": template.plan_lede if template else "",
        "matrix": matrix,
        # Ninguna fase es la actual: o el período es anterior al plan, o el plan
        # ya terminó. Las dos se dicen, en vez de fingir una fase vigente. Sin
        # fases no se afirma ninguna de las dos.
        "concluded": bool(last) and key > last,
        "not_started": bool(first) and key < first,
    }


def collect_incidents(cutoff):
    """LV-235: los eventos operacionales del período, uno por fila.

    La plantilla del Dato Ejecutivo pide *"detalle del evento, fecha, CC,
    aeronave y estado del reporte a la DGAC"*, y el informe emitido lo llevaba
    como una frase escrita a mano. **Todo eso ya está en `NonConformity`**
    —incluido el reporte a la DGAC, que `R7.6` guarda como fecha y folio
    justamente porque es la evidencia que pide un auditor— así que la sección se
    calcula en vez de redactarse.

    Sólo `source="incident"`: un re-vuelo o un entregable rechazado son hallazgos
    de calidad, y listarlos acá los presentaría ante la DGAC como eventos
    notificables.

    Por **fecha de detección**, no de creación: un evento del 20 de agosto
    cargado el 2 de septiembre pertenece a agosto, que es de lo que el informe
    habla.
    """
    from apps.compliance.models import NonConformity

    rows = []
    for finding in (
        NonConformity.objects.filter(
            is_active=True,
            source=NonConformity.SOURCE_INCIDENT,
            detected_on__gte=cutoff.replace(day=1),
            detected_on__lte=cutoff,
        )
        .select_related("cost_center")
        .order_by("detected_on")
    ):
        rows.append(
            {
                "title": finding.title,
                "detected_on": finding.detected_on.isoformat(),
                "cost_centre": (
                    finding.cost_center.code if finding.cost_center_id else None
                ),
                "status": finding.status,
                "status_label": finding.get_status_display(),
                # El reporte a la DGAC, que para un evento notificable **es** la
                # evidencia. `None` y no cadena vacía: no reportado y reportado
                # sin folio son dos cosas distintas.
                "reported_to_dgac": (
                    finding.reported_to_dgac_at.isoformat()
                    if finding.reported_to_dgac_at
                    else None
                ),
                "dgac_reference": finding.dgac_report_reference or None,
            }
        )
    return rows


def collect_concentration(permits):
    """R4: cuánto depende la operación de una sola persona.

    El hallazgo del informe emitido: *"8 de los 11 permisos vigentes designan a
    un solo operador. La ausencia o indisponibilidad de esa persona detiene la
    operación de dos Centros de Costo."*

    **La faena depende de una persona cuando la unión de los operadores de todos
    sus permisos vigentes tiene un solo miembro**, y esa definición es la que
    responde al riesgo real: si alguno de sus permisos designa a otra persona,
    la faena sigue pudiendo volar sin la primera. Contar "faenas con algún
    permiso de un solo operador" habría inflado la cifra con faenas que tienen
    suplente.

    Se calcula sobre las filas ya recolectadas y no con otra consulta, por lo
    mismo que `collect_kpis` recibe las faenas: dos recorridos del mismo dato es
    cómo dos páginas del informe empiezan a discrepar.
    """
    in_force = [row for row in permits if row["in_force"]]
    single = [row for row in in_force if len(row["operators"]) == 1]

    by_centre = {}
    for row in in_force:
        by_centre.setdefault(row["cost_centre"], set()).update(row["operators"])
    dependent = sorted(code for code, people in by_centre.items() if len(people) == 1)

    # LV-378: **lo mismo, sólo con las faenas con operación.** El riesgo de «depende
    # de una persona» es de la operación que vuela: una faena terminada con un
    # permiso que se deja vencer inflaba la cifra («8 de 15», «CC716, CC738») y
    # nombraba como dependiente una faena que ya no opera. Las llaves de arriba
    # conservan su significado —los informes emitidos y el comparador dependen de
    # ellas— y las corregidas van en llaves nuevas. `in_operation` falta en las
    # filas de payloads anteriores a LV-378: sin él, todas cuentan.
    operating = [row for row in in_force if row.get("in_operation", True)]
    operating_by_centre = {}
    for row in operating:
        operating_by_centre.setdefault(row["cost_centre"], set()).update(
            row["operators"]
        )

    return {
        "permits_in_force": len(in_force),
        "permits_with_one_operator": len(single),
        "cost_centres_on_one_person": dependent,
        "permits_in_force_operating": len(operating),
        "permits_with_one_operator_operating": sum(
            1 for row in operating if len(row["operators"]) == 1
        ),
        "cost_centres_on_one_person_operating": sorted(
            code for code, people in operating_by_centre.items() if len(people) == 1
        ),
    }


def collect_changes(period, cutoff, cost_centres, permits):
    """LV-378: qué cambió desde el último informe del mes anterior, **congelado**.

    Lo comparable ya existe y está probado (`compare_permits`): se reutiliza **acá,
    al construir**, y el resultado viaja en el payload. No se calcula al dibujar:
    un informe congelado tiene que decir lo mismo el día que se reabra, y
    recomparar contra un informe que entre tanto se reemplazó cambiaría la hoja.

    Se compara contra la revisión más alta del mes anterior (la que quedó
    vigente), no contra la revisión previa del mismo mes. Sin informe del mes
    anterior devuelve `None`, no una comparación vacía: «sin cambios» y «no hay
    contra qué comparar» son afirmaciones distintas.
    """
    from apps.reporting.compare import compare_permits
    from apps.reporting.models import ReportRun

    previous_period = (period.replace(day=1) - timedelta(days=1)).replace(day=1)
    previous = (
        ReportRun.objects.filter(period=previous_period).order_by("-revision").first()
    )
    if previous is None:
        return None

    before = previous.payload or {}
    now = {"permits": permits}
    changed = compare_permits(before, now)

    def without_permit(rows):
        return {row["code"] for row in rows if not row.get("permits_in_force")}

    was = without_permit(before.get("cost_centres") or [])
    now_without = without_permit(cost_centres)

    def figure(payload, key):
        leaf = (payload.get("kpis") or {}).get(key)
        return leaf.get("value") if isinstance(leaf, dict) else None

    now_kpis = {
        "permits_in_force": sum(1 for row in permits if row["in_force"]),
        "permits_awaiting": sum(1 for row in permits if row["status"] == "requested"),
        "cost_centres_without_permit": len(now_without),
    }
    return {
        "against": {
            "period": f"{previous.period:%Y-%m}",
            "revision": previous.revision,
            "cutoff": (before.get("meta") or {}).get("cutoff"),
            "layout": (before.get("meta") or {}).get("layout", 1),
        },
        "in_force": changed["in_force"],
        "awaiting": changed["awaiting"],
        "without_permit": {
            "added": sorted(now_without - was),
            "removed": sorted(was - now_without),
        },
        "kpis": {
            key: {"before": figure(before, key), "after": value}
            for key, value in now_kpis.items()
        },
    }


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


def build(period, cutoff=None, early=False, early_reason=""):
    """El payload del período, listo para congelar en un `ReportRun`.

    `cutoff` por defecto es el último día del mes: un informe mensual describe el
    mes cerrado, y usar "hoy" haría que el mismo período diera cifras distintas
    según cuándo se generara — que es justo lo que congelar el dato viene a
    evitar.

    ⚠️ **Salvo que el mes todavía no haya terminado, y ahí el corte es hoy.**
    `LV-233`: el usuario lo vio en pantalla el 2026-09-03 — la portada de
    septiembre, abierta el día 3, declaraba *"FECHA DE CORTE 30-09-2026"*, una
    fecha que no había ocurrido, sobre datos que eran los de ese día. En un
    informe cuya regla es que **nunca inventa un dato**, una fecha de corte
    futura es exactamente eso.

    Y no es cosmético: el mismo defecto explica el 41 contra 42 del padrón de
    agosto (`LV-234`). El informe emitido se hizo antes del 26 de agosto y decía
    "corte al 31-08", afirmando cinco días que no había mirado.

    `min` y no un `if` sobre el mes en curso, porque cubre de una vez el caso que
    importa y el que nadie piensa: pedir el informe de un mes **futuro**, donde
    "hoy" también es la única fecha honesta.
    """
    from django.utils import timezone

    _start, end = month_bounds(period)
    cutoff = cutoff or min(end, timezone.localdate())
    centres = operating_centres()
    permits = collect_permits(cutoff, {centre.code for centre in centres})
    cost_centres = collect_cost_centres(cutoff, permits, centres)
    payload = {
        "meta": collect_meta(period, cutoff, early, early_reason),
        "kpis": collect_kpis(cutoff, cost_centres, permits),
        "cost_centres": cost_centres,
        # LV-378: las faenas sin operación que conservan un permiso vivo, aparte de
        # la cobertura (regla a').
        "outside_centres": collect_outside_centres(permits),
        "permits": permits,
        "concentration": collect_concentration(permits),
        # LV-378: lo que cambió desde el informe anterior, congelado con el resto.
        "changes": collect_changes(period, cutoff, cost_centres, permits),
        # LV-235: el detalle de los eventos del período, para la sección que la
        # plantilla del Dato Ejecutivo pedía escribir a mano.
        "incidents": collect_incidents(cutoff),
        # LV-235: el plan de la página 5, con la fase que corresponde al período.
        # Contra el **período** y no contra hoy: reimprimir agosto en diciembre
        # tiene que devolver la página que agosto vio.
        "plan": collect_plan(period),
    }
    return payload, find_missing(payload)
