"""LV-159: llevar a la ficha las Resoluciones de la JAC que ya están cargadas.

La señal de `LV-159` corre cuando un documento se guarda, así que arregla de aquí
en adelante — y no toca lo que **ya** está en producción: `RPA-5534` tiene su
resolución adjunta desde el 2026-08-24 y su ficha seguía diciendo "Vencida".

Sin `--apply` no escribe nada: dice qué haría. Es el mismo trato que
`chapter1_docx_import` y `import_aip_aerodromes`, y por el mismo motivo — una
pasada sobre datos operativos se mira antes de correrla.
"""

from django.core.management.base import BaseCommand

from apps.registry.insurance import jac_approval_expiry, sync_insurance_expiry
from apps.registry.models import Aircraft


class Command(BaseCommand):
    help = (
        "Sync each aircraft's JAC insurance expiry from the JAC resolution on "
        "file. Dry run unless --apply is given."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Write the changes. Without it, only report what would change.",
        )

    def handle(self, *args, **options):
        apply = options["apply"]
        # Todas las activas, incluidas las que no están `active` de seguro: el
        # caso que motiva esto es justamente una ficha cuyo estado y cuya fecha
        # no coincidían con el papel.
        aircraft = Aircraft.objects.filter(is_active=True).order_by("registration")
        changed = 0
        for airframe in aircraft:
            declared = jac_approval_expiry(airframe)
            if declared is None:
                continue
            before = (airframe.insurance_expiry, airframe.insurance_status)
            if not apply:
                # Se pregunta sin escribir: se compara contra lo que la función
                # haría, sin llamarla, para que un `--dry-run` no toque la base.
                moves = (
                    airframe.insurance_expiry is None
                    or airframe.insurance_expiry < declared
                )
                activates = (
                    declared >= _today()
                    and airframe.insurance_status != Aircraft.INSURANCE_STATUS_ACTIVE
                )
                if not moves and not activates:
                    continue
                changed += 1
                self.stdout.write(
                    f"{airframe.registration}: {before[0]} / {before[1]} -> "
                    f"{declared if moves else before[0]} / "
                    f"{'active' if activates else before[1]}"
                )
                continue
            if sync_insurance_expiry(airframe) is None:
                continue
            airframe.refresh_from_db()
            changed += 1
            self.stdout.write(
                f"{airframe.registration}: {before[0]} / {before[1]} -> "
                f"{airframe.insurance_expiry} / {airframe.insurance_status}"
            )
        verb = "updated" if apply else "would change"
        self.stdout.write(self.style.SUCCESS(f"{changed} aircraft {verb}."))
        if not apply and changed:
            self.stdout.write("Re-run with --apply to write these changes.")


def _today():
    from django.utils import timezone

    return timezone.localdate()
