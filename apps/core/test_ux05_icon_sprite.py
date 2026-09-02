"""`UX-05`: los iconos del menú, en un solo archivo y referenciados por nombre.

`base.html` llevaba **55 `<path>` en línea**, veintiocho iconos escritos dentro
del marcado de navegación. El coste no es el peso: es que el archivo que define
la estructura del menú era también el que dibujaba, así que tocar un enlace
obligaba a leer por encima de un `d="M4 21V6l7-3 7 3v15"`.

⚠️ **Lo que este archivo protege por encima de todo**: que los símbolos **no
declaren color propio**. `LV-207` da un color por sección del menú, y un símbolo
con su `stroke` escrito adentro habría congelado los ocho colores dentro del
sprite — el menú entero se habría vuelto de un solo color sin que ningún test de
contraste se enterara, porque esos tests leen el CSS.
"""

import re
from pathlib import Path

from django.conf import settings

SPRITE = Path(settings.BASE_DIR) / "static" / "img" / "icons.svg"
BASE = Path(settings.BASE_DIR) / "templates" / "base.html"


def _sprite():
    return SPRITE.read_text(encoding="utf-8")


def _symbol_ids():
    return set(re.findall(r'<symbol id="([^"]+)"', _sprite()))


def _referenced_ids():
    return set(
        re.findall(r"icons\.svg' %\}#([a-z0-9-]+)", BASE.read_text(encoding="utf-8"))
    )


class TestThereIsOneSpriteAndTheMenuUsesIt:
    def test_the_sprite_exists_with_every_icon(self):
        assert SPRITE.exists()
        assert len(_symbol_ids()) == 28

    def test_the_menu_no_longer_draws_the_icons_itself(self):
        """El criterio de la fila: `base.html` pierde los `path` de navegación.

        Quedan los de los controles que **no** son de navegación —el botón de
        menú, la lupa, el chevron de los grupos, el sol y la luna del tema—, que
        no son iconos de sección y no comparten su vocabulario de color.
        """
        source = BASE.read_text(encoding="utf-8")

        assert '<svg class="nav-icon" viewBox' not in source
        assert source.count("<use href=") == 28

    def test_every_reference_points_at_a_symbol_that_exists(self):
        """**Un `<use>` a un id inexistente no falla: dibuja nada.**

        Es el modo de fallo de esta fila — un icono desaparece y la página sigue
        respondiendo 200. Por eso se cruzan los dos conjuntos en vez de contar.
        """
        missing = _referenced_ids() - _symbol_ids()

        assert not missing, sorted(missing)

    def test_no_symbol_is_left_unused(self):
        """Al revés: un símbolo que nadie referencia es peso muerto que se
        arrastra en cada carga."""
        orphan = _symbol_ids() - _referenced_ids()

        assert not orphan, sorted(orphan)

    def test_the_ids_are_named_after_their_destination(self):
        """`icon-3` obliga a abrir el archivo para saber cuál es, y el nombre
        del destino ya estaba en `base.html` justo al lado."""
        assert "icon-dashboard" in _symbol_ids()
        assert "icon-permission-list" in _symbol_ids()
        for sid in _symbol_ids():
            assert sid.startswith("icon-"), sid


class TestTheSymbolsDoNotCarryTheirOwnColour:
    def test_no_symbol_declares_stroke_or_fill(self):
        """**El que importa.**

        `LV-207` pinta cada sección del menú con su color, y `.nav-icon` lo
        aplica con `currentColor`. Un `stroke="#..."` dentro del símbolo habría
        ganado y dejado el menú de un solo color — sin que ningún test de
        contraste se enterara, porque esos leen el CSS y no el sprite.
        """
        symbols = re.findall(r"<symbol .*?</symbol>", _sprite(), re.DOTALL)

        assert symbols
        for symbol in symbols:
            assert 'stroke="#' not in symbol, symbol[:80]
            assert 'fill="#' not in symbol, symbol[:80]

    def test_the_stylesheet_is_still_the_one_setting_the_colour(self):
        css = (Path(settings.BASE_DIR) / "static" / "css" / "app.css").read_text(
            encoding="utf-8"
        )

        assert ".nav-icon" in css
