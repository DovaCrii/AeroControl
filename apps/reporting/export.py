"""LV-355 F1: la tubería de exportación de los informes operativos.

Un informe entrega `headers + rows` **una sola vez** y de ahí salen el CSV, el XLSX
y el DOCX. Antes había cuatro escritores XLSX (`compliance/report_views.py` dos,
`registry/report_views.py`, `workboard/views.py`), cuatro CSV con BOM escritos a
mano y el bucle de autoancho copiado en cada uno; el nombre del archivo lo
decidía cada vista (`aerocontrol-cumplimiento.pdf`, sin fecha).

**Qué NO hace**: no toca el informe mensual a la DGAC (su A4 es un contrato
congelado) ni los listados de `CsvExportMixin`, que exportan modelos y no
informes. El PDF sigue en `apps.core.pdf` (la tubería PDF es F2).

⚠️ **La neutralización de fórmulas es obligatoria y no se reimplementa**: todo
valor de texto que entra a un CSV o a un XLSX pasa por `apps.core.exports.
neutralize`, la misma función que usa `CsvExportMixin`. Excel y LibreOffice
ejecutan una celda que empieza con `=`, `+`, `-` o `@`, y el valor viene de campos
que alguien escribió. Se aplica **aquí, al escribir**, y no en cada vista: una
vista nueva que olvide neutralizar sigue siendo inerte. El DOCX no la necesita
(un párrafo de Word no ejecuta nada) y por eso escribe el texto tal cual.
"""

import csv
from dataclasses import dataclass
from io import BytesIO, StringIO

from django.http import HttpResponse

from apps.core.exports import neutralize

CSV_TYPE = "text/csv; charset=utf-8"
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

# El ancho de columna que ninguna celda larga ensancha más allá: una descripción
# de 200 caracteres no tiene que hacer una hoja que no cabe en pantalla.
MAX_COLUMN_WIDTH = 40
DOCX_SIDE_MARGIN_IN = 0.6
BOM = "﻿"  # escrita como escape: un BOM literal en el fuente es invisible


def dated_filename(stem, as_of, extension):
    """`stem_AAAA-MM-DD.ext`: **el nombre de todo informe operativo** (S12).

    La fecha es la del corte del informe (`as_of`), no la de la descarga: dos
    archivos bajados en días distintos del mismo corte se reconocen como el mismo
    informe, y uno que se archiva en una carpeta dice de cuándo es. El informe
    mensual a la DGAC **no** pasa por aquí: su nombre es el código del documento.
    """
    return f"{stem}_{as_of:%Y-%m-%d}.{extension}"


def download(content, content_type, filename):
    """Una respuesta de descarga con el nombre ya decidido."""
    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@dataclass(frozen=True)
class Table:
    """Una tabla de informe: lo único que un informe entrega a la tubería.

    - `headers` y `rows`: la tabla. Los valores pueden ser cualquier cosa que
      `neutralize` entienda (texto, número, fecha, `None`).
    - `sheet`: el nombre de la hoja del XLSX.
    - `heading`: el título sobre la tabla en el CSV y el DOCX (el XLSX usa `sheet`).
    - `footer`: una fila de totales; va en negrita y dentro del filtro del XLSX.
    """

    headers: tuple
    rows: tuple
    sheet: str = ""
    heading: str = ""
    footer: tuple | None = None


def _footer_value(value):
    """Los números de una fila de totales se escriben como números."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    return neutralize(value)


def to_csv(tables, preamble=(), trailing_blank=False):
    """CSV con BOM (para que Excel detecte UTF-8) y fin de línea `\\r\\n`.

    `preamble`: filas sueltas antes de las tablas (título, fecha de corte). Entre
    una tabla y la siguiente va una fila en blanco; `trailing_blank` agrega una
    también al final (el catastro la tenía).
    """
    buffer = StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    for row in preamble:
        writer.writerow([neutralize(value) for value in row])
    if preamble:
        writer.writerow([])
    for index, table in enumerate(tables):
        if index:
            writer.writerow([])
        if table.heading:
            writer.writerow([neutralize(table.heading)])
        writer.writerow([neutralize(head) for head in table.headers])
        for row in table.rows:
            writer.writerow([neutralize(value) for value in row])
        if table.footer is not None:
            writer.writerow([_footer_value(value) for value in table.footer])
    if trailing_blank:
        writer.writerow([])
    return (BOM + buffer.getvalue()).encode("utf-8")


def to_xlsx(tables, preamble=()):
    """XLSX: una hoja por tabla, encabezado en negrita, panel y filtro anclados
    **en la fila de encabezados** y ancho de columna por contenido.

    `preamble`: frases sueltas arriba de cada hoja (el corte del catastro), con
    una fila en blanco de separación. El filtro se ancla en el encabezado y no en
    `sheet.dimensions`: con un preámbulo, `dimensions` tomaría una frase por
    título de columna.

    Se escribe por coordenada y no con `append`: un `append([])` avanza el cursor
    interno de openpyxl sin crear celda, y la negrita y el filtro quedaban un
    renglón corridos.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

    workbook = Workbook()
    for index, table in enumerate(tables):
        sheet = workbook.active if index == 0 else workbook.create_sheet()
        sheet.title = table.sheet or table.heading or "Hoja"

        for offset, sentence in enumerate(preamble, start=1):
            sheet.cell(row=offset, column=1, value=neutralize(sentence))
        header_row = len(preamble) + 2 if preamble else 1
        for column, head in enumerate(table.headers, start=1):
            sheet.cell(
                row=header_row, column=column, value=neutralize(head)
            ).font = Font(bold=True)
        row_number = header_row
        for row_number, row in enumerate(table.rows, start=header_row + 1):
            for column, value in enumerate(row, start=1):
                sheet.cell(row=row_number, column=column, value=neutralize(value))
        if table.footer is not None:
            row_number += 1
            for column, value in enumerate(table.footer, start=1):
                sheet.cell(
                    row=row_number, column=column, value=_footer_value(value)
                ).font = Font(bold=True)

        sheet.freeze_panes = f"A{header_row + 1}"
        sheet.auto_filter.ref = (
            f"A{header_row}:{get_column_letter(len(table.headers))}{row_number}"
        )
        for column in sheet.columns:
            sheet.column_dimensions[column[0].column_letter].width = min(
                max(len(str(cell.value or "")) for cell in column) + 2,
                MAX_COLUMN_WIDTH,
            )

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def to_docx(title, blocks):
    """DOCX con la plantilla controlada: título, y luego los bloques en orden.

    Cada bloque es `("paragraph", texto)`, `("heading", texto)` o
    `("table", Table)`. Las tablas llevan el estilo de la plantilla y los
    márgenes laterales son los de siempre (0,6 pulgadas): cuatro columnas más no
    caben en los 1,25 por defecto de Word.
    """
    from docx import Document
    from docx.shared import Inches

    document = Document()
    document.add_heading(title, 0)
    for kind, payload in blocks:
        if kind == "paragraph":
            document.add_paragraph(payload)
        elif kind == "heading":
            document.add_heading(payload, level=1)
        elif kind == "table":
            grid = document.add_table(rows=1, cols=len(payload.headers))
            grid.style = "Light Shading Accent 1"
            for cell, header in zip(grid.rows[0].cells, payload.headers):
                cell.text = str(header)
            for row in payload.rows:
                for cell, value in zip(grid.add_row().cells, row):
                    cell.text = str(value)
        else:  # pragma: no cover - un bloque mal escrito es un error del informe
            raise ValueError(f"bloque desconocido: {kind!r}")
    for section in document.sections:
        section.left_margin = Inches(DOCX_SIDE_MARGIN_IN)
        section.right_margin = Inches(DOCX_SIDE_MARGIN_IN)
    output = BytesIO()
    document.save(output)
    return output.getvalue()


def cost_center_filter(params):
    """La faena pedida en `?cost_center=` o `None` (S6).

    Antes estaba escrita dos veces, en `compliance/report_views.py` y en
    `registry/report_views.py`. Un valor que no es un UUID, o de una faena
    archivada, es **«sin filtro»** y no un 500 ni «no hay nada»: llega de un
    marcador viejo o de un enlace pegado a mano.
    """
    from apps.core.views import lookup_by_pk
    from apps.registry.models import CostCenter

    raw = params.get("cost_center")
    if not raw:
        return None
    return lookup_by_pk(CostCenter.objects.filter(is_active=True), raw)
