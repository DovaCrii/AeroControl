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
        parser.add_argument(
            "--eval",
            action="store_true",
            help="Run the golden questions against the real service (needs --user); "
            "prints figures only, never the answer text.",
        )
        parser.add_argument(
            "--user", type=int, help="User id whose permissions --eval uses."
        )
        parser.add_argument(
            "--max",
            type=int,
            default=10,
            help="Most questions --eval asks (default 10).",
        )

    def _eval(self, options, client):
        """LV-345: el golden set contra el servicio REAL, con los permisos de `--user`.

        Respeta los topes y cuenta en `AssistantUsage` como cualquier pregunta. Por pregunta
        imprime SOLO «herramientas OK/KO, citas, longitud, ms, tokens»: nunca el texto de la
        respuesta ni la llave.
        """
        from django.contrib.auth import get_user_model

        from apps.assistant.evals.golden import GOLDEN, evaluate

        if not options["user"]:
            raise CommandError(
                "--eval needs --user <id>: it runs with that user's permissions."
            )
        if not client.configured:
            raise CommandError("eval: not configured (no key in this environment).")
        user = (
            get_user_model().objects.filter(pk=options["user"], is_active=True).first()
        )
        if user is None:
            raise CommandError("eval: no active user with that id.")
        limit = max(1, options["max"])
        cases = [case for case in GOLDEN if case.permissions is None][:limit]
        ok = 0
        for case in cases:
            result = evaluate(user, case, client=client)
            ok += bool(result["ok_tools"])
            self.stdout.write(
                f"{case.name}: tools {'OK' if result['ok_tools'] else 'KO'}, "
                f"citations {result['citations']}, length {result['length']}, "
                f"{result['ms']} ms, tokens {result['tokens'] if result['tokens'] is not None else 'unknown'}"
            )
        self.stdout.write(f"eval: {ok}/{len(cases)} with the expected tools")

    def handle(self, *args, **options):
        client = NvidiaClient()
        if options["eval"]:
            return self._eval(options, client)
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
