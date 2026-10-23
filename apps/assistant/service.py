"""El ciclo del asistente: pregunta → herramientas de solo lectura → respuesta.

PROTOTIPO (`LV-305`), sólo para el demo. Ver `docs/dev/asistente-ia.md`.

Cómo se mantiene acotado:
- **Tope de vueltas** (`MAX_ROUNDS`): si el modelo sigue pidiendo herramientas, se corta.
- **El modelo sólo ve lo que devuelven las herramientas** (`tools.py`), ya acotado y sin datos
  personales; la pregunta de la persona es lo único libre que viaja.
- **Las instrucciones piden no inventar**: si la herramienta no trae el dato, se dice.
- **No se guarda la pregunta ni la respuesta**: se registra (`AssistantUsage`) quién, qué
  herramientas, cuántas llamadas y cuánto tardó, nunca el texto (una pregunta puede nombrar a
  alguien).
- **Topes en la base** (compartidos por todos los procesos): por persona y hora, y global por
  día, revisados antes de CADA llamada al servicio.
"""

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone
from django.utils.translation import gettext as _

from . import prompts
from .client import AssistantUnavailable, NvidiaClient
from .models import AssistantUsage
from .tools import execute_tool, tool_definitions

logger = logging.getLogger(__name__)

MAX_ROUNDS = 4
MAX_QUESTION_CHARS = 500
MAX_ANSWER_CHARS = 1500
# Fallos tras los cuales la llamada se devuelve al tope (no llegó a producir respuesta).
GIVE_BACK_REASONS = frozenset({"unreachable", "timeout", "http-429"})
_URL_RE = re.compile(r"(?:https?://|www\.)\S*", re.IGNORECASE)


def clean_model_text(text):
    """Lo que el servidor le hace al texto del modelo antes de mostrarlo (LV-345).

    Quita toda URL (los enlaces salen sólo de las citas armadas con `reverse()`) y recorta a
    `MAX_ANSWER_CHARS`. El escape HTML sigue siendo de la plantilla.
    """
    text = _URL_RE.sub("", text or "").strip()
    if len(text) > MAX_ANSWER_CHARS:
        text = text[: MAX_ANSWER_CHARS - 1].rstrip() + "…"
    return text


def default_client():
    """El cliente real, o el guionizado sólo con `AI_ASSISTANT_FAKE` **y** `DEBUG`."""
    if settings.AI_ASSISTANT_FAKE and settings.DEBUG:
        from .fake_client import ScriptedClient

        return ScriptedClient()
    return NvidiaClient()


@dataclass
class Answer:
    text: str
    tools_used: list = field(default_factory=list)
    ok: bool = True
    # Enlaces armados por el servidor desde lo que devolvieron las herramientas (nunca del texto
    # del modelo). `state`: "ok", "limit" (tope alcanzado) o "error".
    citations: list = field(default_factory=list)
    state: str = "ok"


def ask(user, question, client=None):
    """Contesta `question` para `user`. Nunca levanta: un fallo se vuelve un texto neutro."""
    client = client or default_client()
    if not client.configured:
        return Answer(
            _(
                "The assistant is not configured: the NVIDIA key is missing in this "
                "environment."
            ),
            ok=False,
            state="error",
        )

    started = time.monotonic()
    usage = AssistantUsage.objects.create(
        user=user if getattr(user, "pk", None) else None,
        model=str(getattr(client, "model", "") or "")[:100],
    )
    messages = [
        {"role": "system", "content": prompts.SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    tools_used = []
    citations = []
    tokens = 0
    try:
        for _round in range(MAX_ROUNDS):
            blocked = _reserve_call(usage)
            if blocked:
                return _finish(
                    usage,
                    started,
                    tools_used,
                    _blocked_text(blocked),
                    AssistantUsage.OUTCOME_LIMIT,
                    tokens,
                )
            try:
                message = client.chat(messages, tools=tool_definitions())
            except AssistantUnavailable as error:
                reason = str(error)
                if reason in GIVE_BACK_REASONS:
                    # Como en AeroAcademy: una llamada que no llegó a responder (red, tiempo
                    # agotado o límite de ritmo) no gasta tope. Un error del servicio (5xx,
                    # llave) sí cuenta: la llamada se hizo.
                    _give_back_call(usage)
                return _finish(
                    usage,
                    started,
                    tools_used,
                    _unavailable_text(reason),
                    _outcome_for(reason),
                    tokens,
                )
            tokens += message.pop("_total_tokens", 0) or 0
            used_model = message.pop("_model", "")
            if used_model and used_model != usage.model:
                # Respondió un modelo de respaldo: el registro dice cuál (sólo el id público).
                usage.model = used_model[:100]
                AssistantUsage.objects.filter(pk=usage.pk).update(model=usage.model)
            calls = message.get("tool_calls") or []
            if not calls:
                text = clean_model_text(message.get("content") or "")
                return _finish(
                    usage,
                    started,
                    tools_used,
                    text or _("The assistant returned no answer."),
                    AssistantUsage.OUTCOME_OK if text else AssistantUsage.OUTCOME_EMPTY,
                    tokens,
                    citations if text else [],
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
                content, cites = execute_tool(user, name, function.get("arguments"))
                for cite in cites:
                    if cite not in citations:
                        citations.append(cite)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id", ""),
                        "content": content,
                    }
                )
        return _finish(
            usage,
            started,
            tools_used,
            _("The assistant needed too many steps. Try a simpler question."),
            AssistantUsage.OUTCOME_TOO_MANY_STEPS,
            tokens,
        )
    except Exception:
        # Un fallo inesperado no deja la fila «en curso» para siempre.
        _finish(usage, started, tools_used, "", AssistantUsage.OUTCOME_ERROR, tokens)
        raise


def _outcome_for(reason):
    if reason == "http-429":
        return AssistantUsage.OUTCOME_429
    if reason in ("http-401", "http-403"):
        return AssistantUsage.OUTCOME_AUTH
    if reason in ("unreachable", "timeout"):
        return AssistantUsage.OUTCOME_UNREACHABLE
    return AssistantUsage.OUTCOME_ERROR


def _blocked_text(which):
    if which == "daily":
        return _("The assistant reached its daily limit. Try again tomorrow.")
    return _("You have asked too many questions this hour. Try again later.")


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
    if reason == "no-tools":
        return _(
            "The assistant's model cannot use the lookup tools. Ask the administrator "
            "to check the model list."
        )
    return _("The assistant is not available right now. Try again in a moment.")


def _reserve_call(usage):
    """Reserva UNA LLAMADA al servicio contra los topes; devuelve `None`, «daily» u «hourly».

    Se cuenta por llamada y no por pregunta: una pregunta puede hacer hasta `MAX_ROUNDS`
    llamadas, y cada una cuesta. Los topes se calculan sobre `AssistantUsage.rounds`, en la base
    y por lo tanto compartidos por todos los procesos; revisar y sumar ocurre en una misma
    transacción. Un tope en 0 desactiva ese tope.
    """
    now = timezone.now()
    with transaction.atomic():
        daily_cap = settings.AI_ASSISTANT_DAILY_CAP
        if daily_cap:
            start_of_day = timezone.localtime(now).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            used = AssistantUsage.objects.filter(
                created_at__gte=start_of_day
            ).aggregate(n=Sum("rounds"))["n"]
            if (used or 0) >= daily_cap:
                return "daily"
        hourly_cap = settings.AI_ASSISTANT_MAX_PER_HOUR
        if hourly_cap:
            used = AssistantUsage.objects.filter(
                user_id=usage.user_id, created_at__gte=now - timedelta(hours=1)
            ).aggregate(n=Sum("rounds"))["n"]
            if (used or 0) >= hourly_cap:
                return "hourly"
        AssistantUsage.objects.filter(pk=usage.pk).update(rounds=F("rounds") + 1)
    return None


def _give_back_call(usage):
    AssistantUsage.objects.filter(pk=usage.pk, rounds__gt=0).update(
        rounds=F("rounds") - 1
    )


def _finish(usage, started, tools_used, text, outcome, tokens=0, citations=()):
    ms = round((time.monotonic() - started) * 1000)
    AssistantUsage.objects.filter(pk=usage.pk).update(
        outcome=outcome,
        tools=tools_used,
        ms=ms,
        total_tokens=tokens or None,
    )
    logger.info(
        "assistant_answered",
        extra={
            "user_id": usage.user_id,
            "tools": tools_used,
            "ok": outcome == AssistantUsage.OUTCOME_OK,
            "outcome": outcome,
            "total_tokens": tokens,
            "ms": ms,
            "prompt_version": prompts.PROMPT_VERSION,
        },
    )
    ok = outcome == AssistantUsage.OUTCOME_OK
    if ok:
        state = "ok"
    elif outcome in (AssistantUsage.OUTCOME_LIMIT, AssistantUsage.OUTCOME_429):
        state = "limit"
    else:
        state = "error"
    return Answer(
        text=text,
        tools_used=tools_used,
        ok=ok,
        citations=list(citations),
        state=state,
    )
