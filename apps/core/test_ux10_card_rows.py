"""`UX-10`: la fila se apila como tarjeta bajo 768 px.

**Medido antes de escribir nada**: la lista de aeronaves mide **900 px de tabla
dentro de un contenedor de 356** en una pantalla de 390. Leer una fila en faena
obliga a arrastrar de lado, con guantes, y volver a empezar en la siguiente.

⚠️ **Esto revierte una decisión deliberada de `LV-162`**, y por eso el archivo lo
dice: esa fila puso `min-width: 900px` en `.table-normalized` con el motivo
escrito —*"por debajo de esto scrollea"*—, y era la elección correcta **cuando la
única alternativa era aplastar las columnas**. Con la fila apilada ya no hay
columnas que aplastar, así que el mínimo dejó de proteger algo.

El rótulo de cada celda lo pone `worktable.js` **leyéndolo del `<th>`**: la
alternativa era escribir `data-label` en las 58 tablas, un cambio irrevisable
que además duplicaría cada encabezado para que se separen la primera vez que
alguien renombre una columna.
"""

import re
from pathlib import Path

from django.conf import settings

CSS = Path(settings.BASE_DIR) / "static" / "css" / "app.css"
JS = Path(settings.BASE_DIR) / "static" / "js" / "worktable.js"
BASE = Path(settings.BASE_DIR) / "templates" / "base.html"


def _mobile_block():
    css = CSS.read_text(encoding="utf-8")
    start = css.index("@media (max-width: 767.98px)")
    return css[start : css.index("\n}\n", css.index(".print-stamp", start))]


class TestTheRowStacks:
    def test_the_cells_become_blocks_under_the_breakpoint(self):
        block = _mobile_block()

        assert ".table-responsive td" in block
        assert "display: block" in block

    def test_the_fixed_minimum_width_is_lifted(self):
        """**El que hace que la fila deje de desbordar.**

        Sin esto, apilar las celdas no alcanza: la tabla conserva sus 900 px de
        mínimo y el contenedor sigue teniendo que desplazarse. Medido: 900 → 456
        → 356 al levantar el mínimo y dejar encoger las celdas.
        """
        block = _mobile_block()

        assert ".table-responsive .table-normalized" in block
        assert "min-width: 0" in block

    def test_the_cells_are_allowed_to_shrink(self):
        """Un ítem flex trae `min-width: auto` y **no encoge por debajo de su
        contenido**: sin los tres juntos, la celda de Seguro medía 447 px en un
        contenedor de 356 y la tabla seguía desbordando aunque las filas ya
        fueran bloques."""
        block = _mobile_block()

        assert "flex-wrap: wrap" in block
        assert "overflow-wrap: anywhere" in block

    def test_the_header_is_hidden_without_leaving_the_accessibility_tree(self):
        """`display: none` lo sacaría del árbol de accesibilidad, y un lector de
        pantalla perdería los nombres de columna que la vista sigue usando."""
        block = _mobile_block()
        header = block[block.index(".table-responsive thead") :][:220]

        assert "position: absolute" in header
        assert "display: none" not in header


class TestTheLabelComesFromTheHeader:
    def test_the_script_reads_the_th_and_is_loaded(self):
        """Escribir `data-label` en las 58 tablas habría duplicado cada
        encabezado —el del `<th>` y el del atributo— para que se separen la
        primera vez que alguien renombre una columna."""
        script = JS.read_text(encoding="utf-8")

        assert "thead th" in script
        assert "data-label" in script
        assert "js/worktable.js" in BASE.read_text(encoding="utf-8")

    def test_it_relabels_after_an_htmx_swap(self):
        """La paginación y los filtros reemplazan `#table-body` sin recargar:
        las filas nuevas llegarían sin rótulo y la tarjeta se vería a medias."""
        assert "htmx:afterSwap" in JS.read_text(encoding="utf-8")

    def test_a_spanning_cell_gets_no_label(self):
        """Las filas de agrupación y la de "sin resultados" abarcan varias
        columnas: rotularlas con el nombre de la primera diría algo falso."""
        assert "colSpan > 1" in JS.read_text(encoding="utf-8")

    def test_the_actions_cell_gets_no_label(self):
        """Son botones. Un rótulo delante no agrega nada y le roba la mitad del
        ancho a la fila más angosta."""
        script = JS.read_text(encoding="utf-8")

        assert re.search(r'querySelector\("\.btn, button, form"\)', script)


class TestItIsNotInlineJavaScript:
    def test_the_script_lives_in_a_file(self):
        """La CSP de esta aplicación no lleva `unsafe-inline` en `script-src`:
        un `<script>` con cuerpo en la plantilla no se ejecutaría en producción
        y las tarjetas saldrían sin rótulo, sólo allá."""
        assert JS.exists()
        assert "<script>" not in BASE.read_text(encoding="utf-8")
