"""El ciclo del asistente: pregunta → herramientas de solo lectura → respuesta.

PROTOTIPO (`LV-305`), sólo para el demo. Ver `docs/dev/asistente-ia.md`.

Cómo se mantiene acotado:
- **Tope de vueltas** (`MAX_ROUNDS`): si el modelo sigue pidiendo herramientas, se corta.
- **El modelo sólo ve lo que devuelven las herramientas** (`tools.py`), ya acotado y sin datos
  personales; la pregunta de la persona es lo único libre que viaja.
- **Las instrucciones piden no inventar**: si la herramienta no trae el dato, se dice.
- **No se guarda la pregunta ni la respuesta**: se registra quién, cuántas herramientas y cuánto
  tardó, nunca el texto (una pregunta puede nombrar a alguien).
"""

import logging
import time
from dataclasses import dataclass, field

from django.conf import settings
from django.core.cache import cache
from django.utils.translation import gettext as _

from .client import AssistantUnavailable, NvidiaClient
from .tools import run_tool, tool_definitions

logger = logging.getLogger(__name__)

MAX_ROUNDS = 4
MAX_QUESTION_CHARS = 500

SYSTEM_PROMPT = (
    "Eres el asistente de consulta de AeroControl, una aplicación interna de operaciones con "
    "drones (RPA) en Chile. Responde en español neutro, breve y claro. Usa SOLO los datos que "
    "devuelvan las herramientas: si no tienes el dato, di que no lo tienes y no lo inventes. "
    "No des consejos legales ni declares que algo cumple una norma: describe los datos y "
    "deja la decisión a la persona. Las fechas están en formato año-mes-día."
)


@dataclass
class Answer:
    text: str
    tools_used: list = field(default_factory=list)
    ok: bool = True


def ask(user, question, client=None):
    """Contesta `question` para `user`. Nunca levanta: un fallo se vuelve un texto neutro."""
    client = client or NvidiaClient()
    if not client.configured:
        return Answer(
            _(
                "The assistant is not configured: the NVIDIA key is missing in this "
                "environment."
            ),
            ok=False,
        )

    started = time.monotonic()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    tools_used = []
    tokens = 0
    try:
        for _round in range(MAX_ROUNDS):
            if _over_the_hourly_cap(user):
                return _finish(
                    user,
                    started,
                    tools_used,
                    _("You have asked too many questions this hour. Try again later."),
                    ok=False,
                    tokens=tokens,
                )
            message = client.chat(messages, tools=tool_definitions())
            tokens += message.pop("_total_tokens", 0) or 0
            calls = message.get("tool_calls") or []
            if not calls:
                text = (message.get("content") or "").strip()
                return _finish(
                    user,
                    started,
                    tools_used,
                    text or _("The assistant returned no answer."),
                    ok=bool(text),
                    tokens=tokens,
                )
            messages.append(
                {
                    "role": "assistant",
                    "content": message.get("content") or "",
                    "tool_calls": calls,
                }
            )
            for call in calls:
                function = call.get("function") or {}
                name = function.get("name", "")
                tools_used.append(name)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id", ""),
                        "content": run_tool(user, name, function.get("arguments")),
                    }
                )
        return _finish(
            user,
            started,
            tools_used,
            _("The assistant needed too many steps. Try a simpler question."),
            ok=False,
            tokens=tokens,
        )
    except AssistantUnavailable as error:
        return _finish(
            user,
            started,
            tools_used,
            _unavailable_text(str(error)),
            ok=False,
            tokens=tokens,
        )


def _unavailable_text(reason):
    """Un texto propio según por qué falló, sin detalles técnicos ni nada de la petición.

    «Límite alcanzado» y «llave no aceptada» se distinguen porque se arreglan distinto: lo primero
    se espera (créditos o ritmo del servicio de prueba), lo segundo lo corrige quien administra
    el entorno.
    """
    if reason == "http-429":
        return _("The assistant reached its usage limit. Try again later.")
    if reason in ("http-401", "http-403"):
        return _(
            "The assistant's key was not accepted. Ask the administrator to check it."
        )
    return _("The assistant is not available right now. Try again in a moment.")


def _over_the_hourly_cap(user):
    """Cuenta UNA LLAMADA al servicio y dice si esta persona ya pasó su tope de la hora.

    Se cuenta por llamada y no por pregunta: una pregunta puede hacer hasta `MAX_ROUNDS`
    llamadas, y cada una cuesta. El tope por hora es entonces de llamadas, no de preguntas.

    ⚠️ El contador vive en la caché **por proceso**: con varios procesos de gunicorn el tope real
    es `AI_ASSISTANT_MAX_PER_HOUR` × procesos. Es aceptable sólo mientras el asistente esté
    limitado al demo. La persistencia en base (un registro de uso por llamada, compartido por
    todos los procesos) llega en el PR 2 del endurecimiento; no se inventa una tabla acá.
    Con el tope en 0 no cuenta nada.
    """
    cap = settings.AI_ASSISTANT_MAX_PER_HOUR
    if not cap:
        return False
    key = f"assistant:{getattr(user, 'pk', 'anon')}:{int(time.time() // 3600)}"
    cache.add(key, 0, timeout=3700)
    return cache.incr(key) > cap


def _finish(user, started, tools_used, text, ok, tokens=0):
    logger.info(
        "assistant_answered",
        extra={
            "user_id": getattr(user, "pk", None),
            "tools": tools_used,
            "ok": ok,
            "total_tokens": tokens,
            "ms": round((time.monotonic() - started) * 1000),
        },
    )
    return Answer(text=text, tools_used=tools_used, ok=ok)
