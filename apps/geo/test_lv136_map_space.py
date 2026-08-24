"""LV-136: más espacio para el mapa, y "Ampliar" para tener la pantalla entera.

Pedido del usuario mirando la ficha: *"evaluar una opción para darle más espacio
al mapa o ver una opción de utilizar mejor el espacio para editar y trabajar con
más espacio"*. El mapa medía **480 px fijos**, así que en una pantalla de 1080
sobraba la mitad del alto y dibujar obligaba a arrastrar el lienzo en vez de
mirarlo.

**Estos tests leen los archivos**, no una página renderizada ni el navegador: lo
que cambió es alto, posición y una clase que aplica JavaScript, y nada de eso se
puede comprobar desde el cliente de pruebas de Django — el mismo criterio del test
de iconos de `R10.3`. Lo que se fija son las decisiones: que el alto dependa de la
ventana, que el estado ampliado exista y quede **bajo** el modal de Bootstrap, y
que el mapa ampliado siga siendo el mismo elemento y no una copia.
"""

from django.conf import settings

CSS = settings.BASE_DIR / "static" / "css" / "app.css"
MAIN_JS = settings.BASE_DIR / "static" / "js" / "geo" / "main.js"
EXPAND_JS = settings.BASE_DIR / "static" / "js" / "geo" / "expand.js"
TEMPLATE = settings.BASE_DIR / "templates" / "geo" / "plan_detail.html"


def _css():
    return CSS.read_text(encoding="utf-8")


class TestTheMapGrowsWithTheWindow:
    def test_the_height_is_no_longer_a_fixed_number(self):
        css = _css()

        # `clamp` da piso, techo y proporción en una sola declaración: 480 px
        # sigue siendo el mínimo para una pantalla baja.
        assert "height: clamp(480px, 68vh, 900px)" in css
        assert "height: 480px" not in css

    def test_the_layers_panel_matches_the_map_height(self):
        """Antes eran dos números (480 y 480) que había que acordarse de mover
        juntos; ahora la altura la fija el contenedor y el panel la hereda."""
        css = _css()

        assert "max-height: 100%" in css


class TestTheExpandedState:
    def test_it_covers_the_window_but_stays_under_the_modal(self):
        """1045 está sobre la barra lateral (1040) y bajo el modal de Bootstrap
        (1055), para que un diálogo abierto desde el mapa siga quedando encima."""
        css = _css()
        bloque = css.split(".geo-map-card.geo-expanded {")[1].split("}")[0]

        assert "position: fixed" in bloque
        assert "inset: 0" in bloque
        assert "z-index: 1045" in bloque

    def test_the_page_behind_it_does_not_scroll(self):
        """Arrastrar el mapa movería la página en vez del lienzo."""
        assert "body.geo-expanded-open" in _css()

    def test_leaflet_is_told_the_container_changed_size(self):
        """El único requisito funcional de Leaflet al cambiar el tamaño del
        contenedor: sin `invalidateSize()` el lienzo queda del tamaño viejo, con
        las teselas cortadas y los clics desplazados de lo que se ve."""
        assert "invalidateSize()" in EXPAND_JS.read_text(encoding="utf-8")

    def test_escape_leaves(self):
        """En modo ampliado no queda a la vista ningún otro elemento de la app:
        sin Escape, la única salida visible sería el propio botón."""
        source = EXPAND_JS.read_text(encoding="utf-8")

        assert '"Escape"' in source

    def test_it_is_the_same_map_and_not_a_second_one(self):
        """La clave del diseño: ampliar es un estado de la tarjeta, así que los
        controles de dibujo, el panel de capas y Guardar siguen siendo los mismos
        elementos. Un modal con su propia copia del mapa sería un segundo editor
        que se desincroniza del primero."""
        template = TEMPLATE.read_text(encoding="utf-8")

        assert 'id="geo-map-card"' in template
        # Un solo contenedor de mapa en la ficha.
        assert template.count('id="geo-map"') == 1

    def test_the_button_carries_both_labels_for_translation(self):
        """El texto lo cambia JavaScript, así que las dos etiquetas viajan desde
        el servidor en `data-`: traducirlas en el cliente exigiría un catálogo en
        JavaScript que este proyecto no tiene."""
        template = TEMPLATE.read_text(encoding="utf-8")

        assert "data-label-expand=" in template
        assert "data-label-collapse=" in template

    def test_main_wires_it_up(self):
        assert "installExpand" in MAIN_JS.read_text(encoding="utf-8")
