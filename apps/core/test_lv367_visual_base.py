"""LV-367 (Visual v3), fase 1: la base visual. Tokens de profundidad e iconos de contenido.

Los contrastes se CALCULAN (mismas funciones que `test_lv315`), no se leen de un navegador:
`--id-edge` es el borde de figuras y tarjetas, así que debe llegar a 3:1 (WCAG 1.4.11) contra las tres
superficies donde se dibuja, y el texto de la app debe leerse (4,5:1) sobre `--id-tile`. Además fija las
reglas que toda la tanda comparte: la capa sólo define `--id-*`, hay UN bloque de movimiento y nada se
desplaza en horizontal.
"""

import importlib.util
import re

import pytest

from apps.core.test_lv315_identity_foundation import APP, IDENTITY, ROOT


def _load_script():
    spec = importlib.util.spec_from_file_location(
        "contrast_script", ROOT / ".claude/skills/diseno-ui/scripts/contrast.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CONTRAST = _load_script()
_THEMES = CONTRAST.load(
    [str(ROOT / "static/css/app.css"), str(ROOT / "static/css/identity.css")]
)


def _theme_tokens(theme):
    """Tokens efectivos de cada tema, leídos como los lee `contrast.py` (claro y oscuro de verdad)."""
    raw = _THEMES["claro" if theme == "light" else "oscuro"]
    return {f"--{name}": value for name, value in raw.items()}


def _resolve(value, tokens):
    plain = {name[2:]: v for name, v in tokens.items()}
    return CONTRAST.resolve(plain, value)


def _contrast(a, b):
    return CONTRAST.ratio(CONTRAST.to_rgb(a), CONTRAST.to_rgb(b))


SPRITE = ROOT / "static" / "img" / "icons-ui.svg"
SKILL = ROOT / ".claude" / "skills" / "diseno-ui"
THEMES = ["light", "dark"]

# Símbolos del sprite de contenido que todavía no usa ninguna plantilla. Cada fase de la tanda saca
# los suyos de acá al usarlos; la lista vacía es la meta (el guardián de huérfanos de `icons.svg`
# aplica la misma regla al menú: un símbolo que nadie referencia es peso muerto).
PENDING = set()


def _symbols():
    return dict(
        re.findall(
            r'<symbol id="([^"]+)"[^>]*>(.*?)</symbol>',
            SPRITE.read_text(encoding="utf-8"),
            re.DOTALL,
        )
    )


def _templates():
    return "\n".join(
        p.read_text(encoding="utf-8") for p in (ROOT / "templates").rglob("*.html")
    )


class TestDepthTokens:
    @pytest.mark.parametrize("theme", THEMES)
    @pytest.mark.parametrize("surface", ["--ac-bg", "--ac-surface", "--id-tile"])
    def test_the_edge_reaches_3_to_1_on_every_surface_it_is_drawn_on(
        self, theme, surface
    ):
        tokens = _theme_tokens(theme)
        edge = _resolve(tokens["--id-edge"], tokens)
        assert _contrast(edge, _resolve(tokens[surface], tokens)) >= 3, (theme, surface)

    @pytest.mark.parametrize("theme", THEMES)
    @pytest.mark.parametrize(
        "text", ["--ac-text", "--ac-text-secondary", "--ac-text-muted"]
    )
    def test_app_text_reads_on_the_tile(self, theme, text):
        tokens = _theme_tokens(theme)
        assert (
            _contrast(
                _resolve(tokens[text], tokens), _resolve(tokens["--id-tile"], tokens)
            )
            >= 4.5
        ), (theme, text)

    def test_the_tile_differs_between_themes_and_from_the_surface(self):
        light, dark = _theme_tokens("light"), _theme_tokens("dark")
        assert light["--id-tile"] != dark["--id-tile"]
        assert light["--id-edge"] != dark["--id-edge"]
        assert dark["--id-tile"] != dark["--ac-surface"]

    def test_the_decorative_border_is_not_the_one_that_defines_a_shape(self):
        """`--ac-border` ya medía 1,12:1 contra la tarjeta: por eso existe `--id-edge`."""
        tokens = _theme_tokens("dark")
        assert _contrast(tokens["--ac-border"], tokens["--ac-surface"]) < 3, (
            "si esto sube de 3:1, `--id-edge` dejó de hacer falta"
        )

    def test_the_skill_lists_the_new_pairs_and_contrast_py_passes_them(self):
        """Los pares nuevos viven en la skill (`diseno-ui`) y el script los mide en los dos temas."""
        module = CONTRAST
        pairs = ["id-edge:ac-bg", "id-edge:ac-surface", "id-edge:id-tile"]
        args = [str(ROOT / "static/css/app.css"), str(ROOT / "static/css/identity.css")]
        for pair in pairs:
            assert f"--pair {pair}" in (SKILL / "SKILL.md").read_text(encoding="utf-8")
        argv = [*args, "--min", "3"] + [x for p in pairs for x in ("--pair", p)]
        assert module.main(argv) == 0
        text_pairs = [
            x
            for p in ("ac-text:id-tile", "ac-text-secondary:id-tile")
            for x in ("--pair", p)
        ]
        assert module.main([*args, *text_pairs]) == 0


class TestLayerRulesOfTheWholeBatch:
    def test_the_layer_defines_only_id_tokens(self):
        defined = set(re.findall(r"(?m)^\s*(--[\w-]+)\s*:", IDENTITY))
        assert {"--id-edge", "--id-tile"} <= defined
        assert {n for n in defined if not n.startswith("--id-")} == set()

    def test_there_is_a_single_motion_block(self):
        assert IDENTITY.count("@media (prefers-reduced-motion: no-preference)") == 1

    def test_nothing_slides_sideways(self):
        assert "translateX" not in IDENTITY

    def test_the_e7_block_has_no_transition(self):
        e7 = IDENTITY[
            IDENTITY.index("/* E7: sección") : IDENTITY.index("/* == F: ilustración")
        ]
        assert "transition" not in e7

    def test_app_css_is_not_touched_by_the_new_tokens(self):
        assert "--id-edge" not in APP and "--id-tile" not in APP


class TestContentIconSprite:
    def test_the_sprite_has_the_symbols_the_batch_needs(self):
        assert set(_symbols()) == {
            "icon-satellite",
            "icon-moon",
            "icon-sunset",
            "icon-sunrise",
            "icon-clock",
            "icon-zone",
            "icon-check",
            "icon-info",
        }

    def test_no_symbol_carries_a_colour_of_its_own(self):
        source = SPRITE.read_text(encoding="utf-8")
        assert not re.search(r'(stroke|fill)="(?!none)', source)
        assert (
            "style=" in source.split("<symbol")[0]
        )  # sólo el `display:none` del contenedor
        assert "style=" not in source.split("<symbol", 1)[1]

    def test_every_symbol_draws_something_different_and_is_24px(self):
        drawings = {}
        for name, drawing in _symbols().items():
            drawings.setdefault(re.sub(r"\s+", "", drawing), []).append(name)
        assert all(len(v) == 1 for v in drawings.values()), drawings
        assert SPRITE.read_text(encoding="utf-8").count('viewBox="0 0 24 24"') == len(
            _symbols()
        )

    def test_the_comment_is_valid_xml(self):
        """Un `--` dentro de un comentario XML invalida el archivo y el `<use>` dibuja nada."""
        import xml.dom.minidom

        xml.dom.minidom.parse(str(SPRITE))

    def test_no_symbol_is_left_unused_except_the_pending_ones(self):
        used = set(re.findall(r"icons-ui\.svg' %\}#([a-z0-9-]+)", _templates()))
        orphan = set(_symbols()) - used - PENDING
        assert not orphan, sorted(orphan)

    def test_every_reference_points_at_a_symbol_that_exists(self):
        used = set(re.findall(r"icons-ui\.svg' %\}#([a-z0-9-]+)", _templates()))
        assert not used - set(_symbols()), sorted(used - set(_symbols()))

    def test_pending_only_names_symbols_that_exist(self):
        assert PENDING <= set(_symbols())
