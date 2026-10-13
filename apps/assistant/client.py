"""Cliente mínimo del servicio de modelos de NVIDIA (compatible con OpenAI).

PROTOTIPO (`LV-305`), sólo para el demo. Usa `urllib` de la biblioteca estándar: el proyecto no
suma una dependencia para una llamada HTTP.

⚠️ **La llave nunca se registra ni se escribe en un mensaje de error.** Viene de `NVIDIA_API_KEY`
(entorno), no está en el repositorio, y este módulo no la vuelve a mostrar.

Cualquier fallo de red o respuesta ilegible se convierte en `AssistantUnavailable` con un texto
neutro: quien llama dibuja una pantalla normal, nunca un traceback.
"""

import json
import logging
import urllib.error
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

# Una respuesta del modelo con herramientas es corta; más de esto es un error o un abuso.
MAX_RESPONSE_BYTES = 256_000


class AssistantUnavailable(Exception):
    """El servicio no está configurado o no respondió: se dice sin detalles técnicos."""


class NvidiaClient:
    def __init__(self, api_key=None, base_url=None, model=None, timeout=None):
        self.api_key = api_key if api_key is not None else settings.NVIDIA_API_KEY
        self.base_url = (base_url or settings.NVIDIA_BASE_URL).rstrip("/")
        self.model = model or settings.NVIDIA_MODEL
        self.timeout = timeout or settings.AI_ASSISTANT_TIMEOUT

    @property
    def configured(self):
        return bool(self.api_key)

    def chat(self, messages, tools=None):
        """Una llamada de chat; devuelve el `message` del modelo (un diccionario)."""
        if not self.configured:
            raise AssistantUnavailable("not-configured")
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 700,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        request = urllib.request.Request(  # noqa: S310 - la URL es de configuración, no del usuario
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310  # nosec B310
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as error:
            # Sólo el código: el cuerpo puede traer eco de la petición.
            logger.warning("assistant_http_error", extra={"status": error.code})
            raise AssistantUnavailable(f"http-{error.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            logger.warning("assistant_unreachable")
            raise AssistantUnavailable("unreachable") from None
        if len(raw) > MAX_RESPONSE_BYTES:
            raise AssistantUnavailable("too-large")
        try:
            return json.loads(raw)["choices"][0]["message"]
        except (ValueError, KeyError, IndexError, TypeError):
            raise AssistantUnavailable("unreadable") from None
