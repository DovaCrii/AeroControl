"""T1.4: dar por revisado un fallo de escritura de auditoría.

La marca de `apps/core/audit_health.py` se queda hasta que alguien la mira. Este
comando la borra: se corre **después** de leer el log y entender qué pasó, y
conviene hacerlo con la fecha a la vista, porque el paso (3) de T1.4 —encender el
modo estricto— pide *una semana con cero*, y borrar la marca sin mirarla borra
también esa cuenta.
"""

from django.core.management.base import BaseCommand

from apps.core.audit_health import clear_failure, last_failure


class Command(BaseCommand):
    help = "Clear the audit-write-failure marker once it has been reviewed."

    def handle(self, *args, **options):
        failure = last_failure()
        if failure is None:
            self.stdout.write("No audit write failure on record.")
            return
        clear_failure()
        self.stdout.write(
            self.style.SUCCESS(
                f"Cleared: {failure.get('count', '?')} failure(s), "
                f"from {failure.get('first_at', '?')} to {failure.get('last_at', '?')}."
            )
        )
