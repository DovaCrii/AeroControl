"""LV-447: abre la revisión de 24 h de los REG-016 que ya estaban cargados.

La revisión nace sola al cargar un REG-016 (`compliance.signals.open_mission_review`),
pero los que se cargaron **antes** de esta función no la tienen. Este comando la
abre para los vigentes desde `--since` (la Act. 19 rige desde 2026-11-10): sin fecha
de misión, importados en lote (`source_reference`) o de otro sujeto que no sea una
faena no abren revisión, igual que al cargarlos. Idempotente: el que ya la tiene se
salta. `--dry-run` sólo cuenta.

    bash scripts/deploy.sh --manage backfill_mission_reviews --since 2026-11-10 --dry-run
"""

from datetime import date

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandError

from apps.compliance.models import Document, MissionReview
from apps.compliance.signals import MISSION_RECORD_CODE
from apps.registry.models import CostCenter


class Command(BaseCommand):
    help = "Open the 24-hour review of REG-016 records loaded before LV-447."

    def add_arguments(self, parser):
        parser.add_argument("--since", required=True, help="Mission date YYYY-MM-DD.")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        try:
            since = date.fromisoformat(options["since"])
        except ValueError as exc:
            raise CommandError(f"Invalid --since date: {options['since']}") from exc

        documents = Document.objects.filter(
            is_active=True,
            is_current_version=True,
            doc_type__code=MISSION_RECORD_CODE,
            content_type=ContentType.objects.get_for_model(CostCenter),
            source_reference="",
            issue_date__gte=since,
            mission_review__isnull=True,
        )
        opened = 0
        for document in documents:
            if not options["dry_run"]:
                MissionReview.open_for_document(document)
            opened += 1
        verb = "Would open" if options["dry_run"] else "Opened"
        self.stdout.write(self.style.SUCCESS(f"{verb} {opened} mission review(s)."))
