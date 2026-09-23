"""Shared read selectors for ResourceMovementLog (OPS-1/2/6).

Kept in one place so the Operator/Aircraft/CostCenter timelines and the
standalone movement log list cannot drift apart on how a row's bare
resource_id gets resolved to a human label.
"""

from collections import defaultdict
from datetime import timedelta

from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from .models import Aircraft, Operator, Qualification, ResourceMovementLog

# LV-242: el criterio de "al día", en un solo lugar para las dos superficies.
#
# El panel dice *"Seguros al día 13/14 · 1 vencido"* y su tarjeta llevaba al padrón
# **completo, sin filtrar**: la cifra decía cuántos faltan y después había que
# buscarlos a ojo entre dieciséis. El filtro no existía en `AircraftList` ni en
# `OperatorList` — sólo `search_fields`.
#
# ⚠️ **Y el criterio tiene que ser el mismo, o el clic miente.** Si la lista
# filtrara sólo por fecha, una aeronave con póliza vencida pero dada de baja
# aparecería ahí y no en la tarjeta: el usuario contaría cinco donde el panel dijo
# cuatro. Por eso las exclusiones viven acá y las usan los dos —`panel_readiness`
# y la lista—, que es la lección que `LV-188` y `LV-201` dejaron cara: dos mitades
# del mismo cálculo separadas terminan diciendo números distintos.


def operational_fleet():
    """La flota sobre la que se mide disponibilidad y cobertura.

    `retired` queda fuera porque una aeronave dada de baja no está "no
    disponible": salió de la flota, y contarla hundiría el indicador para siempre
    por una decisión correcta (el mismo criterio que `kpis.fleet_availability`).

    Las faenas que **no vuelan** también (`LV-229`): sus equipos están en bodega, y
    un seguro sin renovar ahí no es una brecha de cobertura. `cost_center__isnull`
    **entra**, y eso no es descuido: una aeronave sin faena no es una que no vuela,
    es una cuya pertenencia falta — y eso sí hay que verlo.
    """
    return (
        Aircraft.objects.filter(is_active=True)
        .exclude(status="retired")
        .exclude(cost_center__operates_flights=False)
    )


def operational_roster():
    """El padrón sobre el que se miden las credenciales DGAC."""
    return Operator.objects.filter(is_active=True)


def filter_by_insurance(queryset, key, today):
    """Acota la flota por el estado de su póliza JAC, o la devuelve intacta.

    `attention` es **el complemento exacto del numerador de la tarjeta**: todo lo
    que no cuenta como "al día", sea por fecha vencida, por no tener fecha o
    porque la póliza no está activa. Es el destino natural del clic — la tarjeta
    dice cuántos faltan y el clic muestra cuáles.

    Una clave desconocida no filtra ni falla, que es la convención del repo para
    los parámetros de listado: un filtro mal escrito es un no-op, no un error.

    ⚠️ **Con filtro puesto se acota además a la flota operativa, y ese es el punto
    de la fila.** Sin eso, una aeronave con la póliza vencida pero **dada de baja**
    —o de una faena que no vuela— saldría en la lista y no en la tarjeta: el
    usuario contaría cinco donde el panel dijo cuatro, y la cifra dejaría de ser
    creíble justo cuando se va a actuar sobre ella. Lo cazaron dos tests de
    `LV-242` escritos antes de que el filtro existiera.

    Sin filtro **no** se acota: la lista es el padrón, y esconder ahí una aeronave
    dada de baja sería peor que mostrarla.
    """
    if key not in {"attention", "lapsed", "missing", "soon"}:
        return queryset
    queryset = queryset.exclude(status="retired").exclude(
        cost_center__operates_flights=False
    )
    if key == "attention":
        return queryset.exclude(
            insurance_status=Aircraft.INSURANCE_STATUS_ACTIVE,
            insurance_expiry__gte=today,
        )
    if key == "lapsed":
        return queryset.filter(insurance_expiry__lt=today)
    if key == "missing":
        return queryset.filter(insurance_expiry__isnull=True)
    return queryset.filter(
        insurance_expiry__gte=today,
        insurance_expiry__lte=today + timedelta(days=30),
    )


def filter_by_credential(queryset, key, today):
    """Lo mismo para la credencial DGAC de cada operador.

    Aquí "al día" es sólo la fecha —no hay un campo de estado como en la póliza—
    así que `attention` es todo lo que no tiene una vigencia por delante,
    incluidos los que nunca la tuvieron cargada.
    """
    if key == "attention":
        return queryset.exclude(credential_expiry__gte=today)
    if key == "lapsed":
        return queryset.filter(credential_expiry__lt=today)
    if key == "missing":
        return queryset.filter(credential_expiry__isnull=True)
    if key == "soon":
        return queryset.filter(
            credential_expiry__gte=today,
            credential_expiry__lte=today + timedelta(days=30),
        )
    return queryset


def label_movements(entries):
    """Attach `.resource_label` to each entry (Operator full_name / Aircraft
    registration), resolved in two queries regardless of how many rows."""
    entries = list(entries)
    operator_ids = [
        entry.resource_id for entry in entries if entry.resource_kind == "operator"
    ]
    aircraft_ids = [
        entry.resource_id for entry in entries if entry.resource_kind == "aircraft"
    ]
    operators = dict(
        Operator.objects.filter(pk__in=operator_ids).values_list("pk", "full_name")
    )
    aircraft = dict(
        Aircraft.objects.filter(pk__in=aircraft_ids).values_list("pk", "registration")
    )
    for entry in entries:
        label = (
            operators.get(entry.resource_id)
            if entry.resource_kind == "operator"
            else aircraft.get(entry.resource_id)
        )
        entry.resource_label = label or str(entry.resource_id)
        # LV-88: the log named the resource in plain text, so reading "RPA-3696
        # moved" and then opening it meant going back to the padrón and
        # searching for it. None when the row points at something that no
        # longer resolves -- the log is append-only and outlives its subject.
        entry.resource_url = (
            reverse(f"{entry.resource_kind}-detail", args=[entry.resource_id])
            if label
            else None
        )
    return entries


def movements_for_resource(resource_kind, resource_id):
    """This resource's own timeline (OPS-6): every movement, newest first."""
    queryset = ResourceMovementLog.objects.filter(
        resource_kind=resource_kind, resource_id=resource_id
    ).select_related("from_cost_center", "to_cost_center", "changed_by_user")
    return label_movements(queryset)


def movements_for_cost_center(cost_center, limit=100):
    """A contract's movement history: anything that moved into or out of it."""
    queryset = ResourceMovementLog.objects.filter(
        Q(from_cost_center=cost_center) | Q(to_cost_center=cost_center)
    ).select_related("changed_by_user", "from_cost_center", "to_cost_center")[:limit]
    return label_movements(queryset)


def operator_aircraft_compatibility_gaps(operators, aircraft_fleet):
    """B4.4: (operator, aircraft) pairs from these rosters where the operator
    holds no current qualification covering that aircraft's model.

    Non-blocking by design (agreed with the user 2026-07-30): a flight
    permission can still be created with a gap, this only flags it. Matched
    against `Aircraft.model` -- `Aircraft.type` is uniformly "RPA" in the real
    fleet and carries no signal to compare against.

    Returns a list of (operator, aircraft) tuples, empty when either roster is
    empty, no qualification type declares `model_keywords`, or every pair is
    covered.
    """
    operators = list(operators)
    aircraft_fleet = list(aircraft_fleet)
    if not operators or not aircraft_fleet:
        return []

    today = timezone.localdate()
    current_qualifications = (
        Qualification.objects.filter(operator__in=operators, is_active=True)
        .filter(Q(expiry_date__isnull=True) | Q(expiry_date__gte=today))
        .select_related("qualification_type")
    )
    keywords_by_operator = defaultdict(list)
    for qualification in current_qualifications:
        keywords_by_operator[qualification.operator_id].extend(
            qualification.qualification_type.keyword_list()
        )

    gaps = []
    for operator in operators:
        keywords = keywords_by_operator.get(operator.pk, [])
        for aircraft in aircraft_fleet:
            model = (aircraft.model or "").lower()
            if not any(keyword in model for keyword in keywords):
                gaps.append((operator, aircraft))
    return gaps
