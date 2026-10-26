"""Shared read selectors for ResourceMovementLog (OPS-1/2/6).

Kept in one place so the Operator/Aircraft/CostCenter timelines and the
standalone movement log list cannot drift apart on how a row's bare
resource_id gets resolved to a human label.
"""

import unicodedata
from collections import defaultdict
from datetime import timedelta

from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from django.utils.translation import gettext as _

from .models import (
    Aircraft,
    CostCenter,
    KnowledgeAssessment,
    Operator,
    Qualification,
    ResourceMovementLog,
)

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


def operating_cost_centers():
    """LV-266: las faenas que **entran en los registros**. Una sola definición.

    Entra una faena activa, en la que se vuela y con el contrato abierto. Una
    faena **cerrada** o **sin operación** queda fuera de la cobertura de permisos,
    del cierre mensual, del resumen de vencimientos y de la consulta «¿Puedo
    volar?»: ya no hay nada que registrar ahí, y listarla declara incumplida una
    operación que no le toca. Regla del usuario, 2026-10-05: *«al estar como sin
    vuelo u operación no entra en los registros»*.

    Estaba escrita **tres veces y distinta**: la cobertura y el cierre mensual
    excluían las cerradas; «¿Puedo volar?» sólo las que no vuelan; y el resumen de
    vencimientos ninguna de las dos, así que seguía escribiéndole a la faena
    cerrada (`CC716`, con permiso vivo) mientras la tabla del informe ya no la
    contaba. Un lugar donde se decide es lo que impide que vuelvan a separarse.

    🔶 Lo que **no** cambia: un permiso vivo de una faena cerrada sigue listándose
    en la hoja de permisos del informe —existe ante la DGAC aunque la faena haya
    cerrado—, y por eso el bloque «Revisar antes de emitir» avisa del desacuerdo
    en vez de esconderlo.
    """
    return CostCenter.objects.filter(is_active=True, operates_flights=True).exclude(
        contract_status=CostCenter.CONTRACT_CLOSED
    )


def is_operating(cost_center):
    """¿Esta faena entra en los registros? Es la misma regla que
    `operating_cost_centers`, leída sobre una fila ya cargada."""
    return (
        cost_center.is_active
        and cost_center.operates_flights
        and cost_center.contract_status != CostCenter.CONTRACT_CLOSED
    )


def live_permits_of(cost_center, user, today=None):
    """LV-378 fase 4: los permisos de vuelo **vivos** de una faena.

    Vivo es `requested` o `approved`, activo y con la vigencia **no vencida** (sin
    fecha de término también cuenta: un permiso en trámite aún no la tiene). Es
    lo que hay que dejar vencer o archivar cuando la faena deja de operar; no se
    inventa un estado nuevo.

    Acotado al tenant de `user` por la faena del permiso, y vacío si la persona
    no puede ver permisos de vuelo: el aviso no es un canal para enterarse de
    folios que la pantalla de permisos le negaría.
    """
    from apps.core.tenancy import scope_queryset_to_tenant
    from apps.operations.models import FlightPermission

    if not user.has_perm("operations.view_flightpermission"):
        return FlightPermission.objects.none()
    today = today or timezone.localdate()
    queryset = FlightPermission.objects.filter(
        cost_center=cost_center,
        is_active=True,
        status__in=(
            FlightPermission.STATUS_REQUESTED,
            FlightPermission.STATUS_APPROVED,
        ),
    ).filter(Q(valid_until__isnull=True) | Q(valid_until__gte=today))
    return scope_queryset_to_tenant(
        queryset, user, tenant_path="cost_center__tenant_id"
    ).order_by("internal_folio")


def closed_centre_permit_warning(cost_center, user, today=None):
    """El aviso (HTML ya escapado) de los permisos vivos que dejó una faena que
    salió de operación, o `None` si no hay nada que decir."""
    permits = list(live_permits_of(cost_center, user, today))
    if not permits:
        return None
    links = format_html_join(
        ", ",
        '<a href="{}">{}</a>',
        (
            (
                reverse("permission-detail", args=[permit.pk]),
                permit.internal_folio,
            )
            for permit in permits
        ),
    )
    return format_html(
        _(
            "{code} no longer operates, but these flight permits are still "
            "live: {permits}. They are not renewed: let them expire or "
            "archive them."
        ),
        code=cost_center.code,
        permits=links,
    )


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


def operational_roster(as_of=None):
    """El padrón sobre el que se miden las credenciales DGAC.

    Sin `as_of`: el padrón **de hoy** (activos). Con `as_of` (el corte de un
    informe, LV-369): además de los activos, quien **salió después** del corte
    —estaba en la empresa ese día—, y no quien salió antes o **en** el corte. Se
    lee `left_company_on` y no `is_active`: el informe mensual describe una fecha,
    y archivar a alguien hoy no debe sacarlo de un mes que ya pasó cuando se sabe
    cuándo se fue. Para los datos sin salida registrada todo queda como estaba.

    ⚠️ La diferencia hoy-vs-corte es deliberada: el catastro y el panel de hoy no
    muestran a un ex colaborador, y el informe de un mes en que aún estaba, sí.
    """
    if as_of is None:
        return Operator.objects.filter(is_active=True)
    return Operator.objects.filter(
        Q(is_active=True, left_company_on__isnull=True) | Q(left_company_on__gt=as_of)
    )


def without_departed(queryset):
    """Quita de un queryset lo que cuelga de alguien que **salió de la empresa**.

    LV-369: lo usan el motor de alertas y las listas de vencimientos. Entiende
    `Operator`, lo que lleva un `operator` (habilitaciones, pruebas) y los
    documentos cuyo sujeto es una persona. Cualquier otro modelo vuelve intacto.
    """
    from django.contrib.contenttypes.models import ContentType

    model = queryset.model
    if model is Operator:
        return queryset.filter(left_company_on__isnull=True)
    if model in (Qualification, KnowledgeAssessment):
        return queryset.filter(operator__left_company_on__isnull=True)
    if model._meta.label == "compliance.Document":
        return queryset.exclude(
            content_type=ContentType.objects.get_for_model(Operator),
            object_id__in=Operator.objects.filter(left_company_on__isnull=False).values(
                "pk"
            ),
        )
    return queryset


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


def operator_aircraft_compatibility_gaps(operators, aircraft_fleet, today=None):
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

    # LV-257: el día **a evaluar**, cuando quien llama lo sabe. «¿Puedo volar?»
    # (`can_fly`) recibe una fecha y la pasaba a todas sus comprobaciones menos a
    # ésta, que decidía la vigencia de las habilitaciones con el día real — un
    # veredicto sobre una fecha armado con dos fechas.
    today = today or timezone.localdate()
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
        written = _plain(getattr(operator, "authorizations", ""))
        for aircraft in aircraft_fleet:
            model = (aircraft.model or "").lower()
            if any(keyword in model for keyword in keywords):
                continue
            # LV-300: la habilitación escrita a mano en la ficha también cuenta.
            series = aircraft_series(aircraft)
            if series and series in written:
                continue
            gaps.append((operator, aircraft))
    return gaps


def _plain(text):
    """Minúsculas y sin tildes, para comparar texto libre sin que una tilde decida."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def aircraft_series(aircraft):
    """La **serie** del equipo: la primera palabra de su modelo («Mavic» en «Mavic 3
    Enterprise», «Matrice» en «Matrice 300 RTK»), sin tildes y en minúsculas.

    LV-300, pedido del usuario (2026-10-13): *«si tiene una parte del nombre del equipo
    ya cumple, como Mavic series»*. Los operadores importados de los capítulos traen su
    habilitación como texto libre («Mavic-Phantom-Matrice / Series»), no como
    `Qualification`, y la comprobación sólo miraba éstas: un operador que sí cumple salía
    con brecha.

    **La serie y no cualquier palabra del modelo**, a propósito: «Enterprise» o «Thermal»
    aparecen en modelos de series distintas, y habilitarse en «Mavic 3 Enterprise» no
    habilita para «Matrice 4 Enterprise». Un falso «cumple» es peor que un falso «no
    cumple», que sólo cuesta una revisión. Una palabra de menos de tres letras o sin
    letras no sirve de serie.
    """
    first = (_plain(getattr(aircraft, "model", "")).split() or [""])[0]
    first = "".join(c for c in first if c.isalpha())
    return first if len(first) >= 3 else ""
