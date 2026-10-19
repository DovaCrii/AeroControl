"""Herramientas de SOLO LECTURA que el asistente puede pedir.

PROTOTIPO (`LV-305`). El modelo **nunca** toca la base: sólo puede pedir estas funciones, que
reutilizan los mismos cálculos que el panel (`apps.compliance.kpis`) y devuelven **datos
agregados o no personales**. Reglas que no se rompen:

- **Cada herramienta declara el permiso** que exige; el servicio lo comprueba contra el usuario
  que pregunta antes de ejecutarla (la IA no amplía lo que esa persona puede ver).
- **Nada personal sale hacia el servicio externo**: ni nombres de operadores, ni RUT, ni correos,
  ni teléfonos, ni el nombre de la faena (dato del cliente). Sólo folios internos, códigos de
  faena y fechas. Un guardián de pruebas lo vigila en las tres herramientas.
- **Cada herramienta acota por la empresa (tenant) de quien pregunta**, igual que el panel y
  `expiring_permits`: con dos empresas, ninguna ve los permisos de la otra (`LV-323`).
- **Salida acotada**: listas con tope y números, nunca tablas enteras.
- **Ninguna herramienta escribe.** Agregar una que escriba exige una decisión explícita del
  usuario: una máquina que aprueba o declara cumplimiento es lo contrario de la evidencia.
"""

import json
from dataclasses import dataclass
from datetime import timedelta
from typing import Callable
from uuid import UUID

from django.urls import reverse
from django.utils import timezone

from apps.core.tenancy import scope_queryset_to_tenant

MAX_ROWS = 25
MAX_DAYS = 365


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict
    permission: str
    run: Callable


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
            "code": row["cost_center"].code,
            "in_force": row["in_force"],
            "not_started": row["not_started"],
            "awaiting": row["awaiting"],
            "expiring_in_30_days": row["soon"],
            "next_expiry": (
                row["next_expiry"].isoformat() if row["next_expiry"] else None
            ),
        }
        for row in rows[:MAX_ROWS]
    ]


def _expiring_permits(user, arguments):
    from apps.operations.models import FlightPermission

    try:
        days = int(arguments.get("days", 30))
    except (TypeError, ValueError):
        days = 30
    days = max(1, min(days, MAX_DAYS))
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
            "permit": permit.internal_folio,
            "cost_centre": permit.cost_center.code,
            "valid_until": permit.valid_until.isoformat(),
            "days_left": (permit.valid_until - today).days,
        }
        for permit in permits.select_related("cost_center").order_by("valid_until")[
            :MAX_ROWS
        ]
    ]


TOOLS = {
    tool.name: tool
    for tool in (
        Tool(
            name="permits_summary",
            description=(
                "Resumen de permisos de vuelo: cuántos hay vigentes, aún sin empezar, "
                "esperando respuesta de la DGAC, por vencer en 30 días y atrasados."
            ),
            parameters={"type": "object", "properties": {}},
            permission="operations.view_flightpermission",
            run=_permits_summary,
        ),
        Tool(
            name="cost_centres_permit_status",
            description=(
                "Estado de permisos por centro de costo (faena): vigentes, esperando, "
                "por vencer y próximo vencimiento. Sirve para saber qué faenas no tienen "
                "permiso vigente."
            ),
            parameters={"type": "object", "properties": {}},
            permission="operations.view_flightpermission",
            run=_cost_centres_status,
        ),
        Tool(
            name="expiring_permits",
            description=(
                "Permisos aprobados que vencen dentro de los próximos N días, ordenados "
                "por fecha de término."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Ventana en días (1 a 365). Por omisión 30.",
                    }
                },
            },
            permission="operations.view_flightpermission",
            run=_expiring_permits,
        ),
    )
}


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


def citations_for(name, data):
    """Las citas de lo que devolvió una herramienta: `[{"label", "url"}]`.

    Las arma el servidor con `reverse()` a partir de **datos que la herramienta ya acotó por
    tenant**; el texto del modelo no interviene, así que no puede inyectar un enlace. Sólo
    se acepta un `pk` con forma de UUID.
    """
    if name != "expiring_permits" or not isinstance(data, list):
        return []
    cites = []
    for row in data:
        try:
            pk = UUID(str(row.get("pk")))
        except (AttributeError, ValueError):
            continue
        cites.append(
            {
                "label": str(row.get("permit") or ""),
                "url": reverse("permission-detail", args=[pk]),
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
        data = tool.run(user, arguments)
        return json.dumps(data, ensure_ascii=False)[:6000], citations_for(name, data)
    except Exception:  # noqa: BLE001 - la IA no debe poder romper la pantalla
        return json.dumps({"error": "the data could not be read"}), []
