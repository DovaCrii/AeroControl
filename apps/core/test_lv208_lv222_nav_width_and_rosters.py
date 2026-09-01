"""LV-208 y LV-222: el ancho de la navegación, y rosters que se leen parejos.

Dos pedidos del usuario que se tocan más de lo que parece: el ancho de la barra
decide cuánto espacio le queda al contenido, y la rejilla de los rosters se
reparte en ese espacio.

- `LV-208`, textual: *"se podía poner que la navegación poder agrandar o desplazar
  para poder regular el ancho de la barra"*. Tenía dos estados —abierta o en modo
  icono— y nada en medio.
- `LV-222`, textual: *"sigue viendo desalineado al buscar operador y RPA; buscar
  una forma de que el orden sea prolijo en las listas"*.

**Estos tests cubren lo que Python puede afirmar**: que los ganchos están en la
plantilla, que el CSS dice lo que debe decir, y que la accesibilidad del control
nuevo no depende del ratón. La lógica de JavaScript (límites, paso de teclado,
`localStorage` que lanza) se verificó ejecutando el archivo real con node —el repo
no tiene infraestructura de tests JS y el navegador integrado no compone— y esa
comprobación está en el registro de la fila, no acá.
"""

from pathlib import Path

import pytest
from django.urls import reverse

from apps.core.testing import login_as

CSS = Path("static/css/app.css")
BASE_TEMPLATE = Path("templates/base.html")
RESIZE_JS = Path("static/js/sidebar-resize.js")


def _css():
    return CSS.read_text(encoding="utf-8")


class TestTheNavigationWidthIsAdjustable:
    @pytest.mark.django_db
    def test_the_grip_reaches_the_page(self, db):
        client = login_as()

        body = client.get(reverse("dashboard")).content.decode()

        assert "sidebar-resizer" in body

    @pytest.mark.django_db
    def test_the_script_is_loaded(self, db):
        client = login_as()

        body = client.get(reverse("dashboard")).content.decode()

        assert "sidebar-resize.js" in body

    def test_the_grip_is_reachable_without_a_mouse(self):
        """Un control que sólo responde al ratón es inalcanzable con tabulador.

        `LV-185` fijó el precedente de medir la accesibilidad antes de dar un
        cambio visual por bueno. `role="separator"` con `tabindex` es lo que un
        lector de pantalla anuncia como movible, y las flechas son lo que lo
        mueve (verificado con node).
        """
        template = BASE_TEMPLATE.read_text(encoding="utf-8")

        assert 'role="separator"' in template
        assert 'tabindex="0"' in template
        assert "aria-orientation" in template

    def test_the_user_width_is_a_separate_token(self):
        """**El detalle que habría rota el botón de colapsar.**

        Una custom property se resuelve en el elemento donde se usa, así que un
        ancho escrito inline en `.sidebar` ganaría por especificidad de estilo
        inline y anularía `--ac-sidebar-width: 72px` del estado colapsado: el
        botón `<` dejaría de hacer nada en cuanto alguien tocara el borde una vez.
        Por eso el valor del usuario es un token aparte, escrito en
        `documentElement`, y la regla del colapso sigue ganando por ser más
        específica.
        """
        css = _css()

        assert "--ac-sidebar-width: var(--ac-sidebar-width-user, 280px);" in css
        # El JS escribe el token del usuario, nunca el ancho directamente.
        js = RESIZE_JS.read_text(encoding="utf-8")
        assert "'--ac-sidebar-width-user'" in js
        assert "documentElement.style.setProperty" in js

    def test_the_collapsed_state_still_wins(self):
        """Colapsar no se reemplaza: es lo que se usa para ganar pantalla de golpe."""
        css = _css()

        assert ".sidebar.is-collapsed {" in css
        assert "--ac-sidebar-width: 72px;" in css
        # Y con la barra colapsada el tirador no se ofrece: estirar una barra en
        # modo icono a 400 px de iconos centrados no es un estado útil.
        assert ".sidebar.is-collapsed .sidebar-resizer { display: none; }" in css

    def test_storage_access_is_guarded(self):
        """`localStorage` **lanza** en una ventana privada, no devuelve null.

        Encontrado escribiendo esta fila: dos de los cuatro accesos de `app.js` no
        estaban envueltos, y una excepción ahí no deja una preferencia sin
        recordar — corta la función. El menú habría quedado colapsado con su botón
        rotulado al revés.
        """
        app_js = Path("static/js/app.js").read_text(encoding="utf-8")

        # Ningún acceso crudo fuera de los dos ayudantes que sí atrapan.
        crudos = [
            line.strip()
            for line in app_js.splitlines()
            if "localStorage." in line
            and "function" not in line
            and "//" not in line.split("localStorage.")[0]
        ]
        # Los únicos que quedan son los de dentro de `remember`/`recall` y los de
        # `collapsedGroups`, todos dentro de un `try`.
        assert all(
            "try" in app_js[max(0, app_js.find(line) - 120) : app_js.find(line)]
            for line in crudos
        ), crudos


class TestTheRostersReadEvenly:
    def test_the_grid_replaced_the_multicolumn_layout(self):
        """La causa del desalineado era `column-width`.

        En multicolumna nada relaciona la altura de un elemento con la del vecino,
        así que un nombre de dos líneas corre su columna y desalinea la de al
        lado. En una rejilla las celdas de una fila comparten altura por
        definición.
        """
        css = _css()
        roster = css[
            css.index(".roster-options {") : css.index(".roster-options.is-invalid")
        ]

        assert "display: grid;" in roster
        assert "grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));" in roster
        assert "column-width" not in roster

    def test_the_checkboxes_align_to_the_top_of_their_row(self):
        """Sin esto el síntoma vuelve dentro de la rejilla.

        `.form-check` centraría verticalmente, así que la casilla de un rótulo
        corto quedaría a media altura de su vecina de tres líneas — la casilla "a
        media altura" que el usuario fotografió.
        """
        css = _css()
        roster = css[
            css.index(".roster-options {") : css.index(".roster-options.is-invalid")
        ]

        assert "align-items: start;" in roster

    def test_the_checkbox_and_its_label_sit_side_by_side(self):
        """**El desorden que la medición no veía y la captura sí.**

        Con la rejilla puesta, los `top` de todas las casillas de una fila ya
        coincidían al milímetro — medido en el navegador— y en pantalla la lista
        seguía torcida. `.form-check` de Bootstrap pone el input con `float: left`,
        así que una etiqueta que no entra en una línea **baja por debajo del
        float** y arranca pegada al margen izquierdo, con la casilla flotando sola
        arriba. Con la etiqueta de una aeronave —matrícula, modelo y serie
        (`R5.5`)— eso era la mayoría de las filas.

        Verificado midiendo el desplazamiento del texto respecto a la casilla: con
        flex, las once opciones lo tienen a +7 px y en la misma línea.
        """
        css = _css()
        option = css[
            css.index(".roster-option {") : css.index(
                ".roster-option .form-check-label"
            )
        ]

        assert "display: flex;" in option
        assert "align-items: flex-start;" in option
        # Y el float de Bootstrap explícitamente anulado, que es la causa.
        assert (
            "float: none;" in css[css.index(".roster-option .form-check-input") :][:220]
        )

    def test_the_minimum_column_width_from_lv38_is_preserved(self):
        """210 px es medida, no gusto: es el ancho con que un nombre no se parte."""
        css = _css()

        assert "minmax(210px, 1fr)" in css

    @pytest.mark.django_db
    def test_the_roster_still_has_its_search_and_counter(self, db):
        """`LV-222` no debía costar lo que `LV-151` ganó.

        No se adoptó el desplegable con buscador que el usuario propuso: estos
        campos son de selección múltiple y `LV-151` eligió la rejilla justamente
        para que lo elegido se vea de un vistazo. Este test es la guarda de que
        arreglar la alineación no se llevó el buscador ni el contador.
        """
        from apps.registry.models import CostCenter, Operator

        cc = CostCenter.objects.create(code="CC1", name="Uno", operates_flights=True)
        Operator.objects.create(
            employee_id="P1", full_name="Francisca Fredes Araya", cost_center=cc
        )
        client = login_as("add_flightpermission", "view_flightpermission")

        body = client.get(reverse("permission-create")).content.decode()

        assert "data-roster-search" in body
        assert "data-roster-count" in body
        assert "Francisca Fredes Araya" in body
