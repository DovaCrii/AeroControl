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

    def test_operators_no_longer_grow_the_row(self):
        """⚠️ **LV-248, y el cambio de signo es a propósito.** Estos tests
        afirmaban que cuatro operadores hacían crecer la fila a 60 px —era cierto:
        la celda los listaba a todos y envolvía de dos en dos, y fue lo que rompió
        el primer reparto—. El usuario pidió un informe más corto con lo esencial y
        eligió recortar **exactamente eso**: la celda dice ahora «4 operadores», y
        la nómina completa va al anexo del final (`roster_row_px`). Así que ya no
        importa cuántos sean: la fila mide una línea."""
        assert row_px(_row(operators=4)) == ROW_BASE_PX
        assert row_px(_row(operators=12)) == ROW_BASE_PX

    def test_aircraft_still_do(self):
        """Las aeronaves siguen listándose, una por línea —la plantilla las separa
        con `<br>`—, así que son lo único que todavía hace crecer la fila."""
        from apps.reporting.pagination import ROW_LINE_PX

        assert row_px(_row(aircraft=3)) == ROW_BASE_PX + 2 * ROW_LINE_PX

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

    @pytest.mark.parametrize("shortfall", [0, 1, 2])
    def test_the_closing_blocks_always_get_their_room(self, shortfall):
        """⚠️ **LV-248.** Cuando todas las filas caben en la primera hoja *no
        final* —cuyo presupuesto no descuenta el cierre— pero no en una sola hoja,
        la hoja final quedaba vacía, se descartaba, y la primera pasaba a ser la
        última **sin el espacio del cierre**: la observación, la leyenda y las
        solicitudes en trámite quedaban bajo el pie, recortadas en silencio. Se vio
        con los números de entonces —once filas de 45 px, 495 contra 500—, y se
        construye acá desde las constantes y no con números fijos, para que el caso
        siga ejercitándose cuando se vuelva a medir."""
        closing = 313
        non_final = sheet_budget_px(first=True, last=False, closing_px=closing)
        single = sheet_budget_px(first=True, last=True, closing_px=closing)
        count = non_final // ROW_BASE_PX - shortfall
        # El caso existe sólo si no caben en una hoja sola: si no, no hay trampa.
        assert count * ROW_BASE_PX > single
        rows = [_row(operators=4) for _ in range(count)]

        sheets = paginate(rows, closing_px=closing)

        last = sheets[-1]
        budget = sheet_budget_px(first=len(sheets) == 1, last=True, closing_px=closing)
        assert sum(row_px(row) for row in last) <= budget or len(last) == 1
        assert [row for sheet in sheets for row in sheet] == rows

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
        veinte filas, con cuatro aeronaves cada una, no caben donde caben con una.
        LV-248: con aeronaves y no con operadores, que ya no alargan la fila."""
        short = paginate([_row(aircraft=1) for _ in range(20)])
        tall = paginate([_row(aircraft=4) for _ in range(20)])

        assert len(tall) > len(short)

    def test_the_same_permits_now_take_fewer_sheets(self):
        """⚠️ **La mitad visible del pedido**: *"que el informe sea más corto, con
        lo esencial"*. Veinte permisos de cuatro operadores —lo que tiene
        producción— necesitaban una hoja más cuando la celda listaba los nombres;
        ahora caben donde caben veinte de uno."""
        four = paginate([_row(operators=4) for _ in range(20)])
        one = paginate([_row(operators=1) for _ in range(20)])

        assert len(four) == len(one)


class TestTheRosterAnnex:
    """LV-248: la nómina completa, fuera de la tabla de permisos."""

    def test_names_wrap_four_to_a_line(self):
        from apps.reporting.pagination import (
            ROSTER_LINE_PX,
            ROSTER_ROW_BASE_PX,
            roster_row_px,
        )

        assert roster_row_px(_row(operators=4)) == ROSTER_ROW_BASE_PX
        assert roster_row_px(_row(operators=5)) == ROSTER_ROW_BASE_PX + ROSTER_LINE_PX

    def test_the_annex_never_drops_a_row_either(self):
        """La propiedad de fondo, la misma que la tabla de permisos: todo permiso
        cae en exactamente una hoja, y en orden."""
        from apps.reporting.pagination import (
            ROSTER_FIRST_ROW_TOP_PX,
            roster_row_px,
        )

        rows = [_row(operators=9) for _ in range(60)]

        sheets = paginate(
            rows,
            closing_px=0,
            estimate=roster_row_px,
            first_top=ROSTER_FIRST_ROW_TOP_PX,
        )

        assert [row for sheet in sheets for row in sheet] == rows


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
