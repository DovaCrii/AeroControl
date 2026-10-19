"""Cliente guionizado del asistente (LV-345): sin servicio, sin llave, sin red.

Hace de «modelo» con un guion: elige la herramienta por palabras clave de la pregunta y,
cuando el servicio ya la ejecutó (de verdad, sobre la base y con los permisos de la persona),
arma la respuesta con plantillas `gettext`. Sirve para el demo y para probar el ciclo, los
permisos y las citas; NO mide la calidad de ningún modelo.

Se activa SÓLO con `AI_ASSISTANT_FAKE=1` **y** `DEBUG` (`service.default_client`). Fuera de
`DEBUG` se ignora y `manage.py check` avisa, para que nadie crea que lo tiene encendido.
"""

import json
import re
import unicodedata

from django.conf import settings
from django.core import checks
from django.utils.translation import gettext as _


@checks.register()
def check_fake_client_only_in_debug(app_configs, **kwargs):
    if getattr(settings, "AI_ASSISTANT_FAKE", False) and not settings.DEBUG:
        return [
            checks.Warning(
                "AI_ASSISTANT_FAKE is set but DEBUG is off: the scripted assistant "
                "client is ignored outside DEBUG.",
                hint="Unset AI_ASSISTANT_FAKE in this environment.",
                id="assistant.W001",
            )
        ]
    return []


_PERSON_RE = re.compile(
    r"\b(?:piloto|operador|persona|quien|licencia|empleado)|\brut\b"
)
_REGISTRATION_RE = re.compile(r"\bRPA-[A-Za-z0-9]+\b", re.IGNORECASE)

# `(palabras clave, herramienta)`, en orden: gana la primera que coincida.
_ROUTES = (
    (("puede volar", "listo para volar", "lista para volar", "readiness"), None),
    (("seguro",), "aircraft_insurance_status"),
    (("mantencion", "mantenimiento"), "upcoming_maintenance"),
    (("document",), "expiring_company_documents"),
    (("alerta",), "open_alerts_by_urgency"),
    (("solicitud", "sigo"), "flight_requests_status"),
    (("disponib", "flota"), "fleet_availability"),
    (("faena", "centro de costo"), "cost_centres_permit_status"),
    (("vence", "vencen", "vencer", "vencimiento"), "expiring_permits"),
    (("permiso",), "permits_summary"),
)


def _plain(text):
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def _final(text):
    return {"role": "assistant", "content": text}


def _call(name, arguments=None):
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "scripted-1",
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments or {})},
            }
        ],
    }


class ScriptedClient:
    configured = True
    model = "scripted"

    def chat(self, messages, tools=None):
        last = messages[-1]
        if last["role"] == "tool":
            return _final(self._answer(messages))
        question = last.get("content") or ""
        plain = _plain(question)
        if _PERSON_RE.search(plain):
            return _final(
                _(
                    "People are not available in the assistant. Please check the "
                    "operators screen."
                )
            )
        registration = _REGISTRATION_RE.search(question)
        if registration:
            return _call("aircraft_readiness", {"registration": registration.group(0)})
        for words, tool in _ROUTES:
            if any(word in plain for word in words):
                if tool is None:
                    break  # «¿puede volar?» sin matrícula: se pide la matrícula
                return _call(tool)
        if any(word in plain for word in _ROUTES[0][0]):
            return _final(
                _("Please give the aircraft registration, for example RPA-1234.")
            )
        return _final(
            _(
                "That is outside what I can look up here. I can help with flight "
                "permits, maintenance, company and aircraft documents and insurance, "
                "alerts by urgency, SIGO requests and fleet availability."
            )
        )

    def _answer(self, messages):
        names = {}
        for message in messages:
            for call in message.get("tool_calls") or []:
                names[call["id"]] = call["function"]["name"]
        parts = []
        for message in messages:
            if message["role"] != "tool":
                continue
            parts.append(
                _render(
                    names.get(message.get("tool_call_id"), ""),
                    json.loads(message["content"]),
                )
            )
        return " ".join(parts)


def _render(name, payload):
    if "error" in payload:
        return _("I cannot read that data with your permissions.")
    data = payload.get("data")
    n = len(data) if isinstance(data, list) else 0
    if name == "permits_summary":
        return _(
            "Flight permits: %(in_force)s in force, %(soon)s expiring in 30 days, "
            "%(lapsed)s lapsed."
        ) % {key: data.get(key) for key in ("in_force", "soon", "lapsed")}
    if name == "fleet_availability":
        return _("Fleet: %(available)s of %(total)s aircraft available.") % data
    if name == "open_alerts_by_urgency":
        return _("Open alerts: %(total)s.") % data
    if name == "flight_requests_status":
        return _("SIGO requests: %(total)s.") % data
    if name == "aircraft_readiness":
        if not data.get("found"):
            return _("No aircraft with that registration was found.")
        if data.get("nothing_in_records_prevents_flight"):
            return _("For %(registration)s, nothing in the records prevents it.") % data
        return _("For %(registration)s, the records show %(n)s blocking item(s).") % {
            "registration": data.get("registration"),
            "n": len(data.get("blockers") or []),
        }
    templates = {
        "expiring_permits": _("Permits expiring soon: %(n)s."),
        "upcoming_maintenance": _("Upcoming or overdue maintenance: %(n)s."),
        "expiring_company_documents": _("Company documents expiring: %(n)s."),
        "aircraft_insurance_status": _("Aircraft with insurance data: %(n)s."),
        "cost_centres_permit_status": _("Cost centres listed: %(n)s."),
    }
    return templates.get(name, _("Records found: %(n)s.")) % {"n": n}
