"""Herramientas de SOLO LECTURA que el asistente puede pedir.

PROTOTIPO (`LV-305`, ampliado en `LV-340`). El modelo **nunca** toca la base: sólo puede pedir
estas funciones, que reutilizan los mismos cálculos que el panel y devuelven **datos agregados
o no personales**. Reglas que no se rompen:

- **Cada herramienta declara el permiso** que exige; el servicio lo comprueba contra el usuario
  que pregunta antes de ejecutarla (la IA no amplía lo que esa persona puede ver).
- **Nada personal sale hacia el servicio externo.** Quedan EXCLUIDOS para siempre los campos
  libres (descripciones, notas, quién hizo qué, mensajes de alerta, títulos de solicitud, nombre
  de la faena, responsables), cualquier fila de operadores, habilitaciones o evaluaciones, y
  «¿puedo volar?» con una persona. Salen folios internos, códigos de faena, matrículas (son
  públicas en el registro DGAC), tipos del CATÁLOGO de documentos y fechas.
- **Cada herramienta acota por la empresa (tenant) de quien pregunta**, igual que el panel
  (`LV-323`): con dos empresas, ninguna ve los datos de la otra.
- **Salida acotada y validada**: como mucho `MAX_ROWS` filas (se recortan ANTES de serializar,
  así el JSON nunca queda cortado a medias), claves y tipos de una lista blanca, códigos
  saneados, fechas ISO, y todo envuelto como `{"data": ...}`.
- **Ninguna herramienta escribe.** Agregar una que escriba exige una decisión explícita del
  usuario: una máquina que aprueba o declara cumplimiento es lo contrario de la evidencia.
"""

import json
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable
from uuid import UUID

from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core.tenancy import scope_queryset_to_tenant

MAX_ROWS = 25
MAX_DAYS = 365
MAX_CHARS = 6000

_NONE = type(None)
_CODE_RE = re.compile(r"[^A-Za-z0-9\-_.]")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict
    permission: str
    run: Callable
    # Lista blanca de la salida: ver `_validate`.
    schema: object = None


# ----------------------------------------------------------------------------------------
# Ayudas comunes
# ----------------------------------------------------------------------------------------


def _code(value):
    """Un código o folio saneado: sólo `[A-Za-z0-9-_.]` y a lo más 30 caracteres."""
    return _CODE_RE.sub("", str(value or ""))[:30]


def _text(value, limit=80):
    """Un nombre de catálogo: sin caracteres de control y acotado."""
    return _CONTROL_RE.sub(" ", str(value or "")).strip()[:limit]


def _iso(value):
    return value.isoformat() if value else None


def _days_argument(arguments, default=30):
    try:
        days = int(arguments.get("days", default))
    except (TypeError, ValueError):
        days = default
    return max(1, min(days, MAX_DAYS))


def _validate(value, spec, trimmed):
    """Proyecta `value` sobre la lista blanca `spec` y comprueba los tipos.

    - un tipo o tupla de tipos: `isinstance` (un `bool` no pasa por `int`);
    - un `dict` con la clave `"*"`: mapa de claves saneadas a valores de ese tipo;
    - un `dict`: sólo se conservan las claves declaradas;
    - una lista `[spec]`: cada fila se valida y se recorta a `MAX_ROWS`.
    Levanta `ValueError` ante un tipo inesperado: la herramienta devuelve un error neutro.
    """
    if isinstance(spec, dict):
        if not isinstance(value, dict):
            raise ValueError("expected a mapping")
        if "*" in spec:
            return {
                _code(key): _validate(item, spec["*"], trimmed)
                for key, item in value.items()
            }
        return {key: _validate(value[key], sub, trimmed) for key, sub in spec.items()}
    if isinstance(spec, list):
        if not isinstance(value, (list, tuple)):
            raise ValueError("expected a list")
        if len(value) > MAX_ROWS:
            trimmed.append(True)
        return [_validate(item, spec[0], trimmed) for item in list(value)[:MAX_ROWS]]
    types = spec if isinstance(spec, tuple) else (spec,)
    if isinstance(value, bool) and bool not in types:
        raise ValueError("unexpected boolean")
    if not isinstance(value, types):
        raise ValueError("unexpected type")
    return value


def _longest_list(data):
    lists = [data] if isinstance(data, list) else []
    if isinstance(data, dict):
        lists += [item for item in data.values() if isinstance(item, list)]
    lists = [item for item in lists if item]
    return max(lists, key=len) if lists else None


def _envelope(data, truncated):
    """El JSON `{"data": ...}`; si pasa de `MAX_CHARS` quita FILAS, nunca corta el texto."""
    while True:
        body = {"data": data}
        if truncated:
            body["truncated"] = True
        text = json.dumps(body, ensure_ascii=False)
        if len(text) <= MAX_CHARS:
            return text
        rows = _longest_list(data)
        if rows is None:
            return json.dumps({"error": "the data could not be read"})
        rows.pop()
        truncated = True


# ----------------------------------------------------------------------------------------
# Permisos de vuelo (LV-305 / LV-323)
# ----------------------------------------------------------------------------------------


def _permits_summary(user, arguments):
    from apps.compliance.kpis import permit_counts

    counts = permit_counts(timezone.localdate(), user=user)
    keys = (
        "total",
        "in_force",
        "not_started",
        "awaiting",
        "soon",
        "lapsed",
        "expired_this_month",
    )
    return {key: counts.get(key) for key in keys}


def _cost_centres_status(user, arguments):
    from apps.compliance.kpis import permit_status_by_cost_center

    rows = permit_status_by_cost_center(timezone.localdate(), user=user)
    return [
        {
            "code": _code(row["cost_center"].code),
            "in_force": row["in_force"],
            "not_started": row["not_started"],
            "awaiting": row["awaiting"],
            "expiring_in_30_days": row["soon"],
            "next_expiry": _iso(row["next_expiry"]),
        }
        for row in rows[: MAX_ROWS + 1]
    ]


def _expiring_permits(user, arguments):
    from apps.operations.models import FlightPermission

    days = _days_argument(arguments)
    today = timezone.localdate()
    permits = scope_queryset_to_tenant(
        FlightPermission.objects.filter(
            is_active=True,
            status=FlightPermission.STATUS_APPROVED,
            valid_until__gte=today,
            valid_until__lte=today + timedelta(days=days),
        ),
        user,
        "cost_center__tenant_id",
    )
    return [
        {
            # `pk` no es dato personal; sirve para que el SERVIDOR arme el enlace de cita
            # (`citations_for`). El modelo jamás escribe una URL.
            "pk": str(permit.pk),
            "permit": _code(permit.internal_folio),
            "cost_centre": _code(permit.cost_center.code),
            "valid_until": permit.valid_until.isoformat(),
            "days_left": (permit.valid_until - today).days,
        }
        for permit in permits.select_related("cost_center").order_by("valid_until")[
            : MAX_ROWS + 1
        ]
    ]


# ----------------------------------------------------------------------------------------
# Mantención, documentos, seguros, alertas, solicitudes, flota (LV-340)
# ----------------------------------------------------------------------------------------


def _upcoming_maintenance(user, arguments):
    from django.db.models import F, Q

    from apps.maintenance.models import MaintenanceRecord

    days = _days_argument(arguments)
    today = timezone.localdate()
    records = scope_queryset_to_tenant(
        MaintenanceRecord.objects.filter(is_active=True).exclude(
            status__in=MaintenanceRecord.TERMINAL_STATUSES
        ),
        user,
        "aircraft__tenant_id",
    ).filter(
        Q(scheduled_date__lte=today + timedelta(days=days))
        | Q(scheduled_date__isnull=True)
        | Q(maintenance_type="to_be_defined")
    )
    rows = []
    for record in records.select_related("aircraft").order_by(
        F("scheduled_date").asc(nulls_last=True), "pk"
    )[: MAX_ROWS + 1]:
        rows.append(
            {
                "pk": str(record.pk),
                "registration": _code(record.aircraft.registration),
                "maintenance_type": _code(record.maintenance_type),
                "status": _code(record.status),
                "scheduled_date": _iso(record.scheduled_date),
                "days_left": (
                    (record.scheduled_date - today).days
                    if record.scheduled_date
                    else None
                ),
                "to_be_defined": record.is_incomplete,
            }
        )
    return rows


def _expiring_company_documents(user, arguments):
    from django.contrib.contenttypes.models import ContentType

    from apps.compliance.models import Document
    from apps.registry.models import Aircraft, CostCenter

    days = _days_argument(arguments)
    today = timezone.localdate()
    kinds = {
        ContentType.objects.get_for_model(Aircraft).pk: ("aircraft", Aircraft),
        ContentType.objects.get_for_model(CostCenter).pk: ("site", CostCenter),
    }
    documents = list(
        scope_queryset_to_tenant(
            Document.objects.filter(
                is_active=True,
                is_current_version=True,
                expiry_date__isnull=False,
                expiry_date__lte=today + timedelta(days=days),
                # Los documentos de una PERSONA (operador) no salen: sólo aeronave y faena.
                content_type_id__in=list(kinds),
            ),
            user,
            "tenant_id",
        )
        .select_related("doc_type")
        .order_by("expiry_date", "pk")[: MAX_ROWS + 1]
    )
    codes = {}
    for content_type_id, (_kind, model) in kinds.items():
        ids = {d.object_id for d in documents if d.content_type_id == content_type_id}
        field = "registration" if model is Aircraft else "code"
        codes[content_type_id] = dict(
            model.objects.filter(pk__in=ids).values_list("pk", field)
        )
    rows = []
    for document in documents:
        kind = kinds[document.content_type_id][0]
        rows.append(
            {
                "pk": str(document.pk),
                # El tipo del CATÁLOGO, nunca `title`: el título es texto libre.
                "doc_type": _text(document.doc_type.name),
                "subject_kind": kind,
                "subject_code": _code(
                    codes[document.content_type_id].get(document.object_id)
                ),
                "expiry_date": document.expiry_date.isoformat(),
                "days_left": (document.expiry_date - today).days,
            }
        )
    return rows


def _aircraft_insurance_status(user, arguments):
    from django.db.models import F

    from apps.registry.models import Aircraft

    today = timezone.localdate()
    fleet = scope_queryset_to_tenant(
        Aircraft.objects.filter(is_active=True).exclude(status="retired"),
        user,
        "tenant_id",
    )
    return [
        {
            "pk": str(aircraft.pk),
            "registration": _code(aircraft.registration),
            "insurance_status": _code(aircraft.insurance_status),
            "insurance_expiry": _iso(aircraft.insurance_expiry),
            "days_left": (
                (aircraft.insurance_expiry - today).days
                if aircraft.insurance_expiry
                else None
            ),
        }
        for aircraft in fleet.order_by(
            F("insurance_expiry").asc(nulls_first=True), "registration"
        )[: MAX_ROWS + 1]
    ]


def _open_alerts_by_urgency(user, arguments):
    from apps.compliance.digest import ENTITY_TONES, bucket_for
    from apps.compliance.models import Alert

    today = timezone.localdate()
    alerts = scope_queryset_to_tenant(
        Alert.objects.filter(is_active=True, is_resolved=False),
        user,
        "alert_rule__tenant_id",
    ).values_list("watched_value", "content_type__app_label", "content_type__model")
    by_urgency = {
        "overdue": 0,
        "due_7": 0,
        "due_15": 0,
        "due_30": 0,
        "later": 0,
        "undated": 0,
    }
    by_entity = {"person": 0, "aircraft": 0, "permit": 0, "document": 0, "other": 0}
    total = 0
    for watched, app_label, model in alerts:
        total += 1
        try:
            expiry = date.fromisoformat(watched) if watched else None
        except ValueError:
            expiry = None
        key = "undated" if expiry is None else (bucket_for(expiry, today) or "later")
        by_urgency[key] += 1
        tone = ENTITY_TONES.get(f"{app_label}.{model}", "other")
        by_entity[tone if tone in by_entity else "other"] += 1
    # Sólo conteos: el mensaje y la entidad de cada alerta (puede ser una persona) no salen.
    return {"total": total, "by_urgency": by_urgency, "by_entity": by_entity}


def _flight_requests_status(user, arguments):
    from django.db.models import Count

    from apps.operations.models import FlightRequest

    today = timezone.localdate()
    requests = scope_queryset_to_tenant(
        FlightRequest.objects.filter(is_active=True),
        user,
        "cost_center__tenant_id",
    )
    by_status = {
        row["status"]: row["n"]
        for row in requests.values("status").annotate(n=Count("pk"))
    }
    rows = [
        {
            "pk": str(item.pk),
            "cost_centre": _code(item.cost_center.code),
            "status": _code(item.status),
            "request_type": _code(item.request_type),
            "age_days": (today - timezone.localdate(item.created_at)).days,
        }
        for item in requests.exclude(status=FlightRequest.STATUS_CLOSED)
        .select_related("cost_center")
        .order_by("created_at", "pk")[: MAX_ROWS + 1]
    ]
    # Nunca `title`, `commune` ni `area_name`: son texto libre o del cliente.
    return {"total": sum(by_status.values()), "by_status": by_status, "rows": rows}


def _fleet_availability(user, arguments):
    from django.db.models import Count

    from apps.compliance.kpis import fleet_availability
    from apps.registry.models import Aircraft

    result = fleet_availability(user=user)
    by_status = {
        row["status"]: row["n"]
        for row in scope_queryset_to_tenant(
            Aircraft.objects.filter(is_active=True), user, "tenant_id"
        )
        .values("status")
        .annotate(n=Count("pk"))
    }
    return {
        "total": result["total"],
        "available": result["available"],
        "pct": result["pct"],
        "target": result["target"],
        "by_status": by_status,
    }


def _aircraft_readiness(user, arguments):
    from apps.operations.readiness import check_aircraft_for_assistant
    from apps.registry.models import Aircraft

    registration = _code(arguments.get("registration"))
    aircraft = (
        scope_queryset_to_tenant(
            Aircraft.objects.filter(is_active=True, registration__iexact=registration),
            user,
            "tenant_id",
        ).first()
        if registration
        else None
    )
    if aircraft is None:
        return {
            "found": False,
            "pk": None,
            "registration": None,
            "nothing_in_records_prevents_flight": None,
            "blockers": [],
            "warnings": [],
            "note": None,
        }
    found = check_aircraft_for_assistant(aircraft, timezone.localdate())
    return {
        "found": True,
        "pk": str(aircraft.pk),
        "registration": _code(aircraft.registration),
        # Nunca «puede volar»: sólo si en los registros hay algo que lo impida.
        "nothing_in_records_prevents_flight": not found["blockers"],
        "blockers": [_readiness_row(row) for row in found["blockers"]],
        "warnings": [_readiness_row(row) for row in found["warnings"]],
        "note": NOTE,
    }


NOTE = (
    "Only what the records show; this does not authorise any flight and "
    "does not review any person."
)


def _readiness_row(row):
    return {
        "item": _text(row["item"]),
        "date": row["date"],
        "flag": _code(row["flag"]),
    }


# ----------------------------------------------------------------------------------------
# Registro
# ----------------------------------------------------------------------------------------

_DAYS_PARAMETERS = {
    "type": "object",
    "properties": {
        "days": {
            "type": "integer",
            "description": "Ventana en días (1 a 365). Por omisión 30.",
        }
    },
}
_NO_PARAMETERS = {"type": "object", "properties": {}}
_OPT_STR = (str, _NONE)
_OPT_INT = (int, _NONE)
_COUNTS = {"*": int}

TOOLS = {
    tool.name: tool
    for tool in (
        Tool(
            name="permits_summary",
            description=(
                "Resumen de permisos de vuelo: cuántos hay vigentes, aún sin empezar, "
                "esperando respuesta de la DGAC, por vencer en 30 días y atrasados."
            ),
            parameters=_NO_PARAMETERS,
            permission="operations.view_flightpermission",
            run=_permits_summary,
            schema={
                key: _OPT_INT
                for key in (
                    "total",
                    "in_force",
                    "not_started",
                    "awaiting",
                    "soon",
                    "lapsed",
                    "expired_this_month",
                )
            },
        ),
        Tool(
            name="cost_centres_permit_status",
            description=(
                "Estado de permisos por centro de costo (faena): vigentes, esperando, "
                "por vencer y próximo vencimiento. Sirve para saber qué faenas no tienen "
                "permiso vigente."
            ),
            parameters=_NO_PARAMETERS,
            permission="operations.view_flightpermission",
            run=_cost_centres_status,
            schema=[
                {
                    "code": str,
                    "in_force": int,
                    "not_started": int,
                    "awaiting": int,
                    "expiring_in_30_days": int,
                    "next_expiry": _OPT_STR,
                }
            ],
        ),
        Tool(
            name="expiring_permits",
            description=(
                "Permisos aprobados que vencen dentro de los próximos N días, ordenados "
                "por fecha de término."
            ),
            parameters=_DAYS_PARAMETERS,
            permission="operations.view_flightpermission",
            run=_expiring_permits,
            schema=[
                {
                    "pk": str,
                    "permit": str,
                    "cost_centre": str,
                    "valid_until": str,
                    "days_left": int,
                }
            ],
        ),
        Tool(
            name="upcoming_maintenance",
            description=(
                "Mantenciones abiertas programadas dentro de los próximos N días, más las "
                "atrasadas y las que aún están por definir. Por aeronave (matrícula)."
            ),
            parameters=_DAYS_PARAMETERS,
            permission="maintenance.view_maintenancerecord",
            run=_upcoming_maintenance,
            schema=[
                {
                    "pk": str,
                    "registration": str,
                    "maintenance_type": str,
                    "status": str,
                    "scheduled_date": _OPT_STR,
                    "days_left": _OPT_INT,
                    "to_be_defined": bool,
                }
            ],
        ),
        Tool(
            name="expiring_company_documents",
            description=(
                "Documentos de aeronaves y de faenas que vencen dentro de los próximos N "
                "días (o ya vencidos), con su tipo del catálogo. No incluye documentos "
                "de personas."
            ),
            parameters=_DAYS_PARAMETERS,
            permission="compliance.view_document",
            run=_expiring_company_documents,
            schema=[
                {
                    "pk": str,
                    "doc_type": str,
                    "subject_kind": str,
                    "subject_code": str,
                    "expiry_date": str,
                    "days_left": int,
                }
            ],
        ),
        Tool(
            name="aircraft_insurance_status",
            description=(
                "Estado del seguro JAC de cada aeronave de la flota: trámite, fecha de "
                "vencimiento y días que quedan."
            ),
            parameters=_NO_PARAMETERS,
            permission="registry.view_aircraft",
            run=_aircraft_insurance_status,
            schema=[
                {
                    "pk": str,
                    "registration": str,
                    "insurance_status": str,
                    "insurance_expiry": _OPT_STR,
                    "days_left": _OPT_INT,
                }
            ],
        ),
        Tool(
            name="open_alerts_by_urgency",
            description=(
                "Cuántas alertas abiertas hay, por urgencia (vencidas, 7, 15, 30 días, "
                "más adelante, sin fecha) y por tipo de entidad. Sólo conteos."
            ),
            parameters=_NO_PARAMETERS,
            permission="compliance.view_alert",
            run=_open_alerts_by_urgency,
            schema={"total": int, "by_urgency": _COUNTS, "by_entity": _COUNTS},
        ),
        Tool(
            name="flight_requests_status",
            description=(
                "Solicitudes de vuelo: cuántas hay por estado y las abiertas con su "
                "faena, estado, tipo y antigüedad en días."
            ),
            parameters=_NO_PARAMETERS,
            permission="operations.view_flightrequest",
            run=_flight_requests_status,
            schema={
                "total": int,
                "by_status": _COUNTS,
                "rows": [
                    {
                        "pk": str,
                        "cost_centre": str,
                        "status": str,
                        "request_type": str,
                        "age_days": int,
                    }
                ],
            },
        ),
        Tool(
            name="fleet_availability",
            description=(
                "Disponibilidad de la flota: total, disponibles, porcentaje, meta y "
                "cuántas aeronaves hay por estado."
            ),
            parameters=_NO_PARAMETERS,
            permission="registry.view_aircraft",
            run=_fleet_availability,
            schema={
                "total": int,
                "available": int,
                "pct": (float, _NONE),
                "target": (float, int),
                "by_status": _COUNTS,
            },
        ),
        Tool(
            name="aircraft_readiness",
            description=(
                "Qué dicen los registros de UNA aeronave por su matrícula: estado, seguro, "
                "documentos y permiso vigente de su faena. No dice que pueda volar: sólo si "
                "hay algo que lo impida. No revisa a ninguna persona."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "registration": {
                        "type": "string",
                        "description": "Matrícula de la aeronave, por ejemplo RPA-1234.",
                    }
                },
                "required": ["registration"],
            },
            permission="registry.view_aircraft",
            run=_aircraft_readiness,
            schema={
                "found": bool,
                "pk": (str, _NONE),
                "registration": (str, _NONE),
                "nothing_in_records_prevents_flight": (bool, _NONE),
                "blockers": [{"item": str, "date": _OPT_STR, "flag": str}],
                "warnings": [{"item": str, "date": _OPT_STR, "flag": str}],
                "note": (str, _NONE),
            },
        ),
    )
}


def user_has_any_tool_permission(user):
    """¿Puede esta persona usar AL MENOS una herramienta? Decide si se dibuja el panel."""
    return bool(
        user is not None
        and getattr(user, "is_authenticated", False)
        and any(user.has_perm(tool.permission) for tool in TOOLS.values())
    )


def tool_definitions():
    """La lista que se le ofrece al modelo, en el formato de «functions» de OpenAI."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }
        for tool in TOOLS.values()
    ]


MAX_CITATIONS = 25

# Una cita por herramienta: `(nombre de URL, clave de la fila con la etiqueta)`. El SERVIDOR
# arma el enlace con `reverse`; el modelo nunca escribe una URL. Una etiqueta `None` es una
# cita a una lista sin `pk` (conteos), y sólo sale si hay algo que contar.
CITATION_ROUTES = {
    "expiring_permits": ("permission-detail", "permit"),
    "upcoming_maintenance": ("maintenance-detail", "registration"),
    "expiring_company_documents": ("document-detail", "doc_type"),
    "aircraft_insurance_status": ("aircraft-detail", "registration"),
    "flight_requests_status": ("flight-request-detail", "cost_centre"),
    "aircraft_readiness": ("aircraft-detail", "registration"),
    "open_alerts_by_urgency": ("alert-list", None),
}


def _rows_of(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if isinstance(data.get("rows"), list):
            return data["rows"]
        if "pk" in data:
            return [data]
    return []


def citations_for(name, data):
    """Las citas de lo que devolvió una herramienta: `[{"label", "url"}]`.

    Las arma el servidor con `reverse()` a partir de **datos que la herramienta ya acotó por
    tenant**; el texto del modelo no interviene, así que no puede inyectar un enlace. Sólo
    se acepta un `pk` con forma de UUID.
    """
    route = CITATION_ROUTES.get(name)
    if route is None:
        return []
    url_name, label_key = route
    if label_key is None:
        if isinstance(data, dict) and data.get("total"):
            return [{"label": str(_("Open alerts")), "url": reverse(url_name)}]
        return []
    cites = []
    for row in _rows_of(data):
        try:
            pk = UUID(str(row.get("pk")))
        except (AttributeError, ValueError):
            continue
        cites.append(
            {
                "label": str(row.get(label_key) or ""),
                "url": reverse(url_name, args=[pk]),
            }
        )
    return cites[:MAX_CITATIONS]


def run_tool(user, name, raw_arguments):
    """Sólo el texto JSON de `execute_tool` (lo que ve el modelo)."""
    return execute_tool(user, name, raw_arguments)[0]


def execute_tool(user, name, raw_arguments):
    """Ejecuta una herramienta pedida por el modelo: `(texto JSON acotado, citas)`.

    Nunca levanta: un nombre desconocido, argumentos mal formados o falta de permiso se
    devuelven al modelo como un error legible para que lo diga, no como una excepción.
    """
    tool = TOOLS.get(name)
    if tool is None:
        return json.dumps({"error": "unknown tool"}), []
    if not user.has_perm(tool.permission):
        return json.dumps({"error": "this user has no permission for that data"}), []
    try:
        arguments = json.loads(raw_arguments) if raw_arguments else {}
        if not isinstance(arguments, dict):
            arguments = {}
    except ValueError:
        arguments = {}
    try:
        trimmed = []
        data = _validate(tool.run(user, arguments), tool.schema, trimmed)
        text = _envelope(data, bool(trimmed))
        if text.startswith('{"error"'):
            return text, []
        # Las citas salen de las filas que realmente se entregaron (tras el recorte).
        return text, citations_for(name, data)
    except Exception:  # noqa: BLE001 - la IA no debe poder romper la pantalla
        return json.dumps({"error": "the data could not be read"}), []
