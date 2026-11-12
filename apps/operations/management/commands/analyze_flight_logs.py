"""LV-427: reprocesa los logs de vuelo adjuntos (los que no tienen análisis o quedaron pendientes)."""

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandError

from apps.compliance.models import Document
from apps.operations.flightlog.service import (
    FLIGHT_LOG_TYPE,
    PARSER_VERSION,
    analyze_document,
)
from apps.operations.models import FlightLogAnalysis, FlightPermission, FlightRecord
from apps.registry.models import Aircraft


class Command(BaseCommand):
    help = (
        "Analyse flight log attachments that have no analysis yet (or are pending). "
        "--retry-errors also re-runs the ones that failed; --record limits the run to the "
        "analyses linked to one operation."
    )

    def add_arguments(self, parser):
        parser.add_argument("--record", help="FlightRecord pk to limit the run to.")
        parser.add_argument(
            "--retry-errors", action="store_true", help="Also re-run failed analyses."
        )
        parser.add_argument(
            "--outdated",
            action="store_true",
            help="Also re-run finished analyses made with an older parser version.",
        )

    def handle(self, *args, **options):
        retry = options["retry_errors"]
        statuses = [FlightLogAnalysis.STATUS_PENDING]
        if retry:
            statuses.append(FlightLogAnalysis.STATUS_ERROR)
        if options["outdated"]:
            # LV-434: lo ya analizado con otro `PARSER_VERSION` se rehace (las llaves del log
            # quedaron guardadas, así que no hace falta la API de DJI).
            stale = (
                FlightLogAnalysis.objects.filter(status=FlightLogAnalysis.STATUS_OK)
                .exclude(parser_version=PARSER_VERSION)
                .select_related("document")
            )
            if options["record"]:
                stale = stale.filter(flight_record_id=options["record"])
            for analysis in stale:
                analyze_document(analysis.document, analysis)
            self.stdout.write(f"Outdated re-analysed: {len(stale)}.")
        if options["record"]:
            if not FlightRecord.objects.filter(pk=options["record"]).exists():
                raise CommandError(f"No flight record {options['record']}.")
            targets = list(
                FlightLogAnalysis.objects.filter(
                    flight_record_id=options["record"], status__in=statuses
                ).select_related("document")
            )
            documents = [(a.document, a) for a in targets]
        else:
            existing = FlightLogAnalysis.objects.filter(
                status__in=statuses
            ).select_related("document")
            documents = [(a.document, a) for a in existing]
            analysed = FlightLogAnalysis.objects.values_list("document_id", flat=True)
            missing = Document.objects.filter(
                content_type__in=[
                    ContentType.objects.get_for_model(FlightPermission),
                    ContentType.objects.get_for_model(Aircraft),
                ],
                doc_type__code=FLIGHT_LOG_TYPE,
                is_active=True,
                is_current_version=True,
            ).exclude(pk__in=analysed)
            documents += [(d, None) for d in missing]
        done = failed = 0
        for document, analysis in documents:
            result = analyze_document(document, analysis)
            if result.status == FlightLogAnalysis.STATUS_OK:
                done += 1
            else:
                failed += 1
        self.stdout.write(f"Analysed: {done}. With error: {failed}.")
