"""LV-333: legibilidad, contraste y señales (ola K).

Los contrastes se CALCULAN con las mismas funciones que `test_lv312_hero`, no se leen del navegador.
Cubre: el gris secundario en claro (>= 7:1 sobre las tres superficies), `--bs-secondary-color` (que
arrastra `.text-body-secondary`), cada par texto/fondo de `.id-*` y `.id-chip` en ambos temas, y que
E5 (y lo nuevo de la sección C) no redefine `--ac-*` ni `--sev-*`.
"""

import re
from pathlib import Path

import pytest

from apps.dashboard.test_lv312_hero import _contrast as _ratio, _luminance

ROOT = Path(__file__).resolve().parents[2]
APP = (ROOT / "static" / "css" / "app.css").read_text(encoding="utf-8")
IDENTITY = (ROOT / "static" / "css" / "identity.css").read_text(encoding="utf-8")

DARK_SELECTOR = (
    r'(?m)^\[data-theme="dark"\](?:,\s*\[data-bs-theme="dark"\])?\s*\{([^}]*)\}'
)
SURFACES = ("--ac-bg", "--ac-surface", "--ac-surface-raised")


def _contrast(a, b):
    return _ratio(_luminance(a), _luminance(b))


def _decls(block):
    return {k: v.strip() for k, v in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", block)}


def _tokens(theme):
    out = {}
    for css in (APP, IDENTITY):
        for block in re.findall(r"(?m)^:root\s*\{([^}]*)\}", css):
            out.update(_decls(block))
    if theme == "dark":
        for css in (APP, IDENTITY):
            for block in re.findall(DARK_SELECTOR, css):
                out.update(_decls(block))
    return out


def _resolve(value, tokens):
    match = re.fullmatch(r"var\((--[\w-]+)\)", value.strip())
    return _resolve(tokens[match.group(1)], tokens) if match else value.strip()


def _pair(selector):
    """(texto, fondo) literales de la regla `selector { … }` de identity.css, en el tema dado."""
    match = re.search(rf"(?m)^{re.escape(selector)}\s*\{{([^}}]*)\}}", IDENTITY)
    assert match, selector
    body = match.group(1)
    return (
        re.search(r"(?<![\w-])color:\s*([^;]+);", body).group(1).strip(),
        re.search(r"background:\s*([^;]+);", body).group(1).strip(),
    )


class TestSecondaryGrey:
    @pytest.mark.parametrize("surface", SURFACES)
    @pytest.mark.parametrize("name", ["--ac-text-secondary", "--bs-secondary-color"])
    def test_light_reaches_7_to_1(self, name, surface):
        tokens = _tokens("light")
        assert (
            _contrast(_resolve(tokens[name], tokens), _resolve(tokens[surface], tokens))
            >= 7
        )

    def test_bootstrap_secondary_follows_the_token_in_both_themes(self):
        for theme in ("light", "dark"):
            assert _tokens(theme)["--bs-secondary-color"] == "var(--ac-text-secondary)"

    @pytest.mark.parametrize("surface", SURFACES)
    def test_dark_muted_reads_on_every_surface(self, surface):
        # Sobre `--sev-nominal-bg` (#37455c) da 3.97: no hay texto débil sobre ese relleno (las
        # insignias nominales llevan `--sev-nominal-text`), y subirlo a 4.5 lo igualaría al secundario.
        tokens = _tokens("dark")
        assert _contrast(tokens["--ac-text-muted"], tokens[surface]) >= 4.5


class TestSignalPairs:
    @pytest.mark.parametrize("theme", ["light", "dark"])
    @pytest.mark.parametrize(
        "selector",
        [
            ".id-note",
            ".id-warn",
            ".id-ok",
            ".id-danger",
            ".id-chip--warning",
            ".id-chip--neutral",
            ".id-chip--ok",
        ],
    )
    def test_text_reaches_4_5_on_its_background(self, theme, selector):
        tokens = _tokens(theme)
        text, bg = _pair(selector)
        assert _contrast(_resolve(text, tokens), _resolve(bg, tokens)) >= 4.5

    @pytest.mark.parametrize("theme", ["light", "dark"])
    @pytest.mark.parametrize("surface", SURFACES)
    def test_hint_reaches_4_5_on_every_surface(self, theme, surface):
        tokens = _tokens(theme)
        text, _ = (
            re.search(r"(?m)^\.id-hint\s*\{\s*color:\s*([^;]+);", IDENTITY).group(1),
            None,
        )
        assert (
            _contrast(_resolve(text, tokens), _resolve(tokens[surface], tokens)) >= 4.5
        )

    def test_hints_are_14px_and_never_italic(self):
        assert ".form-shell .form-text {" in IDENTITY
        block = IDENTITY.split(".form-shell .form-text {")[1].split("}")[0]
        assert "font-size: 0.875rem" in block and "font-style: normal" in block


class TestNothingIsRedefined:
    def _e5(self):
        start = IDENTITY.index("/* E5: señales")
        return IDENTITY[start : IDENTITY.index("/* == F:", start)]

    def test_e5_exists_after_e4(self):
        assert IDENTITY.index("/* E4:") < IDENTITY.index("/* E5: señales")

    def test_e5_defines_no_ac_or_sev_token(self):
        assert not re.search(r"--(ac|sev)-[\w-]+\s*:", self._e5())

    def test_identity_still_defines_only_id_tokens(self):
        defined = set(re.findall(r"(?m)^\s*(--[\w-]+)\s*:", IDENTITY))
        assert {n for n in defined if not n.startswith("--id-")} == set()

    def test_every_signal_class_is_declared(self):
        for kind in ("hint", "note", "warn", "ok", "danger"):
            assert f".id-{kind}" in self._e5()
