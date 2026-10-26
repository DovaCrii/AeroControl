"""Fleet and personnel roster: on-screen plus PDF / XLSX / CSV (LV-145).

Same shape as the compliance report next door -- a mixin that resolves the
filters from the query string, one view per output, and every number read from
a single data module (`catastro.py`) so the four cannot disagree.

The PDF wears the corporate letterhead from LV-144; this is the report that
letterhead was built shared for.
"""

from django.utils.translation import gettext as _
from django.views.generic import TemplateView, View

from apps.compliance.digest import bucket_for
from apps.core.exports import neutralize
from apps.core.views import ModelPermissionRequiredMixin
from apps.reporting.export import (
    CSV_TYPE,
    XLSX_TYPE,
    Table,
    cost_center_filter,
    dated_filename,
    download,
    to_csv,
    to_xlsx,
)
from .catastro import (
    AIRCRAFT_EXPIRY_COLUMN,
    AIRCRAFT_HEADERS,
    OPERATOR_EXPIRY_COLUMN,
    OPERATOR_HEADERS,
    CatastroFilters,
    aircraft_expiries,
    aircraft_rows,
    build_catastro,
    closing_total,
    operator_expiries,
    operator_rows,
    totals_sentence,
)
from .models import Aircraft, CostCenter
from .selectors import cost_center_universe, universe_sentence

FILENAME_STEM = "aerocontrol-catastro"

# LV-167: **horizontal** (LV-355 F2: A4, el único papel de los informes). Con la columna de vigencia la flota pasa a nueve
# columnas, y en vertical (525.6 pt útiles) la matrícula y el número de serie se
# cortaban -- justo los dos datos con los que se identifica una aeronave. En
# horizontal hay 755.5 pt útiles en A4 (705.6 en Carta), y los anchos se reparten a mano en vez de dejarlos a las
# partes iguales de reportlab: "Año" necesita 34 pt y "Modelo" ciento doce, y con
# columnas iguales la página se gasta en las cortas y las largas cortan a tres
# líneas.
# Ancho útil de A4 horizontal: 841.89 pt menos los dos márgenes laterales de la
# cabecera única (pps.core.pdf.SIDE_MARGIN, 43.2 pt). Las proporciones son las que
# LV-167 eligió a mano; sólo se escalan para llenar la hoja.
USABLE_WIDTH = 841.89 - 2 * 43.2


def _fit(widths):
    scale = USABLE_WIDTH / sum(widths)
    return [round(width * scale, 1) for width in widths]


AIRCRAFT_COL_WIDTHS = _fit([72, 58, 112, 74, 112, 34, 66, 60, 117.6])
OPERATOR_COL_WIDTHS = _fit([190, 100, 100, 130, 85, 100.6])


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
        cost_center = cost_center_filter(request.GET)
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
            closing=closing_total(catastro),
            # LV-355 F2 (S10): el universo, bajo cada tabla.
            universe=universe_sentence(cost_center_universe(self.request.user)),
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

        def urgency(expiries, column):
            """El color de urgencia de la celda de vigencia, fila por fila.

            LV-167: **la misma escala que el panel y el digest** -- una fecha
            ámbar en pantalla es ámbar en el papel. El tramo lo calcula acá con
            `bucket_for`, que es el dueño de los cortes, y `catastro.py` sólo
            entrega las fechas: que el padrón importara `apps.compliance` para
            colorear una celda sería atarlo al cumplimiento por el color.

            Un nulo **no entra en ningún tramo** y por lo tanto no se pinta: es
            la lección de `LV-29`, un nulo es "nunca se ingresó" y no "vigente".

            Y acá se ve por qué `urgency_commands` toma **rangos**: esto pinta
            una celda por fila (cada fila tiene su fecha y su tramo), mientras el
            informe de cumplimiento pinta columnas enteras. Cualquiera de las dos
            orientaciones fijada en el helper habría tenido que reescribirse.
            """
            today = catastro["as_of"]
            return corepdf.urgency_commands(
                (bucket_for(expiry, today), (column, index), (column, index))
                for index, expiry in enumerate(expiries, start=1)
                if expiry is not None
            )

        def table(headers, rows, widths, empty_message, extra=()):
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
            grid.setStyle(corepdf.executive_table_style(extra))
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
                urgency(aircraft_expiries(catastro), AIRCRAFT_EXPIRY_COLUMN),
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
                urgency(operator_expiries(catastro), OPERATOR_EXPIRY_COLUMN),
            )
        )

        # LV-172: el total de cierre, al final del documento y no sólo en el
        # encabezado. Con la flota y el personal ocupando varias páginas, quien
        # recibe el catastro termina de leer a varias páginas del número que lo
        # resume -- y es al final donde se comprueba que no se cortó nada. Va en
        # negrita, que es lo que lo separa de las notas al pie de cada tabla.
        elements.append(Spacer(1, 12))
        elements.append(
            Paragraph(
                f"<b>{escape(str(closing_total(catastro)))}</b>", styles["Normal"]
            )
        )

        # LV-167: horizontal. Ver el comentario de los anchos: con nueve columnas
        # la vertical cortaba la matrícula y el número de serie.
        from reportlab.lib.pagesizes import A4, landscape

        return corepdf.pdf_response(
            elements,
            letterhead,
            dated_filename(FILENAME_STEM, catastro["as_of"], "pdf"),
            pagesize=landscape(A4),
        )


def _tables(catastro):
    return [
        Table(
            headers=tuple(AIRCRAFT_HEADERS),
            rows=tuple(aircraft_rows(catastro)),
            sheet="Flota",
            heading=_("Fleet"),
        ),
        Table(
            headers=tuple(OPERATOR_HEADERS),
            rows=tuple(operator_rows(catastro)),
            sheet="Personal",
            heading=_("Personnel"),
        ),
    ]


class CatastroReportXlsxView(CatastroMixin, View):
    def get(self, request):
        catastro = self.catastro_for(request)
        content = to_xlsx(
            _tables(catastro), preamble=[str(s) for s in totals_sentence(catastro)]
        )
        return download(
            content,
            XLSX_TYPE,
            dated_filename(FILENAME_STEM, catastro["as_of"], "xlsx"),
        )


class CatastroReportCsvView(CatastroMixin, View):
    def get(self, request):
        catastro = self.catastro_for(request)
        content = to_csv(
            _tables(catastro),
            preamble=[[_("Fleet and personnel roster")]]
            + [[sentence] for sentence in totals_sentence(catastro)],
            trailing_blank=True,
        )
        return download(
            content,
            CSV_TYPE,
            dated_filename(FILENAME_STEM, catastro["as_of"], "csv"),
        )
