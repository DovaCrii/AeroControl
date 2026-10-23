"""LV-361: load the AIP-Chile ENR 5.1 table (P, R, D zones) as a DRAFT snapshot.

    import_aip_enr5 --url                  # the AIP's own ENR 5.1 PDF
    import_aip_enr5 --url <url>
    import_aip_enr5 --file "ENR 5.1-1 Zonas P, R, D.pdf"
    import_aip_enr5 --file enr51.pdf --dry-run

The download happens **only here**, never while a person browses; if the source does not answer or
the file is bad, nothing is written and the current snapshot is not touched. Idempotent by the
SHA-256 of the PDF: the same file twice does nothing.

It never publishes: the snapshot is a draft and nothing is drawn until a person reviews and
approves every zone in the administration (phase 4). The report says what the parser could not
settle (a vertex order that crosses itself, a typo it proposed a fix for, arcs and sectors with no
geometry) and how the zones compare with the Google map. Reading the PDF needs the optional
package `pdfplumber`.

The PDF and its text belong to the DGAC and the remarks carry personal data: neither is kept in
git, and only the scrubbed text reaches the database.
"""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.airspace import aip_import
from apps.airspace.aip_import import AipImportError

SHOWN = 15


class Command(BaseCommand):
    help = "Import the AIP-Chile ENR 5.1 zones (PDF) as a draft snapshot for review."

    def add_arguments(self, parser):
        parser.add_argument("--file", help="Path of the ENR 5.1 PDF on this machine.")
        parser.add_argument(
            "--url",
            nargs="?",
            const=aip_import.DEFAULT_URL,
            help="Download the PDF (no value: the AIP's ENR 5.1 file).",
        )
        parser.add_argument(
            "--timeout",
            type=int,
            default=aip_import.DOWNLOAD_TIMEOUT_SECONDS,
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
        try:
            if path:
                try:
                    data = Path(path).read_bytes()
                except OSError as exc:
                    raise CommandError(f"Cannot read {path}: {exc.strerror}.") from exc
                source_url = Path(path).name
            else:
                data = aip_import.fetch_pdf(url, timeout=options["timeout"])
                source_url = url
            parsed = aip_import.parse_pdf(data)
            report = aip_import.sync_snapshot(
                parsed, source_url=source_url, dry_run=options["dry_run"]
            )
        except AipImportError as exc:
            raise CommandError(str(exc)) from exc

        if report.unchanged:
            snapshot = report.existing
            self.stdout.write(
                self.style.SUCCESS(
                    f"No changes: this PDF is already imported (AMDT "
                    f"{snapshot.amdt_number or '?'}, {snapshot.status}, "
                    f"{report.total} zones)."
                )
            )
            return
        self._report(report, parsed)

    def _report(self, report, parsed):
        prefix = "Would add" if report.dry_run else "Added"
        date = parsed.effective_date.isoformat() if parsed.effective_date else "?"
        summary = parsed.summary
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix} a draft snapshot: AMDT {parsed.amdt_number or '?'} ({date}), "
                f"{report.total} zones; {len(report.added)} new, {len(report.changed)} changed, "
                f"{len(report.kept)} unchanged, {len(report.archived)} to archive on "
                f"publication."
            )
        )
        self.stdout.write(
            f"  by kind: {summary['by_kind']}; by method: {summary['by_method']}"
        )
        self.stdout.write(
            f"  with geometry: {summary['with_geometry']}; clean: {summary['clean']}; "
            f"needs review: {summary['needs_review']}; without code: "
            f"{summary['without_code']}"
        )
        if summary["warning_codes"]:
            self.stdout.write(f"  warnings: {summary['warning_codes']}")
        for label, codes in (
            ("new", report.added),
            ("changed", report.changed),
            ("to archive", report.archived),
        ):
            if codes:
                shown = ", ".join(codes[:SHOWN])
                more = (
                    f" ... and {len(codes) - SHOWN} more" if len(codes) > SHOWN else ""
                )
                self.stdout.write(f"  {label}: {shown}{more}")
        if report.google_missing:
            self.stdout.write(
                "  cross-check: skipped, there is no current Google snapshot to compare with."
            )
        else:
            self.stdout.write(f"  cross-check with the Google map: {report.cross}")
            if aip_import.threshold_m() is None:
                self.stdout.write(
                    "  (no threshold set: distances are shown without a verdict; "
                    "AIRSPACE_CROSSCHECK_THRESHOLD_M)"
                )
        if report.superseded:
            self.stdout.write(
                f"  {report.superseded} earlier unpublished snapshot(s) closed as rejected."
            )
        if report.dry_run:
            self.stdout.write("Dry run: nothing was written.")
        else:
            self.stdout.write(
                "Nothing is published: review and approve the zones in the administration."
            )
