"""`UX-24`, `UX-25` y `UX-28`: la fase E, la de terreno.

- **`UX-24`** — bajo 768 px la búsqueda global desaparecía y no quedaba nada en
  su lugar: en el teléfono, que es donde se trabaja en faena, la aplicación no
  tenía búsqueda.
- **`UX-25`** — la paleta de comandos. *Por qué está en el plan:* quien trabaja
  alertas entra veinte veces al día; y ningún competidor del sector la documenta,
  así que además se ve en una demostración.
- **`UX-28`** — la alternativa sin arrastre del editor geo (WCAG 2.2 §2.5.7).

Las dos primeras son el **mismo componente**: en una pantalla angosta la paleta
es pantalla completa, así que la lupa de la barra la abre y no hay una segunda
cosa que mantener.
"""

import re
from pathlib import Path

from django.conf import settings

BASE = (Path(settings.BASE_DIR) / "templates" / "base.html").read_text(encoding="utf-8")
JS = Path(settings.BASE_DIR) / "static" / "js"
PALETTE = (JS / "command-palette.js").read_text(encoding="utf-8")
APP_JS = (JS / "app.js").read_text(encoding="utf-8")
INSPECTOR = (JS / "geo" / "inspector.js").read_text(encoding="utf-8")
CSS = (Path(settings.BASE_DIR) / "static" / "css" / "app.css").read_text(
    encoding="utf-8"
)


def _without_line_comments(source):
    """Los comentarios de línea de un archivo de JS.

    Basta con `//` al principio del renglón: los archivos de este proyecto
    comentan así, y una versión que entendiera cadenas y expresiones regulares
    sería un analizador de JavaScript dentro de un test.
    """
    return "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith("//")
    )


class TestTheSearchCameBackToThePhone:
    """`UX-24`. *Criterio:* un icono de lupa en la barra que abre la búsqueda a
    pantalla completa."""

    def test_the_bar_carries_a_magnifier_below_md(self):
        assert re.search(r'id="palette-open"', BASE)
        opener = BASE.split('id="palette-open"')[0].rsplit("<button", 1)[1]
        assert "d-md-none" in opener

    def test_and_the_desktop_box_is_still_the_one_that_hides(self):
        """La lupa **sustituye** a la caja bajo 768 px, no se suma: las dos a la
        vez serían dos búsquedas en una barra que no tiene ancho para una."""
        assert "global-search d-none d-md-flex" in BASE

    def test_the_panel_fills_the_screen_on_a_phone(self):
        # El archivo tiene varias consultas al mismo ancho, así que se busca la
        # que contiene la regla de la paleta y no "la última": cortar por el
        # separador y quedarse con un extremo mide la que casualmente esté ahí.
        block = next(
            part
            for part in CSS.split("@media (max-width: 767.98px)")
            if ".command-palette-panel" in part.split("\n@media")[0]
        )

        assert "height: 100%" in block.split("\n@media")[0]


class TestThePalette:
    """`UX-25`."""

    def test_it_opens_with_the_shortcut_on_both_platforms(self):
        """`Ctrl` y `⌘`: la mitad del equipo trabaja en Windows y la otra no."""
        assert "event.ctrlKey || event.metaKey" in PALETTE
        assert "'k'" in PALETTE

    def test_the_destinations_come_from_the_menu(self):
        """⚠️ Y no de una lista propia. El menú ya esconde lo que esta persona no
        puede ver, así que la paleta hereda los permisos sin preguntarle nada al
        servidor — una lista propia habría ofrecido rutas que terminan en un 403,
        que es `LV-130`: enseñar a desconfiar de la pantalla."""
        assert "#sidebar a[href]" in PALETTE

    def test_it_rereads_the_menu_on_every_open(self):
        """Una lectura única al cargar quedaría corta el día que una pantalla se
        dibuje después."""
        assert "entries = readMenu()" in PALETTE.split("function open()", 1)[1]

    def test_the_typed_text_is_never_written_as_markup(self):
        """La primera opción lleva dentro lo que la persona tecleó."""
        assert "textContent = entry.label" in PALETTE
        # Sin los comentarios: el archivo **explica** por qué no usa `innerHTML`,
        # y buscarlo en el texto crudo encontraría esa explicación. Mismo
        # tropiezo que ya obligó a `without_template_comments` del lado HTML.
        assert "innerHTML" not in _without_line_comments(PALETTE)

    def test_the_global_search_is_always_offered(self):
        """Escribir la matrícula de una aeronave no se parece al nombre de
        ninguna pantalla, y ése es justo el caso en que la paleta tiene que
        servir de algo: la búsqueda va primero incluso sin coincidencias."""
        render = PALETTE.split("function render(", 1)[1]

        assert "found.unshift(" in render
        assert "encodeURIComponent(query)" in render

    def test_escape_belongs_to_the_palette_while_it_is_open(self):
        """⚠️ Los dos escuchan en el `document`, y ahí `stopPropagation` no
        detiene a otro oyente del mismo elemento; `stopImmediatePropagation`
        sólo alcanza a los registrados después, o sea que dependería del orden de
        las etiquetas `<script>`. `app.js` pregunta, y así no depende de nada:
        sin eso, un `Esc` para cerrar la paleta cerraba además la barra lateral,
        que la persona no había tocado."""
        assert re.search(
            r"getElementById\('command-palette'\)[\s\S]{0,120}palette\.hidden\) return",
            APP_JS,
        )

    def test_the_labels_do_not_live_in_the_javascript(self):
        """El archivo es estático y no pasa por gettext."""
        assert "dataset.searchLabel" in PALETTE
        assert "data-search-label=" in BASE


class TestTheGeoEditorNoLongerNeedsDragging:
    """`UX-28` (WCAG 2.2 §2.5.7). El criterio de éxito pide que **toda**
    operación que se hace arrastrando tenga alternativa de un solo puntero, y
    mover un vértice no la tenía: quien no puede arrastrar no podía corregir una
    coordenada."""

    def test_the_popup_lists_the_vertices(self):
        assert "buildCoordinateTable" in INSPECTOR
        assert "geo-coord-input" in INSPECTOR

    def test_the_closing_vertex_of_a_ring_is_hidden(self):
        """⚠️ El último punto de un anillo KML repite el primero. Mostrarlo
        obligaría a editar la misma esquina dos veces, y olvidar la segunda deja
        el polígono abierto — un archivo que el validador rechaza por un descuido
        que la pantalla invitó a cometer."""
        assert "closed ? ring.slice(0, -1) : ring" in INSPECTOR
        assert "points.concat([points[0]])" in INSPECTOR

    def test_a_bad_number_rejects_the_whole_table(self):
        """Aplicar la mitad dejaría una figura que nadie pidió, y la persona no
        vería cuál mitad."""
        read = INSPECTOR.split("box.readGeometry", 1)[1]

        assert "Number.isFinite" in read
        assert "return null" in read

    def test_an_empty_cell_is_not_a_zero(self):
        """⚠️ Y ésta es la que `isFinite` sola no atrapaba. Un
        `<input type="number">` con basura dentro devuelve `""` —el navegador
        rechaza lo tipeado y no lo refleja en `value`— y `Number("")` es **0**,
        que pasa `isFinite` sin chistar. O sea que escribir una letra en una
        latitud mandaba el vértice al ecuador **en silencio**, y quedaba
        guardado. Encontrado en el navegador, con la tabla recién escrita."""
        assert 'raw === "" ? NaN : Number(raw)' in INSPECTOR

    def test_the_screen_reads_lat_lon_and_the_document_keeps_lon_lat(self):
        """En pantalla va como se dicta una coordenada y como se transcribe a
        SIGO; en el archivo va como manda GeoJSON. La vuelta se hace al aplicar,
        una sola vez — invertir el documento habría cambiado el formato por una
        comodidad de pantalla."""
        assert "[1, 0].map" in INSPECTOR
        assert "[number(pair.lon), number(pair.lat)]" in INSPECTOR

    def test_the_table_scrolls_instead_of_covering_the_map(self):
        """Un círculo llega poligonalizado en 64 vértices — los KMZ de Trimble de
        CC 738— y sin tope el globo taparía el mapa entero."""
        assert re.search(r"\.geo-coord-table\s*{[^}]*overflow-y:\s*auto", CSS)
