"""Fleet and personnel roster: on-screen plus PDF / XLSX / CSV (LV-145).

Same shape as the compliance report next door -- a mixin that resolves the
filters from the query string, one view per output, and every number read from
a single data module (`catastro.py`) so the four cannot disagree.

The PDF wears the corporate letterhead from LV-144; this is the report that
letterhead was built shared for.
"""

import csv
from io import BytesIO

from django.http import HttpResponse
from django.utils.translation import gettext as _
from django.views.generic import TemplateView, View

from apps.core.exports import neutralize
from apps.core.views import ModelPermissionRequiredMixin, lookup_by_pk
from .catastro import (
    AIRCRAFT_HEADERS,
    OPERATOR_HEADERS,
    CatastroFilters,
    aircraft_rows,
    build_catastro,
    operator_rows,
    totals_sentence,
)
from .models import Aircraft, CostCenter

FILENAME_STEM = "aerocontrol-catastro"

# Letter portrait, 0.6in side margins (apps/core/pdf.SIDE_MARGIN): 525.6pt of
# usable width, split explicitly rather than left to reportlab's equal shares --
# "Year" needs 30pt and "Model" needs a hundred, and equal columns spend the
# page on the short ones and wrap the long ones to three lines.
AIRCRAFT_COL_WIDTHS = [66, 58, 100, 68, 92, 30, 56, 55.6]
OPERATOR_COL_WIDTHS = [70, 150, 85, 90, 75, 55.6]


class CatastroMixin(ModelPermissionRequiredMixin):
    """Requires **both** view permissions, because the report has two halves.

    `ModelPermissionRequiredMixin` derives a single permission from `model` and
    `permission_action`; this document carries a fleet table and a personnel
    table, and someone holding `view_aircraft` without `view_operator` must not
    be handed the personnel one. `PermissionRequiredMixin` requires *all* of
    what `get_permission_required` returns, and the mixin already brings the
    right `handle_no_permission` (anonymous to the login page, authenticated
    without the permission to a 403).
    """

    # Kept for the mixin's contract and for anyone reading the class; the
    # permission tuple below is what actually gates the view.
    model = Aircraft
    permission_action = "view"

    def get_permission_required(self):
        return ("registry.view_aircraft", "registry.view_operator")

    def filters_for(self, request):
        cost_center = None
        if request.GET.get("cost_center"):
            cost_center = lookup_by_pk(
                CostCenter.objects.filter(is_active=True), request.GET["cost_center"]
            )
        # An unknown status is "no status filter", not an empty roster: the value
        # comes from a query string, and a stale bookmark should not answer
        # "you have no aircraft".
        status = request.GET.get("status", "")
        if status not in {code for code, _label in Aircraft.STATUS_CHOICES}:
            status = ""
        return CatastroFilters(
            cost_center=cost_center,
            status=status,
            include_terminal=request.GET.get("include_terminal") == "1",
            include_archived=request.GET.get("include_archived") == "1",
        )

    def catastro_for(self, request):
        return build_catastro(request.user, self.filters_for(request))


class CatastroReportView(CatastroMixin, TemplateView):
    template_name = "registry/catastro.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        catastro = self.catastro_for(self.request)
        context.update(
            catastro=catastro,
            # Object and row side by side: the cells come from the same
            # `*_rows` the PDF prints, so the screen and the paper cannot drift
            # apart, while the object still supplies the link to the ficha.
            aircraft_table=list(zip(catastro["aircraft"], aircraft_rows(catastro))),
            operator_table=list(zip(catastro["operators"], operator_rows(catastro))),
            aircraft_headers=AIRCRAFT_HEADERS,
            operator_headers=OPERATOR_HEADERS,
            sentences=totals_sentence(catastro),
            title=_("Fleet and personnel roster"),
            cost_centers=CostCenter.objects.filter(is_active=True).order_by("code"),
            statuses=Aircraft.STATUS_CHOICES,
            filter_params=self.request.GET,
            export_query=self.request.GET.urlencode(),
        )
        return context


class CatastroReportPdfView(CatastroMixin, View):
    def get(self, request):
        from django.utils.html import escape
        from reportlab.platypus import PageBreak, Paragraph, Spacer, Table

        from apps.core import pdf as corepdf

        catastro = self.catastro_for(request)
        styles = corepdf.executive_stylesheet()
        title = str(_("AeroControl — Fleet and personnel roster"))
        letterhead = corepdf.Letterhead(
            title=title,
            reference=corepdf.derived_reference("CAT", catastro["as_of"]),
            generated_on=catastro["as_of"],
        )

        def table(headers, rows, widths, empty_message):
            if not rows:
                return Paragraph(escape(str(empty_message)), styles["Normal"])
            # Every cell is a Paragraph, headers included: at these widths
            # "Manufacturer" has to wrap, and a plain string in a reportlab
            # table does not wrap -- it overruns into the next column.
            # `escape` because Paragraph parses its text as mini-HTML, and an
            # "&" in a manufacturer name would raise instead of printing.
            data = [
                [Paragraph(escape(str(head)), styles["CellHeader"]) for head in headers]
            ]
            data += [
                [
                    Paragraph(escape(str(neutralize(cell))), styles["Cell"])
                    for cell in row
                ]
                for row in rows
            ]
            grid = Table(data, colWidths=widths, repeatRows=1)
            grid.setStyle(corepdf.executive_table_style())
            return grid

        elements = [Paragraph(escape(title), styles["Title"])]
        for sentence in totals_sentence(catastro):
            elements.append(Paragraph(escape(str(sentence)), styles["Normal"]))
        elements.append(Spacer(1, 14))

        # Escaped like every other Paragraph, catalog string or not: an "&" in a
        # translation is the same crash as an "&" in a manufacturer name.
        elements.append(Paragraph(escape(str(_("Fleet"))), styles["Heading2"]))
        elements.append(
            table(
                AIRCRAFT_HEADERS,
                aircraft_rows(catastro),
                AIRCRAFT_COL_WIDTHS,
                _("No aircraft registered."),
            )
        )
        # LV-164 (pedido del usuario, 2026-08-27): el personal arranca en hoja
        # nueva. Son dos padrones de cosas distintas, y en un documento que se
        # entrega cada tabla se lee —y se fotocopia, y se firma— por separado.
        # El `keepWithNext` del estilo evita además que cualquiera de los dos
        # títulos quede huérfano al pie; el salto es la decisión editorial, no
        # el parche.
        elements.append(PageBreak())
        elements.append(Paragraph(escape(str(_("Personnel"))), styles["Heading2"]))
        elements.append(
            table(
                OPERATOR_HEADERS,
                operator_rows(catastro),
                OPERATOR_COL_WIDTHS,
                _("No operators registered."),
            )
        )

        return corepdf.pdf_response(elements, letterhead, f"{FILENAME_STEM}.pdf")


class CatastroReportXlsxView(CatastroMixin, View):
    def get(self, request):
        from openpyxl import Workbook
        from openpyxl.styles import Font
        from openpyxl.utils import get_column_letter

        catastro = self.catastro_for(request)
        sentences = totals_sentence(catastro)
        workbook = Workbook()

        def fill(sheet, headers, rows):
            """Preamble, then the table, with the filter anchored on the header
            row rather than on `sheet.dimensions`.

            The compliance report puts its headers on row 1 and can hand
            openpyxl the whole sheet; here the cut-off sentences come first, so
            an auto-filter over the dimensions would take the sentences for
            column titles.

            Written by coordinate and not with `append`: an `append([])` for the
            blank separator advances openpyxl's internal cursor but creates no
            cell, so `max_row` still points at the sentence above it -- which
            put the bold font on an empty row and the filter one row short of
            the headers.
            """
            for offset, sentence in enumerate(sentences, start=1):
                sheet.cell(row=offset, column=1, value=str(sentence))
            header_row = len(sentences) + 2  # one blank row of separation
            for column, head in enumerate(headers, start=1):
                sheet.cell(row=header_row, column=column, value=str(head)).font = Font(
                    bold=True
                )
            for index, row in enumerate(rows, start=header_row + 1):
                for column, value in enumerate(row, start=1):
                    sheet.cell(row=index, column=column, value=neutralize(value))
            last_row = header_row + len(rows)
            sheet.freeze_panes = f"A{header_row + 1}"
            sheet.auto_filter.ref = (
                f"A{header_row}:{get_column_letter(len(headers))}{last_row}"
            )
            for column in sheet.columns:
                sheet.column_dimensions[column[0].column_letter].width = min(
                    max(len(str(cell.value or "")) for cell in column) + 2, 40
                )

        fleet = workbook.active
        fleet.title = "Flota"
        fill(fleet, AIRCRAFT_HEADERS, aircraft_rows(catastro))
        fill(
            workbook.create_sheet("Personal"),
            OPERATOR_HEADERS,
            operator_rows(catastro),
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


class CatastroReportCsvView(CatastroMixin, View):
    def get(self, request):
        catastro = self.catastro_for(request)
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{FILENAME_STEM}.csv"'
        response.write("﻿")  # BOM so Excel detects UTF-8
        writer = csv.writer(response, lineterminator="\r\n")
        writer.writerow([_("Fleet and personnel roster")])
        for sentence in totals_sentence(catastro):
            writer.writerow([neutralize(sentence)])
        writer.writerow([])

        for heading, headers, rows in (
            (_("Fleet"), AIRCRAFT_HEADERS, aircraft_rows(catastro)),
            (_("Personnel"), OPERATOR_HEADERS, operator_rows(catastro)),
        ):
            writer.writerow([neutralize(heading)])
            writer.writerow([str(head) for head in headers])
            for row in rows:
                writer.writerow([neutralize(value) for value in row])
            writer.writerow([])
        return response
