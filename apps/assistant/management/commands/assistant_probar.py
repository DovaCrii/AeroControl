"""Diagnóstico del asistente IA (LV-336), como `teo_probar` de AeroAcademy.

Sin `--ping` no llama a nada: sólo informa la configuración vigente. Con `--ping` hace UNA llamada
mínima al servicio e informa latencia y tokens.

⚠️ Nunca imprime la llave ni el texto que devuelve el modelo: sólo si la llave existe, el modelo, la
URL base, el estado del interruptor, los topes y, con `--ping`, el resultado de la llamada.
"""

import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.assistant.client import AssistantUnavailable, NvidiaClient
from apps.assistant.views import assistant_available


class Command(BaseCommand):
    help = "Reports the assistant configuration; with --ping makes ONE minimal call to the service."

    def add_arguments(self, parser):
        parser.add_argument(
            "--ping",
            action="store_true",
            help="Make one minimal call to the service and report latency and tokens.",
        )

    def handle(self, *args, **options):
        client = NvidiaClient()
        out = self.stdout.write

        def cap(value):
            return str(value) if value else "off (0)"

        out(f"key: {'present' if client.configured else 'MISSING'}")
        out(f"model: {client.model}")
        out(f"base_url: {client.base_url}")
        out(f"AI_ASSISTANT_ENABLED: {bool(settings.AI_ASSISTANT_ENABLED)}")
        out(
            f"AI_ASSISTANT_ALLOW_PRODUCTION: {bool(settings.AI_ASSISTANT_ALLOW_PRODUCTION)}"
        )
        out(f"DEBUG: {bool(settings.DEBUG)}")
        out(f"switch: {'OPEN' if assistant_available() else 'CLOSED'}")
        out(f"cap_per_hour_per_user: {cap(settings.AI_ASSISTANT_MAX_PER_HOUR)}")
        out(f"cap_per_day_global: {cap(settings.AI_ASSISTANT_DAILY_CAP)}")

        if not options["ping"]:
            return
        if not client.configured:
            raise CommandError("ping: not configured (no key in this environment).")
        started = time.monotonic()
        try:
            message = client.chat([{"role": "user", "content": "ping"}])
        except AssistantUnavailable as error:
            # Sólo el código de la falla (p. ej. http-401), nunca el cuerpo ni la llave.
            raise CommandError(f"ping: failed ({error}).") from None
        ms = round((time.monotonic() - started) * 1000)
        tokens = message.get("_total_tokens")
        out(f"ping: ok, {ms} ms, tokens: {tokens if tokens is not None else 'unknown'}")
