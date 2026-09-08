"""El reparto de las tablas del informe en hojas, para que nada se pierda.

**El defecto que esto cierra, medido y no supuesto.** El 2026-09-08, con 15
permisos vigentes, el cuerpo de la página 3 terminaba en **1487 px** de una hoja
de 1123: 427 px por encima del pie y 364 px fuera de la hoja, donde
`overflow: hidden` los recortaba. Un papel que va firmado a la DGAC diciendo
«detalle permiso a permiso» y que pierde filas sin avisar es lo más grave que
este informe puede hacer, y lo encontró el usuario mirando la pantalla.

⚠️ **Y el primer arreglo también estuvo mal, que es la parte instructiva.** Usaba
un solo alto de fila, 45 px, medido sobre filas de uno o dos operadores. Con
permisos de **cuatro** operadores designados —lo que tiene producción— la celda
de nombres envuelve a tres líneas, la fila pasa a 60 px, y la última volvía a
quedar 70 px por debajo del pie. Un promedio disfrazado de caso peor. Por eso el
reparto es por presupuesto de píxeles y cada fila se estima por su contenido.
"""

import pytest

from apps.reporting.pagination import (
    CLOSING_PX,
    FOOTER_TOP_PX,
    ROW_BASE_PX,
    paginate,
    row_px,
    sheet_budget_px,
    sheets_for,
)


def _row(operators=1, aircraft=1):
    return {
        "operators": [f"Operador {n}" for n in range(operators)],
        "aircraft": [f"RPA-{n}" for n in range(aircraft)],
    }


class TestWhatARowMeasures:
    def test_one_operator_is_the_base(self):
        assert row_px(_row(operators=1)) == ROW_BASE_PX

    def test_two_names_still_fit_on_one_line(self):
        """La columna es `1fr` de una rejilla de siete y el cuerpo baja a 8,2 px
        (`.rpt-people`) justamente para que quepan dos nombres completos."""
        assert row_px(_row(operators=2)) == ROW_BASE_PX

    def test_four_operators_wrap_and_the_row_grows(self):
        """⚠️ El caso que rompió el primer arreglo: medido en el navegador, una
        fila de cuatro operadores mide **60 px** contra los 45 de una de dos."""
        assert row_px(_row(operators=4)) == 60

    def test_the_tallest_multivalued_cell_wins(self):
        """Van una al lado de la otra, así que la fila mide lo que mida la peor.
        Las aeronaves van una por línea —la plantilla las separa con `<br>`— así
        que tres aeronaves pesan como cinco o seis operadores."""
        assert row_px(_row(operators=1, aircraft=3)) == row_px(
            _row(operators=6, aircraft=1)
        )

    def test_a_row_with_nothing_still_takes_a_line(self):
        """Un permiso sin operadores cargados dibuja un guion, no una celda de
        alto cero."""
        assert row_px({}) == ROW_BASE_PX
        assert row_px({"operators": [], "aircraft": []}) == ROW_BASE_PX


class TestTheBudgetOfASheet:
    def test_the_first_sheet_has_less_room(self):
        """Carga además el ciclo de vigencia y los cuatro indicadores."""
        assert sheet_budget_px(first=True, last=False) < sheet_budget_px(
            first=False, last=False
        )

    def test_the_last_sheet_reserves_the_closing_blocks(self):
        """La observación del período y la leyenda cierran la sección, y su alto
        se descuenta de esa hoja y no de las otras."""
        assert sheet_budget_px(first=False, last=True) == (
            sheet_budget_px(first=False, last=False) - CLOSING_PX
        )

    def test_a_single_sheet_section_is_the_tightest_case(self):
        """Es primera y última a la vez."""
        budgets = [
            sheet_budget_px(first=True, last=True),
            sheet_budget_px(first=True, last=False),
            sheet_budget_px(first=False, last=True),
            sheet_budget_px(first=False, last=False),
        ]

        assert budgets[0] == min(budgets)

    def test_no_budget_ever_reaches_the_footer(self):
        """⚠️ La afirmación de fondo: el presupuesto más generoso, sumado a donde
        empieza la primera fila, tiene que quedar por debajo del pie. Si alguien
        sube un techo sin mirar, esto cae antes de que el informe recorte."""
        from apps.reporting.pagination import CONTINUATION_ROW_TOP_PX

        assert (
            CONTINUATION_ROW_TOP_PX + sheet_budget_px(first=False, last=False)
            < FOOTER_TOP_PX
        )


class TestNothingIsEverDropped:
    """La propiedad que importa, sobre la que todo lo demás es detalle."""

    @pytest.mark.parametrize("count", [0, 1, 5, 9, 14, 15, 40, 120])
    def test_every_row_lands_on_exactly_one_sheet(self, count):
        rows = [_row(operators=4) for _ in range(count)]

        sheets = paginate(rows)

        assert sum(len(sheet) for sheet in sheets) == count
        # Y en orden: el folio de un permiso no puede saltar de hoja.
        assert [row for sheet in sheets for row in sheet] == rows

    @pytest.mark.parametrize("count", [1, 5, 14, 15, 40])
    def test_no_sheet_exceeds_its_budget(self, count):
        rows = [_row(operators=4) for _ in range(count)]

        sheets = paginate(rows)

        for index, sheet in enumerate(sheets):
            budget = sheet_budget_px(first=index == 0, last=index == len(sheets) - 1)
            used = sum(row_px(row) for row in sheet)
            # Una hoja con una sola fila puede pasarse del presupuesto: no hay
            # dónde más ponerla, y partir una fila no es una opción. Es el único
            # caso, y el margen de seguridad lo absorbe.
            assert used <= budget or len(sheet) == 1, (index, used, budget)

    def test_an_empty_section_still_gets_one_sheet(self):
        """La sección existe en el documento y tiene que decir «ningún permiso
        vigente al corte» en su hoja."""
        assert paginate([]) == [[]]

    def test_no_blank_sheet_is_emitted(self):
        """Una hoja vacía con su pie numerado le dice al lector que le falta
        contenido que nunca existió."""
        sheets = paginate([_row() for _ in range(3)])

        assert all(sheets)

    def test_tall_rows_need_more_sheets_than_short_ones(self):
        """La comprobación de que la estimación se usa de verdad: las mismas
        veinte filas, con cuatro operadores cada una, no caben donde caben con
        uno."""
        short = paginate([_row(operators=1) for _ in range(20)])
        tall = paginate([_row(operators=6) for _ in range(20)])

        assert len(tall) > len(short)


class TestWhatTheTemplateGets:
    def test_the_first_and_last_flags_mark_the_ends(self):
        sheets = sheets_for([_row(operators=4) for _ in range(30)])

        assert sheets[0]["first"] and not sheets[0]["last"]
        assert sheets[-1]["last"] and not sheets[-1]["first"]
        assert all(not sheet["first"] and not sheet["last"] for sheet in sheets[1:-1])

    def test_a_single_sheet_is_both(self):
        sheets = sheets_for([_row()])

        assert sheets[0]["first"] and sheets[0]["last"]

    def test_the_page_number_is_not_assigned_here(self):
        """⚠️ Depende de cuántas hojas traen las otras secciones, y sólo la vista
        que arma el documento entero lo sabe. Repartirlo en dos lugares es cómo
        un informe termina con dos hojas numeradas igual."""
        sheets = sheets_for([_row()])

        assert "page" not in sheets[0]
