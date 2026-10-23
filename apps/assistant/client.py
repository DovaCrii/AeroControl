"""Cliente mínimo del servicio de modelos de NVIDIA (compatible con OpenAI).

PROTOTIPO (`LV-305`), sólo para el demo. Usa `urllib` de la biblioteca estándar: el proyecto no
suma una dependencia para una llamada HTTP.

⚠️ **La llave nunca se registra ni se escribe en un mensaje de error.** Viene de `NVIDIA_API_KEY`
(entorno), no está en el repositorio, y este módulo no la vuelve a mostrar. Tampoco se registra el
cuerpo de ninguna respuesta de error (puede traer eco de la petición).

Endurecimiento (`LV-362`), tomado de cómo lo usa AeroAcademy:
- **Cadena de modelos** (`NVIDIA_MODEL` + `NVIDIA_MODEL_FALLBACKS`): se pasa al siguiente ante un
  404/410 (modelo retirado), una respuesta vacía o sólo razonamiento.
- **Herramientas**: un modelo que rechaza `tools` no sirve para el bucle de consulta; se recuerda
  (por proceso) y se salta. Si ninguno de la cadena las admite, el error es claro (`no-tools`).
- **`enable_thinking: false`** en cada petición; si el modelo contesta 400/422 a esa opción, se
  reintenta sin ella y, si así funciona, se recuerda.
- **`strip_reasoning`** (pura): quita `<think>…</think>` y el razonamiento filtrado sin etiquetas.
- **429**: reintento acotado con espera corta (`AI_ASSISTANT_RETRIES_429`, máximo `MAX_RETRIES_429`).

Cualquier fallo de red o respuesta ilegible se convierte en `AssistantUnavailable` con un texto
neutro: quien llama dibuja una pantalla normal, nunca un traceback.
"""

import contextlib
import json
import logging
import re
import time
import urllib.error
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

# Una respuesta del modelo con herramientas es corta; más de esto es un error o un abuso.
MAX_RESPONSE_BYTES = 256_000
# La lista de `/models` es más larga que una respuesta de chat.
MAX_MODELS_BYTES = 2_000_000
# Techo de reintentos ante 429, sea lo que diga la configuración.
MAX_RETRIES_429 = 2
# Ninguna espera individual pasa de esto, aunque el servicio pida más.
MAX_BACKOFF_SECONDS = 4.0

# Por proceso: modelos que rechazaron `enable_thinking` o `tools`. Se recuerdan para no repetir la
# petición que ya se sabe que falla. Sólo se agrega un modelo cuando el reintento lo confirmó.
_THINKING_UNSUPPORTED = set()
_TOOLS_UNSUPPORTED = set()

_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)
_LEAKED_REASONING_RE = re.compile(
    r"^\s*(?:here(?:'|’)s|here is) a thinking process|^\s*thinking process\s*:",
    re.IGNORECASE,
)


def strip_reasoning(text):
    """Deja sólo la respuesta: quita el razonamiento que algunos modelos incluyen.

    Pura. Casos: bloques `<think>…</think>`; un `</think>` sin apertura (se toma lo que sigue); un
    `<think>` sin cierre (todo era razonamiento); y razonamiento filtrado sin etiquetas, que
    empieza con «Here's a thinking process…». Si no queda respuesta, devuelve `""`: quien llama
    pasa al siguiente modelo.
    """
    text = text or ""
    text = _THINK_BLOCK_RE.sub("", text)
    lowered = text.lower()
    if "</think>" in lowered:
        text = text[lowered.rindex("</think>") + len("</think>") :]
    elif "<think>" in lowered:
        text = text[: lowered.index("<think>")]
    text = text.strip()
    if _LEAKED_REASONING_RE.search(text):
        return ""
    return text


class AssistantUnavailable(Exception):
    """El servicio no está configurado o no respondió: se dice sin detalles técnicos.

    `str(error)` es el código corto (`unreachable`, `timeout`, `http-429`…) y `kind` la clase de
    error tipada: `timeout`, `auth`, `rate`, `http`, `bad_response`, `network` o `not_configured`.
    """

    @property
    def kind(self):
        reason = str(self)
        if reason == "timeout":
            return "timeout"
        if reason == "unreachable":
            return "network"
        if reason in ("http-401", "http-403"):
            return "auth"
        if reason == "http-429":
            return "rate"
        if reason == "not-configured":
            return "not_configured"
        if reason.startswith("http-") or reason == "no-tools":
            return "http"
        return "bad_response"


class _Rejected(Exception):
    """El servicio respondió con un estado que decide quien arma la cadena (no se muestra)."""

    def __init__(self, status, mentions_tools=False):
        super().__init__(status)
        self.status = status
        self.mentions_tools = mentions_tools


class _Fallback(Exception):
    """Este modelo no sirve para esta petición: pasar al siguiente de la cadena."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def _sleep(seconds):
    time.sleep(seconds)


def parse_model_list(raw):
    """`NVIDIA_MODEL_FALLBACKS` (lista separada por comas) → lista limpia y sin repetidos."""
    seen = []
    for item in (raw or "").split(","):
        item = item.strip()
        if item and item not in seen:
            seen.append(item)
    return seen


class NvidiaClient:
    def __init__(
        self, api_key=None, base_url=None, model=None, timeout=None, fallbacks=None
    ):
        self.api_key = api_key if api_key is not None else settings.NVIDIA_API_KEY
        self.base_url = (base_url or settings.NVIDIA_BASE_URL).rstrip("/")
        self.model = model or settings.NVIDIA_MODEL
        self.timeout = timeout or settings.AI_ASSISTANT_TIMEOUT
        if fallbacks is None:
            fallbacks = parse_model_list(settings.NVIDIA_MODEL_FALLBACKS)
        self.models = [self.model]
        for name in fallbacks:
            if name not in self.models:
                self.models.append(name)

    @property
    def configured(self):
        return bool(self.api_key)

    # --- HTTP -----------------------------------------------------------------------------

    def _headers(self):
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    def _open(self, request, limit):
        """Una petición HTTP; devuelve los bytes o levanta `AssistantUnavailable`/`_Rejected`."""
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310  # nosec B310
                raw = response.read(limit + 1)
        except urllib.error.HTTPError as error:
            status = error.code
            if status in (404, 410):
                raise _Rejected(status) from None
            if status in (400, 422):
                # El cuerpo sólo sirve para saber si habla de «tools»; nunca se registra.
                body = b""
                with contextlib.suppress(Exception):
                    body = error.read(2000)
                raise _Rejected(
                    status, mentions_tools=b"tool" in (body or b"").lower()
                ) from None
            # Sólo el código: el cuerpo puede traer eco de la petición.
            logger.warning("assistant_http_error", extra={"status": status})
            raise AssistantUnavailable(f"http-{status}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            reason = getattr(error, "reason", None)
            if isinstance(error, TimeoutError) or isinstance(reason, TimeoutError):
                logger.warning("assistant_timeout")
                raise AssistantUnavailable("timeout") from None
            logger.warning("assistant_unreachable")
            raise AssistantUnavailable("unreachable") from None
        if len(raw) > limit:
            raise AssistantUnavailable("too-large")
        return raw

    def _open_with_backoff(self, request, limit):
        """Reintenta ante 429 (máx. `MAX_RETRIES_429`) con espera corta y creciente."""
        retries = max(0, min(int(settings.AI_ASSISTANT_RETRIES_429), MAX_RETRIES_429))
        backoff = max(0.0, float(settings.AI_ASSISTANT_RETRY_BACKOFF))
        attempt = 0
        while True:
            try:
                return self._open(request, limit)
            except AssistantUnavailable as error:
                if str(error) != "http-429" or attempt >= retries:
                    raise
                _sleep(min(backoff * (2**attempt), MAX_BACKOFF_SECONDS))
                attempt += 1

    def _post(self, model, messages, tools, thinking):
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 700,
        }
        if thinking:
            payload["chat_template_kwargs"] = {"enable_thinking": False}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        request = urllib.request.Request(  # noqa: S310 - la URL es de configuración, no del usuario
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        return self._open_with_backoff(request, MAX_RESPONSE_BYTES)

    # --- Un modelo ------------------------------------------------------------------------

    def _call_model(self, model, messages, tools):
        """Una llamada a UN modelo. Devuelve el `message`; `_Fallback` si hay que pasar al siguiente."""
        thinking = model not in _THINKING_UNSUPPORTED
        retried_without_thinking = False
        while True:
            try:
                raw = self._post(model, messages, tools, thinking)
                break
            except _Rejected as rejected:
                if rejected.status in (404, 410):
                    raise _Fallback("gone") from None
                # 400/422: lo primero que se sospecha es la opción de «pensar».
                if thinking:
                    thinking = False
                    retried_without_thinking = True
                    continue
                if tools and rejected.mentions_tools:
                    _TOOLS_UNSUPPORTED.add(model)
                    raise _Fallback("no-tools") from None
                raise AssistantUnavailable(f"http-{rejected.status}") from None
        if retried_without_thinking:
            _THINKING_UNSUPPORTED.add(model)
        try:
            data = json.loads(raw)
            message = dict(data["choices"][0]["message"])
        except (ValueError, KeyError, IndexError, TypeError):
            raise AssistantUnavailable("unreadable") from None
        usage = data.get("usage") if isinstance(data, dict) else None
        total = usage.get("total_tokens") if isinstance(usage, dict) else None
        content = message.get("content")
        content = strip_reasoning(content) if isinstance(content, str) else ""
        message["content"] = content or None
        if not content and not message.get("tool_calls"):
            raise _Fallback("empty")
        message["_model"] = model
        if isinstance(total, int) and not isinstance(total, bool) and total >= 0:
            message["_total_tokens"] = total
        return message

    # --- API pública ----------------------------------------------------------------------

    def chat(self, messages, tools=None):
        """Una llamada de chat; devuelve el `message` del modelo (un diccionario).

        Recorre la cadena de modelos. Con `tools`, los modelos que ya rechazaron herramientas se
        saltan. Agrega `_model` (el que respondió) y, si el servicio informa
        `usage.total_tokens`, `_total_tokens`; ninguna de las dos claves se reenvía al modelo.
        Si todos devolvieron vacío, devuelve un mensaje sin contenido (el servicio lo trata como
        «sin respuesta»).
        """
        if not self.configured:
            raise AssistantUnavailable("not-configured")
        reasons = []
        for model in self.models:
            if tools and model in _TOOLS_UNSUPPORTED:
                reasons.append("no-tools")
                continue
            try:
                return self._call_model(model, messages, tools)
            except _Fallback as fallback:
                reasons.append(fallback.reason)
                logger.warning(
                    "assistant_model_skipped",
                    extra={"model": model, "reason": fallback.reason},
                )
        if reasons and all(reason == "no-tools" for reason in reasons):
            raise AssistantUnavailable("no-tools")
        if "empty" in reasons:
            return {"role": "assistant", "content": None, "_model": self.models[-1]}
        raise AssistantUnavailable("http-404")

    def list_models(self):
        """Los identificadores que informa `GET /models`, ordenados. Sólo ids públicos."""
        if not self.configured:
            raise AssistantUnavailable("not-configured")
        request = urllib.request.Request(  # noqa: S310 - la URL es de configuración
            f"{self.base_url}/models",
            headers=self._headers(),
            method="GET",
        )
        try:
            raw = self._open_with_backoff(request, MAX_MODELS_BYTES)
        except _Rejected as rejected:
            raise AssistantUnavailable(f"http-{rejected.status}") from None
        try:
            data = json.loads(raw)["data"]
            return sorted(
                {item["id"] for item in data if isinstance(item.get("id"), str)}
            )
        except (ValueError, KeyError, TypeError, AttributeError):
            raise AssistantUnavailable("unreadable") from None
