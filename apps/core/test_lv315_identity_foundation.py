"""LV-315: base de la identidad (`identity.css`), ola 0 del rediseño.

Fija lo que las olas siguientes no pueden romper: los tokens `--id-*`, las cinco secciones con
marca (en orden, para que ramas distintas editen zonas distintas), el chip de estado
compartido con su contraste calculado (no leído de un navegador) y las reglas de la capa.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
IDENTITY = (ROOT / "static" / "css" / "identity.css").read_text(encoding="utf-8")
APP = (ROOT / "static" / "css" / "app.css").read_text(encoding="utf-8")

TOKENS = {
    "--id-fs-sm": "0.8125rem",
    "--id-fs-md": "1rem",
    "--id-fs-lg": "1.25rem",
    "--id-fs-xl": "1.5625rem",
    "--id-fs-2xl": "1.9375rem",
    "--id-sp-1": "0.5rem",
    "--id-sp-2": "1rem",
    "--id-sp-3": "1.5rem",
    "--id-sp-4": "2.5rem",
    "--id-r-control": "8px",
    "--id-r-card": "12px",
    "--id-r-modal": "20px",
    "--id-r-pill": "999px",
    "--id-ease": "cubic-bezier(0.2, 0.7, 0.2, 1)",
    "--id-t-fast": "120ms",
    "--id-t-base": "180ms",
}

SECTIONS = [
    "/* == A: listas, tablas y filtros == */",
    "/* == B: fichas de detalle == */",
    "/* == C: formularios == */",
    "/* == D: informes, documentos y SIGO == */",
    "/* == E: pulido global == */",
]

VARIANTS = ["critical", "warning", "ok", "info", "neutral"]


def _declarations(css, selector_re):
    """Declaraciones del primer bloque cuyo selector es exactamente `selector_re`."""
    match = re.search(rf"(?m)^{selector_re}\s*\{{([^}}]*)\}}", css)
    assert match, selector_re
    return dict(re.findall(r"(--[\w-]+|[\w-]+)\s*:\s*([^;]+);", match.group(1)))


def _tokens(css, selector_re):
    return {
        k: v.strip()
        for k, v in _declarations(css, selector_re).items()
        if k.startswith("--")
    }


def _theme_tokens(theme):
    """Tokens `--sev-*` / `--id-*` efectivos: `app.css` y luego `identity.css`."""
    light = {}
    for css in (APP, IDENTITY):
        for block in re.findall(r"(?m)^:root\s*\{([^}]*)\}", css):
            light.update(
                {
                    k: v.strip()
                    for k, v in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", block)
                }
            )
    if theme == "light":
        return light
    dark = dict(light)
    for css in (APP, IDENTITY):
        for block in re.findall(r'(?m)^\[data-theme="dark"\]\s*\{([^}]*)\}', css):
            dark.update(
                {
                    k: v.strip()
                    for k, v in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", block)
                }
            )
    return dark


def _luminance(hex_color):
    hex_color = hex_color.lstrip("#")
    channels = [int(hex_color[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [
        c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels
    ]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(a, b):
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _resolve(value, tokens):
    match = re.fullmatch(r"var\((--[\w-]+)\)", value.strip())
    return _resolve(tokens[match.group(1)], tokens) if match else value.strip()


class TestTokens:
    @pytest.mark.parametrize("name,value", TOKENS.items())
    def test_token_is_declared_in_root(self, name, value):
        assert _tokens(IDENTITY, r":root")  # el primer :root existe
        found = {}
        for block in re.findall(r"(?m)^:root\s*\{([^}]*)\}", IDENTITY):
            found.update(dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", block)))
        assert found[name].strip() == value

    def test_lift_2_exists_in_both_themes(self):
        assert "--id-lift-2" in _theme_tokens("light")
        dark = re.search(
            r'(?m)^\[data-theme="dark"\]\s*\{([^}]*--id-lift-2[^}]*)\}', IDENTITY
        )
        assert dark
        assert (
            _theme_tokens("dark")["--id-lift-2"]
            != _theme_tokens("light")["--id-lift-2"]
        )

    def test_every_custom_property_defined_is_id_prefixed(self):
        """La capa sólo define `--id-*`; `--ac-*` y `--sev-*` son de `app.css`."""
        defined = set(re.findall(r"(?m)^\s*(--[\w-]+)\s*:", IDENTITY))
        assert defined
        assert {n for n in defined if not n.startswith("--id-")} == set()


class TestSections:
    def test_the_five_marks_exist_once_and_in_order(self):
        positions = [IDENTITY.index(mark) for mark in SECTIONS]
        assert positions == sorted(positions)
        for mark in SECTIONS:
            assert IDENTITY.count(mark) == 1

    def test_each_mark_is_followed_by_a_description_comment(self):
        for mark in SECTIONS:
            after = IDENTITY[IDENTITY.index(mark) + len(mark) :].lstrip("\r\n")
            assert after.startswith("/* Contiene:"), mark

    def test_each_mark_is_separated_by_a_blank_line(self):
        for mark in SECTIONS[1:]:
            before = IDENTITY[: IDENTITY.index(mark)]
            assert re.search(r"\n\s*\n$", before), mark


class TestChip:
    def test_base_and_variants_exist(self):
        assert re.search(r"(?m)^\.id-chip\s*\{", IDENTITY)
        for variant in VARIANTS:
            assert re.search(rf"(?m)^\.id-chip--{variant}\s*\{{", IDENTITY), variant

    def test_base_is_a_pill_in_small_caps_mono(self):
        decl = _declarations(IDENTITY, r"\.id-chip")
        assert "var(--id-r-pill)" in decl["border-radius"]
        assert "monospace" in decl["font-family"]
        assert "small-caps" in decl["font-variant-caps"]

    @pytest.mark.parametrize("theme", ["light", "dark"])
    @pytest.mark.parametrize("variant", VARIANTS)
    def test_text_reaches_4_5_to_1_on_its_background(self, theme, variant):
        tokens = _theme_tokens(theme)
        decl = _declarations(IDENTITY, rf"\.id-chip--{variant}")
        fg = _resolve(decl["color"], tokens)
        bg = _resolve(decl["background"], tokens)
        assert _contrast(fg, bg) >= 4.5, (variant, theme, fg, bg)

    def test_the_base_chip_also_reaches_4_5(self):
        for theme in ("light", "dark"):
            tokens = _theme_tokens(theme)
            decl = _declarations(IDENTITY, r"\.id-chip")
            assert (
                _contrast(
                    _resolve(decl["color"], tokens),
                    _resolve(decl["background"], tokens),
                )
                >= 4.5
            )

    def test_variants_read_existing_sev_tokens(self):
        for name in re.findall(r"var\((--sev-[\w-]+)\)", IDENTITY):
            assert f"{name}:" in APP, name


class TestLayerRules:
    def test_no_external_urls(self):
        assert not re.search(r"url\(\s*[\"']?https?:", IDENTITY)

    def test_animations_only_under_no_preference(self):
        marker = "@media (prefers-reduced-motion: no-preference) {"
        start = IDENTITY.index(marker)
        depth, end = 0, None
        for index in range(start + len(marker) - 1, len(IDENTITY)):
            if IDENTITY[index] == "{":
                depth += 1
            elif IDENTITY[index] == "}":
                depth -= 1
                if depth == 0:
                    end = index
                    break
        outside = IDENTITY[:start] + IDENTITY[end:]
        assert not re.search(r"\banimation(-[a-z]+)?\s*:", outside)
        assert "@keyframes" not in outside
