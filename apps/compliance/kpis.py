"""R7.7: the five operational KPIs the audit guide asks for (ISO 9001 9.1.1).

Two of them (fleet availability, on-time execution) were derivable from what
the operation already recorded. The other three -- precision achieved vs.
required, reflight rate, incident-free flight hours -- waited on `Deliverable`
(R7.4) and `NonConformity` (R7.6); both landed on 2026-08-12, so the list is
now complete. See docs/dev/iso-r7-design-plan.md, "De qué dependen los KPI
operacionales".

9.1.1 asks for a **target**, a **trend** and **action when it is missed**. This
module provides the value and the comparison against the target; the trend for
document KPIs comes from `ComplianceSnapshot` (R7.7's first half, already
built). Targets live here as documented constants rather than in the
`KpiTarget` model the design sketches: one number is a constant, and a
configuration table with a single row in it is a table nobody maintains. When a
second target with a different owner appears, that is when the model earns its
place.

Two things every reader of this module has to keep straight, and which are
therefore declared per KPI rather than inferred: **which direction is good**
(the reflight rate is the only one where lower wins) and **what the figure is**
(all percentages except the incident-free counter, which is a duration).
"""

from datetime import timedelta

from django.utils.translation import gettext_lazy as _

# Decided with the user on 2026-08-12. Tolerates roughly one aircraft of a
# ~16-strong fleet being out at any moment.
FLEET_AVAILABILITY_TARGET = 90.0

# No target set yet: the value and its trend are shown, and nothing is flagged
# as a miss. A target invented here would be a threshold nobody agreed to, and
# 9.1.1 wants action on a missed target -- action on an arbitrary line is how a
# KPI turns into noise people learn to ignore. Same for the rest below.
ON_TIME_EXECUTION_TARGET = None
SURVEY_ACCURACY_TARGET = None
REFLIGHT_RATE_TARGET = None

# Which way is good. Every KPI here is "higher is better" except the reflight
# rate, and leaving that to be inferred from the name is how a red badge ends
# up on the best month of the year.
HIGHER_IS_BETTER = "higher"
LOWER_IS_BETTER = "lower"

# How to render the figure. Most are percentages; the incident-free counter is
# an accumulated duration, which has no target and no "out of" denominator.
UNIT_PERCENT = "percent"
UNIT_DURATION = "duration"


# R4: la escala del **permiso**, que no es la del documento y por eso vive acá.
#
# `digest.bucket_for` corta en 7/15/30 y llama "later" a todo lo que pase de un
# mes. Para un permiso eso es tarde: su renovación exige **una carta nueva del
# mandante** y el trámite ante la DGAC, que es por lo que la cadena de `LV-226`
# empieza a avisar a **45** días. El informe emitido dibuja su leyenda en 30/60
# — crítico, por vencer, vigente — y ésa es la escala del documento.
#
# ⚠️ **No es una tercera paleta**, que era el riesgo anotado en el plan: los
# nombres son los mismos cinco niveles de severidad que `UX-01` fijó, y de ellos
# se usan tres. Lo que cambia es el **corte**, no el vocabulario — así el rojo
# significa lo mismo en la bandeja, en el panel y en el informe. El color de
# papel lo pone `report-a4.css`, porque un documento firmado no puede depender
# del tema de quien lo abrió.
PERMIT_CRITICAL_DAYS = 30
PERMIT_WARNING_DAYS = 60
PERMIT_BAND_CRITICAL = "critical"
PERMIT_BAND_WARNING = "warning"
PERMIT_BAND_NOMINAL = "nominal"


def permit_band(days_left):
    """El tramo de un permiso según los días que le quedan.

    `None` cuando no hay días que contar —un permiso **solicitado** no tiene
    vigencia (`LV-219`)— y eso no es lo mismo que "vencido": la DGAC todavía no
    resolvió. Devolver `critical` ahí pintaría de rojo una espera que no es
    incumplimiento de nadie.

    Un permiso ya vencido cae en `critical` junto con los de menos de 30 días, y
    es deliberado: los dos piden la misma acción —renovar ya— y el informe
    distingue el caso vencido por su cifra en negativo, no por un cuarto color.
    """
    if days_left is None:
        return None
    if days_left <= PERMIT_CRITICAL_DAYS:
        return PERMIT_BAND_CRITICAL
    if days_left <= PERMIT_WARNING_DAYS:
        return PERMIT_BAND_WARNING
    return PERMIT_BAND_NOMINAL


def _met(value, target, direction):
    """None when there is nothing to judge -- no value, or no agreed target."""
    if value is None or target is None:
        return None
    return value <= target if direction == LOWER_IS_BETTER else value >= target


def fleet_availability():
    """Percentage of the fleet that is flyable right now.

    `Aircraft.status` is the condition axis (OPS-3 separated it from
    `current_location`): "active" is flyable, "damaged" and "maintenance" are
    not. **"retired" is excluded from the denominator entirely** -- a
    decommissioned aircraft is not unavailable, it left the fleet, and counting
    it would make the number sag permanently for a good decision.
    """
    from apps.registry.models import Aircraft

    fleet = Aircraft.objects.filter(is_active=True).exclude(status="retired")
    total = fleet.count()
    if not total:
        return {
            "total": 0,
            "available": 0,
            "pct": None,
            "target": FLEET_AVAILABILITY_TARGET,
        }
    available = fleet.filter(status="active").count()
    return {
        "total": total,
        "available": available,
        "pct": round(available * 100 / total, 1),
        "target": FLEET_AVAILABILITY_TARGET,
    }


def permit_counts(today, cost_center=None):
    """LV-201: cuántos permisos hay vigentes, atrasados y esperando a la DGAC.

    Pedido del usuario: *"es importante mencionar tanto en los reportes como en el
    dashboard la cantidad de permisos vigentes, atrasados, o el indicador en
    general"*. Las dos palabras del pedido —reportes **y** dashboard— son la razón
    de que esto viva acá y no en `dashboard/views.py`: **una sola función para los
    dos lectores**, o el gerente lee una cifra en el PDF y la pantalla le muestra
    otra. Es la misma regla que `documents_for_cost_center` acaba de aprender a la
    mala en `LV-188`, cuando dos mitades del mismo cálculo se separaron.

    **El denominador son los permisos vivos** (`requested` + `approved`) y no
    todos los que existen. Con la historia acumulada, incluir los caducados haría
    caer el porcentaje para siempre: es el mismo error que `fleet_availability`
    evita excluyendo `retired`, y por la misma razón — un permiso que caducó no es
    un permiso incumplido, terminó.

    Los dos faltantes van **separados** porque se arreglan distinto, que es la
    lección de `LV-129`: `awaiting` espera a la DGAC y no hay nada más que hacer;
    `lapsed` es un permiso aprobado cuya vigencia ya pasó y que nadie cerró, y ése
    sí es trabajo. `lapsed` normalmente vale cero porque `expire_permissions`
    (`LV-83`) los cierra cada noche — y justamente por eso vale mirarlo: un número
    ahí significa que ese trabajo nocturno no corrió.
    """
    from apps.operations.models import FlightPermission

    permits = FlightPermission.objects.filter(
        is_active=True,
        status__in=(
            FlightPermission.STATUS_REQUESTED,
            FlightPermission.STATUS_APPROVED,
        ),
    )
    if cost_center:
        permits = permits.filter(cost_center=cost_center)
    approved = permits.filter(status=FlightPermission.STATUS_APPROVED)
    total = permits.count()
    # Se mira `valid_until` y no `valid_from`, igual que el resto de la app: lo
    # que vence es la autorización, y un permiso aprobado que empieza la semana
    # que viene ya está autorizado — no es trabajo pendiente de nadie.
    #
    # ⚠️ **LV-233 corrigió esto: ahora se miran las dos puntas.** Lo de arriba
    # sigue siendo cierto para el panel —un permiso que empieza la semana que
    # viene ya está autorizado, no es trabajo pendiente— pero **"vigente" no es
    # eso**: es estar en vigor. La diferencia no se nota mirando hoy y se vuelve
    # una afirmación falsa mirando una fecha de corte pasada, que es lo que el
    # informe hace: `JEJ-2026-012` y `013`, con vigencia 06-09 → 05-12, se
    # contaban como vigentes en el informe de **agosto**.
    #
    # Y esta función es **una sola para los dos lectores** a propósito, así que
    # no se podía arreglar el informe sin tocar el panel. Se corrige la
    # definición, y lo que antes se sumaba a "vigentes" no se pierde: pasa a
    # `not_started`, dicho por lo que es. Un número en la casilla equivocada es
    # peor que un número menos.
    in_force = approved.filter(valid_from__lte=today, valid_until__gte=today).count()
    # LV-241: **lo que venció y sigue sin renovarse, dentro del mes en curso.**
    #
    # Pedido del usuario mirando el panel: *"debe contabilizar y marcar y dar el
    # seguimiento completo sobre todo lo que hoy está vencido, por lo cual no debe
    # marcar vigente, indicar vencimiento claro en lo que se lleva al mes"*.
    #
    # ⚠️ **Y lo que fallaba no era un rótulo: era que el vencido no se podía
    # contar.** `lapsed` mira los **aprobados** con fecha pasada, y
    # `expire_permissions` (`LV-83`) los pasa a `expired` cada noche — o sea que un
    # permiso vencido salía del conjunto antes de que nadie lo viera. El propio
    # docstring de esta función lo tenía escrito sin sacar la conclusión:
    # *"`lapsed` normalmente vale cero porque `expire_permissions` los cierra cada
    # noche"*. Un contador que en régimen normal vale cero **no está midiendo el
    # vencimiento**, está midiendo si corrió el cron.
    #
    # Los dos siguen existiendo y por separado, porque son dos hechos distintos:
    # `lapsed` es la anomalía (nadie lo cerró) y `expired_this_month` es el
    # trabajo (venció y hay que renovarlo).
    #
    # **La ventana es el mes en curso, elegida por el usuario**: es el período en
    # que esto se rinde, y uno que se renovó en julio deja de pesar en septiembre.
    # Sin ventana, la columna acumularía historia hasta volverse una lista que
    # nadie termina de cerrar.
    #
    # 🔶 **No entra en el denominador, y es decisión del usuario**: `total` sigue
    # siendo los permisos vivos, así que el porcentaje mide lo mismo que ayer y el
    # informe ya emitido no se mueve. Lo vencido se ve al lado, no dentro.
    expired_this_month = FlightPermission.objects.filter(
        is_active=True,
        status=FlightPermission.STATUS_EXPIRED,
        valid_until__gte=today.replace(day=1),
        valid_until__lt=today,
    )
    if cost_center:
        expired_this_month = expired_this_month.filter(cost_center=cost_center)
    return {
        "total": total,
        "in_force": in_force,
        "expired_this_month": expired_this_month.count(),
        # Aprobados que todavía no empiezan. Existen y habilitan, pero no hoy.
        "not_started": approved.filter(valid_from__gt=today).count(),
        "pct": round(in_force * 100 / total, 1) if total else None,
        "lapsed": approved.filter(valid_until__lt=today).count(),
        "awaiting": permits.filter(status=FlightPermission.STATUS_REQUESTED).count(),
        "soon": approved.filter(
            valid_until__gte=today, valid_until__lte=today + timedelta(days=30)
        ).count(),
        # R4: la ventana de **60 días**, que es la que cuenta el informe emitido
        # ("4 permisos por vencer en 60 días, uno de ellos en 17"). Va como clave
        # aparte y no reemplaza a `soon`: el panel pregunta "qué se me viene este
        # mes" y el informe pregunta "qué hay que empezar a tramitar", y son dos
        # preguntas con dos horizontes. Reemplazar `soon` por 60 habría movido el
        # número del panel sin que nadie lo pidiera.
        "soon_60": approved.filter(
            valid_until__gte=today,
            valid_until__lte=today + timedelta(days=PERMIT_WARNING_DAYS),
        ).count(),
    }


def permit_status_by_cost_center(today):
    """LV-206: una fila por faena, con sus permisos vigentes — y las que no tienen.

    Pedido del usuario: *"necesito una opción de poner los CC que hoy tienen y los
    que no tienen permisos vigentes […] una tabla interactiva"*.

    **Se parte de las faenas y no de los permisos**, y eso es el punto: un `GROUP
    BY` sobre permisos sólo devuelve las faenas que tienen alguno, y las que
    interesan son justamente **las que no tienen ninguno**. Con el recorrido al
    revés, esas filas no existirían y la tabla contestaría lo contrario de la
    pregunta.

    **Sólo las que vuelan** (`operates_flights`): `CC110` y `CC410` administran
    equipos, así que listarlas como "sin permisos vigentes" las declararía
    incumplidas por una operación que no les toca. Ver el comentario del campo en
    `CostCenter`.

    ⚠️ **Y sólo las que siguen contratadas.** Una faena con `contract_status`
    cerrado está en la **misma** situación que `CC110`: ya no opera, así que
    contarla entre las que no tienen permiso vigente la declara incumplida por
    algo que dejó de tocarle. El usuario lo vio en el panel el 2026-09-14 — siete
    faenas cerradas ocupando la tabla con "Ninguno".

    No es sólo ruido de pantalla: estas filas son el denominador del indicador
    *"X de N Centros de Costo cuentan con permiso de vuelo vigente"* que va
    **firmado a la DGAC**, así que cada faena cerrada empeoraba una cifra de
    cumplimiento por una operación terminada.

    **Cerrada es cerrada, tenga permisos o no** — decisión del usuario, y es la
    regla simple: *"independiente que tenga permiso o no, si está cerrado no
    cuenta"*. La alternativa que se propuso —dejar visible la faena cerrada que
    conserva un permiso vivo, por ser una contradicción que alguien debería
    cerrar— se descartó a propósito. 🔶 Lo que se pierde con eso: ese permiso ya
    no se ve **en esta tabla**. Sigue estando en la lista de permisos y en los
    vencimientos del panel, que es donde se trabaja un permiso de todas formas.

    🔶 **Y esto no se reconstruye al corte**, como sí pasa con la población y el
    estado de los permisos (`LV-233`): `contract_status` no guarda **cuándo** se
    cerró, igual que `is_active`. Así que un informe todavía no congelado de un
    mes en que la faena sí operaba la deja fuera. Los ya congelados no cambian —
    guardan su payload— y ése es justamente el motivo de que lo hagan.

    **Dos consultas, no una por faena.** La primera trae las faenas; la segunda
    agrega los permisos de todas de un golpe. Recorrer `permit_counts` por faena
    habría costado cuatro consultas por fila en una pantalla que se abre en cada
    inicio de sesión — el mismo cuidado que `upcoming_expirations` documenta.
    """
    from django.db.models import Count, Min, Q

    from apps.operations.models import FlightPermission
    from apps.registry.models import CostCenter

    horizon = today + timedelta(days=30)
    centers = list(
        CostCenter.objects.filter(is_active=True, operates_flights=True)
        .exclude(contract_status=CostCenter.CONTRACT_CLOSED)
        .order_by("code")
    )
    counted = {
        row["cost_center"]: row
        for row in FlightPermission.objects.filter(
            is_active=True,
            status__in=(
                FlightPermission.STATUS_REQUESTED,
                FlightPermission.STATUS_APPROVED,
                # LV-241: los caducados entran **al conjunto**, no a las cuentas de
                # vigencia. Cada agregado de abajo filtra por su propio estado, así
                # que sumarlos acá no mueve `in_force`, `awaiting`, `soon` ni
                # `next_expiry`: lo único que cambia es que una faena cuyo único
                # permiso venció deja de desaparecer de la tabla. Era el caso que
                # el usuario vio en `CC684` — dos documentos atrasados en la lista
                # de vencimientos y la fila entera en guiones.
                FlightPermission.STATUS_EXPIRED,
            ),
        )
        .values("cost_center")
        .annotate(
            # LV-258: **vigente es haber empezado y no haber terminado.** Este
            # filtro sólo miraba el final, así que un permiso aprobado que arranca
            # la semana próxima contaba como vigente hoy — y una faena cuyo único
            # permiso todavía no empieza salía **con** permiso, fuera de la tarjeta
            # «Faenas sin permiso» del panel y del indicador firmado. `permit_counts`
            # ya los separaba como `not_started` desde `LV-233`; se detectó porque
            # la hoja 3 del informe decía 12 en la fila y 11 en el total.
            in_force=Count(
                "pk",
                filter=Q(
                    status=FlightPermission.STATUS_APPROVED,
                    valid_from__lte=today,
                    valid_until__gte=today,
                ),
            ),
            not_started=Count(
                "pk",
                filter=Q(status=FlightPermission.STATUS_APPROVED, valid_from__gt=today),
            ),
            # LV-241: **la columna de vigencia pasada era estructuralmente cero.**
            # Contaba sólo los `approved` con fecha pasada, y el trabajo nocturno
            # los mueve a `expired` cada noche: el permiso vencido salía del
            # conjunto antes de poder contarse, así que la faena se veía limpia. Se
            # cuentan los dos hechos, y siguen separados porque se arreglan
            # distinto: un `approved` vencido es una anomalía —nadie lo cerró, y
            # eso se ve cualquiera sea su fecha—, mientras que un `expired` del mes
            # en curso es el trabajo de renovarlo.
            lapsed=Count(
                "pk",
                filter=Q(
                    status=FlightPermission.STATUS_APPROVED, valid_until__lt=today
                ),
            ),
            expired_this_month=Count(
                "pk",
                filter=Q(
                    status=FlightPermission.STATUS_EXPIRED,
                    valid_until__gte=today.replace(day=1),
                    valid_until__lt=today,
                ),
            ),
            awaiting=Count("pk", filter=Q(status=FlightPermission.STATUS_REQUESTED)),
            soon=Count(
                "pk",
                filter=Q(
                    status=FlightPermission.STATUS_APPROVED,
                    valid_from__lte=today,
                    valid_until__gte=today,
                    valid_until__lte=horizon,
                ),
            ),
            # R4: la fecha del **primer** permiso que vence, que es la que manda
            # la renovación. Se agrega acá y no en una segunda consulta por
            # faena: esta pantalla se abre en cada inicio de sesión, y una
            # consulta por fila es lo que el docstring de arriba documenta
            # evitar.
            #
            # `Min` y no `Max`: con siete permisos vigentes el que obliga a
            # actuar es el primero en caer. `Max` habría mostrado la fecha más
            # cómoda y escondido justamente la urgente.
            next_expiry=Min(
                "valid_until",
                filter=Q(
                    status=FlightPermission.STATUS_APPROVED,
                    valid_from__lte=today,
                    valid_until__gte=today,
                ),
            ),
        )
    }
    empty = {
        "in_force": 0,
        "not_started": 0,
        "lapsed": 0,
        "expired_this_month": 0,
        "awaiting": 0,
        "soon": 0,
    }
    rows = []
    for center in centers:
        counts = counted.get(center.pk, empty)
        # `None` cuando la faena no tiene ningún permiso vigente, y se propaga
        # como `None` hasta la plantilla: "sin fecha" no es "vence hoy".
        next_expiry = counts.get("next_expiry")
        rows.append(
            {
                "cost_center": center,
                **{key: counts.get(key, 0) for key in empty},
                "next_expiry": next_expiry,
                "days_remaining": (next_expiry - today).days if next_expiry else None,
            }
        )
    return rows


def on_time_execution(start, end):
    """Percentage of committed work that was flown inside its own window.

    Measured over the **approved permits whose validity ended within the
    period**, asking whether each one has at least one flight recorded against
    it. A permit that expired with nothing flown is committed work that did not
    happen on time; that is the failure this KPI is for.

    Deliberately *not* "flights outside the permit's date range": the flight
    form already refuses those (`FlightRecordForm.clean`), so that reading is
    ~100% by construction, and a KPI whose value cannot move is not a KPI --
    the same trap R6.4 documented for the document counters.

    Only permits already past their window are counted: one still open has not
    failed anything yet, and including it would score the period lower the
    earlier you look at it.

    **`expired` belongs in this filter (LV-83), and leaving it out would have
    been a silent regression**: the daily job now moves a lapsed permit out of
    `approved`, so without this line the KPI would quietly stop counting the
    permits that ran out with nothing flown -- its own failures -- and drift up
    towards a meaningless 100%.
    """
    from apps.operations.models import FlightPermission

    permits = FlightPermission.objects.filter(
        is_active=True,
        status__in=(
            FlightPermission.STATUS_APPROVED,
            FlightPermission.STATUS_COMPLETED,
            FlightPermission.STATUS_EXPIRED,
        ),
        valid_until__gte=start,
        valid_until__lte=end,
    )
    total = permits.count()
    if not total:
        return {
            "total": 0,
            "on_time": 0,
            "pct": None,
            "target": ON_TIME_EXECUTION_TARGET,
        }
    on_time = permits.filter(records__is_active=True).distinct().count()
    return {
        "total": total,
        "on_time": on_time,
        "pct": round(on_time * 100 / total, 1),
        "target": ON_TIME_EXECUTION_TARGET,
    }


def survey_accuracy(start, end):
    """Share of assessed deliverables that met the contract's criteria.

    This is the guide's "precision achieved vs. required", aggregated. Only
    deliverables that could actually be judged count: one whose contract set no
    thresholds is not a pass and not a failure, and folding it into either
    direction would make the number describe how many contracts have criteria
    rather than how good the work was.
    """
    from apps.compliance.models import Deliverable

    assessed, met = 0, 0
    candidates = Deliverable.objects.filter(
        is_active=True,
        validated_at__date__gte=start,
        validated_at__date__lte=end,
    ).select_related("cost_center")
    for deliverable in candidates:
        verdict = deliverable.meets_acceptance_criteria
        if verdict is None:
            continue
        assessed += 1
        met += 1 if verdict else 0
    if not assessed:
        return {"total": 0, "met": 0, "pct": None}
    return {"total": assessed, "met": met, "pct": round(met * 100 / assessed, 1)}


def reflight_rate(start, end):
    """Reflights as a share of the flights actually flown in the period.

    Denominator is flights, not deliverables: a reflight is a flight that had
    to be repeated, so "out of how many flights" is the question it answers.
    **Lower is better here**, unlike every other KPI in this module -- which is
    why `operational_kpis` marks its direction explicitly instead of leaving
    the reader to infer it from the name.
    """
    from apps.compliance.models import NonConformity
    from apps.operations.models import FlightRecord

    flights = FlightRecord.objects.filter(
        is_active=True, actual_date__gte=start, actual_date__lte=end
    ).count()
    reflights = NonConformity.objects.filter(
        is_active=True,
        source=NonConformity.SOURCE_REFLIGHT,
        detected_on__gte=start,
        detected_on__lte=end,
    ).count()
    if not flights:
        return {"flights": 0, "reflights": reflights, "pct": None}
    return {
        "flights": flights,
        "reflights": reflights,
        "pct": round(reflights * 100 / flights, 1),
    }


def incident_free_flight_hours():
    """Flight hours accumulated since the last recorded incident.

    A running counter, not a percentage -- the "N days without an accident"
    shape, which is how this figure is read in practice. Counts from the day
    after the incident was detected, and over the whole history when there has
    never been one, which is the honest reading of "no incidents so far".
    """
    from apps.compliance.models import NonConformity
    from apps.operations.models import FlightRecord
    from apps.operations.selectors import format_duration

    last_incident = (
        NonConformity.objects.filter(
            is_active=True, source=NonConformity.SOURCE_INCIDENT
        )
        .order_by("-detected_on")
        .first()
    )
    records = FlightRecord.objects.filter(is_active=True)
    if last_incident is not None:
        records = records.filter(actual_date__gt=last_incident.detected_on)
    total = sum((record.duration for record in records), timedelta())
    return {
        "since": last_incident.detected_on if last_incident else None,
        "hours": round(total.total_seconds() / 3600, 1),
        "display": format_duration(total),
    }


def operational_kpis(start, end):
    """Both KPIs, shaped for the report template and the executive email.

    `pct is None` means "nothing to measure in this period" -- an empty fleet,
    or no permit whose window closed. Rendered as "—", never as 0%: zero would
    read as total failure where the honest answer is that the question does not
    apply.
    """
    availability = fleet_availability()
    execution = on_time_execution(start, end)
    accuracy = survey_accuracy(start, end)
    reflights = reflight_rate(start, end)
    incident_free = incident_free_flight_hours()
    return [
        {
            "code": "fleet_availability",
            "label": _("Fleet availability"),
            "help": _("Aircraft flyable now, excluding retired ones."),
            "value": availability["pct"],
            "detail": f"{availability['available']}/{availability['total']}",
            "target": availability["target"],
            "unit": UNIT_PERCENT,
            "direction": HIGHER_IS_BETTER,
            "met": _met(availability["pct"], availability["target"], HIGHER_IS_BETTER),
        },
        {
            "code": "on_time_execution",
            "label": _("On-time execution"),
            "help": _(
                "Approved permits whose validity ended in this period with at "
                "least one flight recorded."
            ),
            "value": execution["pct"],
            "detail": f"{execution['on_time']}/{execution['total']}",
            "target": execution["target"],
            "unit": UNIT_PERCENT,
            "direction": HIGHER_IS_BETTER,
            "met": _met(execution["pct"], execution["target"], HIGHER_IS_BETTER),
        },
        {
            "code": "survey_accuracy",
            "label": _("Survey accuracy"),
            "help": _(
                "Deliverables validated in this period that met the contract's "
                "criteria, out of those that could be assessed."
            ),
            "value": accuracy["pct"],
            "detail": f"{accuracy['met']}/{accuracy['total']}",
            "target": SURVEY_ACCURACY_TARGET,
            "unit": UNIT_PERCENT,
            "direction": HIGHER_IS_BETTER,
            "met": _met(accuracy["pct"], SURVEY_ACCURACY_TARGET, HIGHER_IS_BETTER),
        },
        {
            "code": "reflight_rate",
            "label": _("Reflight rate"),
            "help": _("Reflights recorded in this period, out of flights flown."),
            "value": reflights["pct"],
            "detail": f"{reflights['reflights']}/{reflights['flights']}",
            "target": REFLIGHT_RATE_TARGET,
            "unit": UNIT_PERCENT,
            "direction": LOWER_IS_BETTER,
            "met": _met(reflights["pct"], REFLIGHT_RATE_TARGET, LOWER_IS_BETTER),
        },
        {
            # A running counter, not a percentage: `unit` says so explicitly
            # rather than leaving the template to infer it from a null value --
            # which would also swallow the "nothing to measure" case of the
            # percentages above and print their bare "0/0".
            "code": "incident_free_flight_hours",
            "label": _("Incident-free flight hours"),
            "help": (
                _("Flight time accumulated since the incident of %(date)s.")
                % {"date": incident_free["since"].isoformat()}
                if incident_free["since"]
                else _("Flight time accumulated with no incident on record.")
            ),
            "value": None,
            "detail": incident_free["display"],
            "target": None,
            "unit": UNIT_DURATION,
            "direction": HIGHER_IS_BETTER,
            "met": None,
        },
    ]
