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
        # LV-233: que el período siga abierto es un hecho **del documento**, así
        # que viaja en el payload congelado y no se recalcula al dibujar. Un
        # informe que se congeló a mitad de mes tiene que seguir diciendo que se
        # congeló a mitad de mes, aunque se lea en diciembre.
        "in_progress": cutoff < end,
        "days_remaining": max((end - cutoff).days, 0),
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
    from apps.registry.models import CostCenter

    # El primer día del mes al que pertenece el corte: los incidentes se cuentan
    # **del período**, no acumulados, y sin esto un informe de agosto sumaría los
    # de todo el año.
    period_start = cutoff.replace(day=1)

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


def collect_cost_centres(cutoff):
    """Una fila por faena que vuela, **incluidas las que no tienen permiso**.

    Se apoya en `permit_status_by_cost_center` (`LV-206`), que ya parte de las
    faenas y no de los permisos precisamente para eso: un `GROUP BY` sobre
    permisos sólo devuelve las que tienen alguno, y las que interesan en un
    informe de cumplimiento son las que **no** tienen ninguno. La página 3 del
    informe de agosto lista 12 faenas y 7 sin habilitación; con el recorrido al
    revés esas 7 no existirían.
    """
    from apps.compliance.kpis import permit_band, permit_status_by_cost_center

    return [
        {
            # La fila trae el objeto `cost_center`, no sus campos sueltos.
            "code": row["cost_center"].code,
            "name": row["cost_center"].name,
            "permits_in_force": row["in_force"],
            "permits_awaiting": row["awaiting"],
            "permits_lapsed": row["lapsed"],
            "permits_expiring_30d": row["soon"],
            # R4: el vencimiento que manda es el **primero** de la faena.
            "next_expiry": (
                row["next_expiry"].isoformat() if row["next_expiry"] else None
            ),
            "days_remaining": row["days_remaining"],
            # Una faena sin ningún permiso vigente es `critical` y no "sin
            # banda": no poder volar es la peor situación de la escala, no la
            # ausencia de una. Es el §4.2 del SPEC —el semáforo de la faena es
            # **el peor** de sus habilitantes, nunca el promedio— aplicado al
            # único habilitante que el informe cuenta hoy.
            "band": (
                permit_band(row["days_remaining"])
                if row["in_force"]
                else permit_band(0)
            ),
        }
        for row in permit_status_by_cost_center(cutoff)
    ]


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


def collect_permits(cutoff):
    """R4: una fila por permiso vivo, como la tabla de la página 3.

    **Vivos son los vigentes y los que esperan a la DGAC**, y van juntos en una
    consulta pero separados en la salida por `in_force`: el informe emitido los
    lista en dos bloques —"vigentes" y "solicitudes en trámite, sin habilitación
    hasta su aprobación"— y mezclarlos sugeriría que un trámite habilita a
    volar. Los caducados no entran: un permiso que terminó no es un permiso
    incumplido, es historia (mismo criterio que `permit_counts`).

    ⚠️ **Dos `prefetch_related` y no una consulta por fila.** Cada permiso nombra
    sus operadores y sus aeronaves, así que sin esto son 2N consultas para once
    permisos — y el payload se construye también desde un trabajo nocturno,
    donde nadie mira el reloj.
    """
    from django.db import models

    from apps.compliance.kpis import permit_band
    from apps.operations.models import FlightPermission

    permits = (
        FlightPermission.objects.filter(
            status__in=(
                FlightPermission.STATUS_REQUESTED,
                FlightPermission.STATUS_APPROVED,
            ),
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
        approved = was[permit.pk] == FlightPermission.STATUS_APPROVED
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
                "in_force": approved
                and permit.valid_until
                and permit.valid_until >= cutoff,
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
# Las fases **siguen viviendo en el código y no en la base**, y eso es
# deliberado: son un compromiso de gestión que cambia una vez al año, no un dato
# de operación. Una tabla de configuración para cuatro filas que nadie edita es
# una tabla que nadie mantiene, el mismo criterio con el que `KpiTarget` no se
# creó. Lo que se saca de la plantilla es **en qué fase se está**, que sí cambia
# cada mes.
PLAN_PHASES = [
    (
        (2026, 9),
        "Cierre de brechas de habilitación",
        "Renovar los permisos que vencen dentro del período. Definir cuáles de "
        "los Centros de Costo sin permiso tendrán operación aérea y tramitar su "
        "carta del mandante y su solicitud en SIGO.",
        "ningún CC con operación prevista opera sin permiso vigente.",
    ),
    (
        (2026, 10),
        "Calendario de renovación automático",
        "AeroControl calcula el vencimiento sobre la fecha real de cada "
        "resolución —no sobre un plazo supuesto— y dispara alertas a 45 y 30 "
        "días: a los 45 el ADC solicita la carta del mandante; a los 30 el Jefe "
        "Seguridad Aérea presenta en SIGO y, sin carta, escala al Gerente "
        "Operaciones Aéreas.",
        "ninguna renovación depende de que alguien la recuerde.",
    ),
    (
        (2026, 11),
        "Bitácora digital de vuelo",
        "Se habilita el registro por vuelo: bitácora (JEJ-GTE-CT-REG-015), "
        "check list pre-vuelo (LVE-003) e inspección (LVE-002). Cada vuelo se "
        "asocia al permiso que lo autoriza, de modo que el sistema no admita "
        "registrar un vuelo sin permiso vigente en esa fecha.",
        "completitud reportada como línea base, sin sanción interna.",
    ),
    (
        (2026, 12),
        "Exigibilidad plena y auditoría",
        "La completitud de bitácoras pasa a indicador exigible por Centro de "
        "Costo y se contrasta la coherencia entre vuelos ejecutados y vuelos "
        "autorizados. Auditoría interna regulatoria conforme al numeral 5.4.2 "
        "del INS-096.",
        "informe anual consolidado y plan de acción 2027.",
    ),
]

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
    key = (period.year, period.month)
    rows = []
    for index, (when, title, text, close) in enumerate(PLAN_PHASES):
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
                "title": title,
                "text": text,
                "close": close,
                "state": state,
            }
        )
    return {
        "phases": rows,
        # Ninguna fase es la actual: o el período es anterior al plan, o el plan
        # ya terminó. Las dos se dicen, en vez de fingir una fase vigente.
        "concluded": key > PLAN_PHASES[-1][0],
        "not_started": key < PLAN_PHASES[0][0],
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

    return {
        "permits_in_force": len(in_force),
        "permits_with_one_operator": len(single),
        "cost_centres_on_one_person": dependent,
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


def build(period, cutoff=None):
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
    cost_centres = collect_cost_centres(cutoff)
    permits = collect_permits(cutoff)
    payload = {
        "meta": collect_meta(period, cutoff),
        "kpis": collect_kpis(cutoff, cost_centres, permits),
        "cost_centres": cost_centres,
        "permits": permits,
        "concentration": collect_concentration(permits),
        # LV-235: el detalle de los eventos del período, para la sección que la
        # plantilla del Dato Ejecutivo pedía escribir a mano.
        "incidents": collect_incidents(cutoff),
        # LV-235: el plan de la página 5, con la fase que corresponde al período.
        # Contra el **período** y no contra hoy: reimprimir agosto en diciembre
        # tiene que devolver la página que agosto vio.
        "plan": collect_plan(period),
    }
    return payload, find_missing(payload)
