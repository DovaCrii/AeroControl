from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.compliance.models import DocumentType
from apps.compliance.report_views import build_report_workbook_bytes
from apps.compliance.reports import build_compliance_report, cost_center_rows
from apps.core.jobs import record_job_run
from apps.registry.models import CostCenter


class Command(BaseCommand):
    help = (
        "Print the compliance status report, or write it as XLSX with --output. "
        "Same numbers as the on-screen report and the executive email."
    )

    def add_arguments(self, parser):
        parser.add_argument("--start", help="Period start (YYYY-MM-DD).")
        parser.add_argument("--end", help="Period end (YYYY-MM-DD). Defaults to today.")
        parser.add_argument("--cost-center", help="Cost center code to restrict to.")
        parser.add_argument("--doc-type", help="Document type code to restrict to.")
        parser.add_argument(
            "--output",
            help="Write the XLSX here instead of printing. Must be outside the repo.",
        )

    def handle(self, *args, **options):
        with record_job_run("compliance_report") as run:
            report = build_compliance_report(
                start=self._date(options["start"]),
                end=self._date(options["end"]),
                cost_center=self._cost_center(options["cost_center"]),
                doc_type=self._doc_type(options["doc_type"]),
            )
            if options["output"]:
                path = self._write(report, options["output"])
                run["summary"] = f"{path.name} ({report['totals']['total']} documents)"
                self.stdout.write(self.style.SUCCESS(f"Report written to {path}"))
            else:
                self._print(report)
                run["summary"] = (
                    f"{report['totals']['total']} documents, "
                    f"{report['totals']['expired']} expired"
                )

    @staticmethod
    def _date(value):
        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError as exc:
            raise CommandError(f"Invalid date {value!r}; use YYYY-MM-DD.") from exc

    @staticmethod
    def _cost_center(code):
        if not code:
            return None
        center = CostCenter.objects.filter(code=code, is_active=True).first()
        if center is None:
            raise CommandError(f"No active cost center with code {code!r}.")
        return center

    @staticmethod
    def _doc_type(code):
        if not code:
            return None
        doc_type = DocumentType.objects.filter(code=code, is_active=True).first()
        if doc_type is None:
            raise CommandError(f"No active document type with code {code!r}.")
        return doc_type

    @staticmethod
    def _write(report, output):
        path = Path(output).expanduser()
        # A path with no extension means a directory, whether or not it exists
        # yet: checking is_dir() alone silently produced an extension-less file
        # when the folder had not been created.
        if path.is_dir() or not path.suffix:
            stamp = timezone.localdate().isoformat()
            path = path / f"aerocontrol-cumplimiento-{stamp}.xlsx"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(build_report_workbook_bytes(report))
        return path

    def _print(self, report):
        totals = report["totals"]
        period = report["period"]
        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"Compliance status — generated {report['generated_on']} "
                f"(period {period['start']} to {period['end']})"
            )
        )
        self.stdout.write(
            f"{totals['valid']}/{totals['total']} current documents valid "
            f"({totals['valid_pct']}%), {totals['expired']} expired, "
            f"{totals['due_7']}/{totals['due_15']}/{totals['due_30']} due in 7/15/30 days"
        )
        self.stdout.write("")
        for row in cost_center_rows(report):
            code, name, total, valid, pct, expired, due7, due15, due30 = row
            self.stdout.write(
                f"  {code:<12} {name[:26]:<26} docs={total:<4} valid={pct}% "
                f"expired={expired} 7d={due7} 15d={due15} 30d={due30}"
            )
        resolution = report["resolution"]
        self.stdout.write("")
        if resolution["resolved_count"]:
            self.stdout.write(
                f"Resolved in period: {resolution['resolved_count']} alerts, "
                f"{resolution['avg_days']} days on average"
            )
        else:
            self.stdout.write("Resolved in period: none")
        self.stdout.write(f"Open alerts: {len(report['open_alerts'])}")
