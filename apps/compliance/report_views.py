"""Compliance status report: on-screen plus CSV / XLSX / DOCX exports.

Follows the Workboard report pattern (same freeze-panes/auto-filter XLSX and
controlled-template DOCX), and reads its numbers from apps.compliance.reports
so the screen, the spreadsheet and the executive email cannot disagree.
"""

import csv
from datetime import datetime, timedelta
from io import BytesIO

from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.generic import TemplateView, View

from apps.core.exports import neutralize
from apps.core.views import ModelViewPermissionRequiredMixin
from apps.registry.models import CostCenter
from .models import Document, DocumentType
from .reports import (
    ALERT_HEADERS,
    COST_CENTER_HEADERS,
    alert_rows,
    build_compliance_report,
    cost_center_rows,
)

FILENAME_STEM = "aerocontrol-cumplimiento"


def _parse_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _lookup_by_pk(queryset, raw_pk):
    """`queryset.filter(pk=raw_pk).first()`, treating a malformed UUID the
    same as "not found" instead of a 500.

    A bookmarked URL, browser autofill, or a bot probing query strings can
    hand this a value that isn't a UUID at all -- `pk` is a UUIDField on both
    CostCenter and DocumentType, and `.filter(pk=...)` raises ValidationError
    (uncaught, a 500) rather than just finding nothing, unlike every other
    mismatch (wrong-but-valid UUID, wrong tenant, archived row).
    """
    try:
        return queryset.filter(pk=raw_pk).first()
    except (ValueError, ValidationError):
        return None


class ComplianceReportMixin(ModelViewPermissionRequiredMixin):
    """Resolves the shared filters, kept in the URL like the other reports."""

    model = Document
    permission_action = "view"

    def report_for(self, request):
        # Same timezone as the report's own period bounds; see reports.py.
        end = _parse_date(request.GET.get("end")) or timezone.localdate()
        start = _parse_date(request.GET.get("start")) or (end - timedelta(days=30))
        cost_center = None
        doc_type = None
        if request.GET.get("cost_center"):
            cost_center = _lookup_by_pk(
                CostCenter.objects.filter(is_active=True), request.GET["cost_center"]
            )
        if request.GET.get("doc_type"):
            doc_type = _lookup_by_pk(
                DocumentType.objects.filter(is_active=True), request.GET["doc_type"]
            )
        return build_compliance_report(
            start=start, end=end, cost_center=cost_center, doc_type=doc_type
        )


class ComplianceReportView(ComplianceReportMixin, TemplateView):
    template_name = "compliance/report.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        report = self.report_for(self.request)
        context.update(
            report=report,
            title=_("Compliance status report"),
            cost_centers=CostCenter.objects.filter(is_active=True).order_by("code"),
            document_types=DocumentType.objects.filter(is_active=True).order_by("name"),
            filter_params=self.request.GET,
            export_query=self.request.GET.urlencode(),
        )
        return context


class ComplianceReportCsvView(ComplianceReportMixin, View):
    def get(self, request):
        report = self.report_for(request)
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{FILENAME_STEM}.csv"'
        response.write("﻿")  # BOM so Excel detects UTF-8
        writer = csv.writer(response, lineterminator="\r\n")
        writer.writerow([_("Compliance status report")])
        writer.writerow([_("Generated"), report["generated_on"].isoformat()])
        writer.writerow([])
        writer.writerow(COST_CENTER_HEADERS)
        for row in cost_center_rows(report):
            writer.writerow([neutralize(value) for value in row])
        totals = report["totals"]
        writer.writerow(
            [
                neutralize(_("TOTAL")),
                "",
                totals["total"],
                totals["valid"],
                totals["valid_pct"],
                totals["expired"],
                totals["due_7"],
                totals["due_15"],
                totals["due_30"],
            ]
        )
        writer.writerow([])
        writer.writerow([_("Open alerts")])
        writer.writerow(ALERT_HEADERS)
        for row in alert_rows(report):
            writer.writerow([neutralize(value) for value in row])
        return response


class ComplianceReportXlsxView(ComplianceReportMixin, View):
    def get(self, request):
        from openpyxl import Workbook
        from openpyxl.styles import Font

        report = self.report_for(request)
        workbook = Workbook()
        summary = workbook.active
        summary.title = "Resumen"
        summary.append(COST_CENTER_HEADERS)
        for row in cost_center_rows(report):
            summary.append([neutralize(value) for value in row])
        totals = report["totals"]
        summary.append(
            [
                _("TOTAL"),
                "",
                totals["total"],
                totals["valid"],
                totals["valid_pct"],
                totals["expired"],
                totals["due_7"],
                totals["due_15"],
                totals["due_30"],
            ]
        )
        for cell in summary[1]:
            cell.font = Font(bold=True)
        for cell in summary[summary.max_row]:
            cell.font = Font(bold=True)

        alerts = workbook.create_sheet("Alertas abiertas")
        alerts.append(ALERT_HEADERS)
        for cell in alerts[1]:
            cell.font = Font(bold=True)
        for row in alert_rows(report):
            alerts.append([neutralize(value) for value in row])

        for sheet in (summary, alerts):
            sheet.freeze_panes = "A2"
            sheet.auto_filter.ref = sheet.dimensions
            for column in sheet.columns:
                sheet.column_dimensions[column[0].column_letter].width = min(
                    max(len(str(cell.value or "")) for cell in column) + 2, 40
                )

        output = BytesIO()
        workbook.save(output)
        response = HttpResponse(
            output.getvalue(),
            content_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )
        response["Content-Disposition"] = f'attachment; filename="{FILENAME_STEM}.xlsx"'
        return response


def build_report_workbook_bytes(report):
    """XLSX bytes for a prepared report, for attaching to the executive email."""
    from openpyxl import Workbook
    from openpyxl.styles import Font

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Resumen"
    sheet.append(COST_CENTER_HEADERS)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for row in cost_center_rows(report):
        sheet.append([neutralize(value) for value in row])
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


class ComplianceReportDocxView(ComplianceReportMixin, View):
    def get(self, request):
        from docx import Document as DocxDocument
        from docx.shared import Inches

        report = self.report_for(request)
        document = DocxDocument()
        document.add_heading(_("AeroControl — Compliance status report"), 0)
        document.add_paragraph(
            _("Generated: %(date)s") % {"date": timezone.localdate().isoformat()}
        )
        period = report["period"]
        document.add_paragraph(
            _("Period analysed: %(start)s to %(end)s")
            % {"start": period["start"].isoformat(), "end": period["end"].isoformat()}
        )
        totals = report["totals"]
        document.add_paragraph(
            _(
                "%(valid)s of %(total)s current documents are valid "
                "(%(pct)s%%). %(expired)s expired, %(due)s expiring within "
                "%(horizon)s days."
            )
            % {
                "valid": totals["valid"],
                "total": totals["total"],
                "pct": totals["valid_pct"],
                "expired": totals["expired"],
                "due": totals["due_7"] + totals["due_15"] + totals["due_30"],
                "horizon": report["horizon_days"],
            }
        )

        document.add_heading(_("By cost center"), level=1)
        table = document.add_table(rows=1, cols=len(COST_CENTER_HEADERS))
        table.style = "Light Shading Accent 1"
        for cell, header in zip(table.rows[0].cells, COST_CENTER_HEADERS):
            cell.text = str(header)
        for row in cost_center_rows(report):
            cells = table.add_row().cells
            for cell, value in zip(cells, row):
                cell.text = str(value)

        resolution = report["resolution"]
        document.add_heading(_("Alert resolution in the period"), level=1)
        if resolution["resolved_count"]:
            document.add_paragraph(
                _("%(count)s alerts resolved, %(days)s days on average.")
                % {
                    "count": resolution["resolved_count"],
                    "days": resolution["avg_days"],
                }
            )
        else:
            document.add_paragraph(_("No alerts were resolved in this period."))

        document.add_heading(_("Open alerts"), level=1)
        if report["open_alerts"]:
            alert_table = document.add_table(rows=1, cols=len(ALERT_HEADERS))
            alert_table.style = "Light Shading Accent 1"
            for cell, header in zip(alert_table.rows[0].cells, ALERT_HEADERS):
                cell.text = str(header)
            for row in alert_rows(report):
                cells = alert_table.add_row().cells
                for cell, value in zip(cells, row):
                    cell.text = str(value)
        else:
            document.add_paragraph(_("No open alerts."))

        for section in document.sections:
            section.left_margin = Inches(0.6)
            section.right_margin = Inches(0.6)

        output = BytesIO()
        document.save(output)
        response = HttpResponse(
            output.getvalue(),
            content_type=(
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document"
            ),
        )
        response["Content-Disposition"] = f'attachment; filename="{FILENAME_STEM}.docx"'
        return response
