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
        # 29 desde `LV-262`: «Registros operacionales» y «Cumplimiento mensual»
        # son ahora una entrada, el cierre mensual, y el simbolo de la primera
        # salio con ella. Antes, 30 desde `UX-27`: «¿Puedo volar?» trajo su propio simbolo, como antes
        # lo hizo la bandeja de trabajo (`UX-13`). El numero se sube al agregar
        # una entrada de menu -- que es el punto de que sea exacto: obliga a
        # mirar el sprite en vez de dejar un `<use>` apuntando a un id que no
        # existe, que no falla, dibuja nada.
        assert len(_symbol_ids()) == 29

    def test_the_menu_no_longer_draws_the_icons_itself(self):
        """El criterio de la fila: `base.html` pierde los `path` de navegación.

        Quedan los de los controles que **no** son de navegación —el botón de
        menú, la lupa, el chevron de los grupos, el sol y la luna del tema—, que
        no son iconos de sección y no comparten su vocabulario de color.
        """
        source = BASE.read_text(encoding="utf-8")

        assert '<svg class="nav-icon" viewBox' not in source
        assert source.count("<use href=") == 29

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


class TestNoTwoSymbolsDrawTheSameThing:
    """⚠️ **Una garantía que este mismo cambio debilitó, restaurada donde ahora
    vive.**

    `R103` nació de un defecto que el usuario reportó: dos entradas del menú con
    el mismo icono. Su test compara el **dibujo** de cada `<a class="nav-item">`,
    y mientras el `<svg>` estaba en línea ese dibujo eran los trazos de verdad.

    Al mover los iconos al sprite, lo que ese test compara pasó a ser el
    `<use href="…#icon-X">`, o sea **el identificador**. Sigue cazando dos
    entradas que apunten al mismo símbolo —y con eso el gate siguió verde, sin
    que nada avisara— pero **dejó de ver dos símbolos distintos con el mismo
    trazo dentro**, que es exactamente el defecto original con otra forma.

    Así que la comparación de trazos se hace acá, sobre el sprite. Es el mismo
    modo de fallo del que este repo ya se quemó: un guardián que sigue en verde
    porque mide otra cosa.
    """

    def test_every_symbol_has_its_own_drawing(self):
        symbols = re.findall(
            r'<symbol id="([^"]+)"[^>]*>(.*?)</symbol>', _sprite(), re.DOTALL
        )
        assert len(symbols) == 29

        by_drawing = {}
        for sid, drawing in symbols:
            # Sin espacios: dos trazos que sólo difieren en saltos de línea son
            # el mismo icono para quien lo mira, y un reformateo no debería
            # hacer pasar el test por casualidad. Mismo criterio que `R103`.
            by_drawing.setdefault(re.sub(r"\s+", "", drawing), []).append(sid)

        repeated = {ids[0]: ids for ids in by_drawing.values() if len(ids) > 1}

        assert not repeated, "símbolos con el mismo dibujo:\n" + "\n".join(
            "  " + " ≡ ".join(ids) for ids in repeated.values()
        )
