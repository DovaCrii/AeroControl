"""R5: congelar el informe mensual RPA desde un trabajo programado.

El informe se emite el día 5 de cada mes con corte al último día del anterior
(`_canvas_layout.json` del diseño: *"formato de emisión mensual: una página,
corte al último día del mes, emisión el día 5"*). Este comando es lo que lo
congela para que la persona que firma llegue a una pantalla con las cifras ya
fijas en vez de a una vista previa que se mueve mientras la lee.

**Congela, no aprueba.** Aprobar es un acto de una persona —el informe va
firmado ante la DGAC— y un trabajo nocturno no puede hacerlo en nombre de nadie.
El comando deja el borrador; la aprobación es la vista.

**Es idempotente, y de eso depende que pueda ser un timer.** Correrlo dos veces
sobre el mismo período no crea dos informes: devuelve el que hay y lo dice. Un
reintento del scheduler, o dos timers solapados, no pueden partir en dos un
documento controlado.
"""

import logging
from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.core.jobs import record_job_run
from apps.reporting.models import ReportRun
from apps.reporting.views import PERIOD, previous_month

logger = logging.getLogger("aerocontrol.notifications")

# Queda escrito como autor de la fila. No el `"system"` genérico: quien lea el
# informe tiene que ver **qué** lo generó, no sólo que no fue una persona.
ACTOR = "generate_monthly_report"


class Command(BaseCommand):
    help = "Freeze the monthly RPA report for a period, without approving it."

    def add_arguments(self, parser):
        parser.add_argument(
            "--period",
            help="Period to freeze, as YYYY-MM. Defaults to the month just closed.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help=(
                "Issue the next revision instead of doing nothing. The earlier "
                "revisions are kept and marked superseded, never overwritten."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Say what would happen without writing anything.",
        )

    def handle(self, *args, **options):
        period = self._period(options.get("period"))
        force = options["force"]
        dry_run = options["dry_run"]

        with record_job_run(ACTOR) as run:
            latest = (
                ReportRun.objects.filter(period=period).order_by("-revision").first()
            )
            if latest and not force:
                # **No es un error y no sale con código distinto de cero**: es el
                # resultado normal de un timer que ya corrió. Fallar acá haría
                # que el scheduler marcara en rojo la noche en que todo salió
                # bien, y un rojo que aparece todos los meses se deja de mirar.
                message = (
                    f"{latest.code} rev. {latest.revision} ya existe "
                    f"({latest.get_status_display()}). Sin cambios; "
                    f"usá --force para emitir la revisión siguiente."
                )
                run["summary"] = message
                self.stdout.write(message)
                return

            if dry_run:
                what = f"revisión {latest.revision + 1}" if latest else "revisión 0"
                message = f"[dry-run] Se congelaría {period:%Y-%m} como {what}."
                run["summary"] = message
                self.stdout.write(message)
                return

            report, created = ReportRun.freeze(period, ACTOR, force=force)
            # `created` no puede ser falso acá —los dos caminos que devuelven el
            # existente ya salieron arriba— y se afirma en vez de suponerse: si
            # `freeze` cambiara, esto lo dice en la corrida y no tres meses
            # después en una cifra rara.
            if not created:  # pragma: no cover - defensivo
                raise CommandError("freeze() devolvió un informe que ya existía.")

            missing = len(report.missing_fields)
            message = (
                f"{report.code} rev. {report.revision} congelado. "
                f"{missing} campo(s) sin dato al corte "
                f"({report.get_completeness_display()})."
            )
            run["summary"] = message
            logger.info("monthly_report_frozen", extra={"code": report.code})
            self.stdout.write(self.style.SUCCESS(message))
            # El aviso va después del éxito y no en lugar de él: el informe se
            # congeló igual, y lo que falta es carga de datos, no un fallo del
            # trabajo. `missing_fields` queda guardado y el documento dice qué
            # faltaba **cuando se emitió**.
            if missing:
                self.stdout.write(
                    self.style.WARNING(
                        "Los campos sin dato salen en ámbar punteado, nunca como cero."
                    )
                )

    @staticmethod
    def _period(raw):
        """El período pedido, o el mes ya cerrado.

        Un mes mal escrito **falla** en vez de caer al valor por omisión, que es
        lo contrario de lo que hace la pantalla — y a propósito: ahí el
        parámetro llega de un enlace pegado a mano y conviene mostrar algo,
        mientras que acá alguien tecleó `--period` con una intención concreta y
        congelar otro mes en silencio es peor que no congelar ninguno.
        """
        if not raw:
            return previous_month(timezone.localdate())
        match = PERIOD.match(raw)
        if not match:
            raise CommandError(f"--period tiene que ser YYYY-MM, no {raw!r}.")
        try:
            return date(int(match[1]), int(match[2]), 1)
        except ValueError as exc:
            raise CommandError(f"{raw!r} no es un mes válido.") from exc
