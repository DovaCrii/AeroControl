"""LV-357: load the airspace map (KML) into the database.

    import_airspace_zones --url            # the default Google My Maps export
    import_airspace_zones --url <url>
    import_airspace_zones --file mapa.kml
    import_airspace_zones --file mapa.kml --dry-run

The download happens **only here**, never while a person browses. If the source
does not answer or the file is bad, the current snapshot is not touched.
Idempotent by sha256: the same file twice does nothing. When it changed, a new
snapshot records how many features were added, changed and archived; what
disappeared from the source is archived (`is_active=False`), never deleted.

The data is not in git (license unconfirmed, public repo). On `p340` run it,
then read the report: it names every added, changed and archived feature and the
quality warnings of the source.
"""

import hashlib
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.airspace import kml_import
from apps.geo.kml.errors import KmlImportError

SHOWN = 15


class Command(BaseCommand):
    help = "Import the airspace and aerodrome map (KML) as a new snapshot."

    def add_arguments(self, parser):
        parser.add_argument("--file", help="Path of a KML file on this machine.")
        parser.add_argument(
            "--url",
            nargs="?",
            const=kml_import.DEFAULT_URL,
            help="Download the KML (no value: the default map export).",
        )
        parser.add_argument(
            "--timeout",
            type=int,
            default=kml_import.DOWNLOAD_TIMEOUT_SECONDS,
            help="Seconds to wait for the download.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing anything.",
        )

    def handle(self, *args, **options):
        path, url = options["file"], options["url"]
        if bool(path) == bool(url):
            raise CommandError("Pass exactly one of --file or --url.")

        if path:
            try:
                data = Path(path).read_bytes()
            except OSError as exc:
                raise CommandError(f"Cannot read {path}: {exc.strerror}.") from exc
            source_url = Path(path).name
        else:
            try:
                data = kml_import.fetch_url(url, timeout=options["timeout"])
            except kml_import.AirspaceFetchError as exc:
                raise CommandError(str(exc)) from exc
            source_url = url
        if len(data) > kml_import.MAX_BYTES:
            raise CommandError("The file is larger than the allowed size.")

        try:
            result = kml_import.parse_airspace_kml(data)
        except KmlImportError as exc:
            raise CommandError(f"Not a usable KML: {exc}") from exc

        report = kml_import.sync_features(
            result,
            sha256=hashlib.sha256(data).hexdigest(),
            source_name=result.document_name or "Airspace map",
            source_url=source_url,
            dry_run=options["dry_run"],
        )

        if report.unchanged:
            self.stdout.write(
                self.style.SUCCESS(
                    f"No changes: the source is identical to the current snapshot "
                    f"({report.total} features)."
                )
            )
            return
        prefix = "Would add" if report.dry_run else "Added"
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix} {len(report.added)}, changed {len(report.changed)}, "
                f"archived {len(report.archived)}; {report.total} features in the "
                f"source."
            )
        )
        for label, rows in (
            ("added", report.added),
            ("changed", report.changed),
            ("archived", report.archived),
        ):
            for row in rows[:SHOWN]:
                self.stdout.write(f"  {label}: {row.code or '-'} {row.name}")
            if len(rows) > SHOWN:
                self.stdout.write(f"  {label}: ... and {len(rows) - SHOWN} more")
        if result.warnings:
            self.stdout.write(
                f"{len(result.warnings)} quality warning(s) in the source:"
            )
            for warning in result.warnings[:SHOWN]:
                self.stdout.write(f"  {warning}")
            if len(result.warnings) > SHOWN:
                self.stdout.write(f"  ... and {len(result.warnings) - SHOWN} more")
        if report.dry_run:
            self.stdout.write("Dry run: nothing was written.")
