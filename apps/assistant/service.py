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
    try:
        for _round in range(MAX_ROUNDS):
            message = client.chat(messages, tools=tool_definitions())
            calls = message.get("tool_calls") or []
            if not calls:
                text = (message.get("content") or "").strip()
                return _finish(
                    user,
                    started,
                    tools_used,
                    text or _("The assistant returned no answer."),
                    ok=bool(text),
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
        )
    except AssistantUnavailable:
        return _finish(
            user,
            started,
            tools_used,
            _("The assistant is not available right now. Try again in a moment."),
            ok=False,
        )


def _finish(user, started, tools_used, text, ok):
    logger.info(
        "assistant_answered",
        extra={
            "user_id": getattr(user, "pk", None),
            "tools": tools_used,
            "ok": ok,
            "ms": round((time.monotonic() - started) * 1000),
        },
    )
    return Answer(text=text, tools_used=tools_used, ok=ok)
