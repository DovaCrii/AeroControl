"""UX foco-y-bordes: el borde de los campos y el anillo de foco llegan a 3:1 (WCAG 1.4.11).

Antes: `.form-control` pintaba su borde con `--ac-border` (1,29:1 en claro, 1,50:1 en oscuro
sobre la tarjeta) y el foco tenia cuatro estilos, uno de ellos el azul de Bootstrap
(`#0d6efd`) y otro el turquesa de marca, que sobre blanco da 2,17:1.

El contraste se **calcula** con la misma aritmetica de `contrast.py` (la del skill
`diseno-ui`), no se lee de un navegador.
"""

import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CSS_DIR = ROOT / "static" / "css"
APP = CSS_DIR / "app.css"
IDENTITY = CSS_DIR / "identity.css"
AIRSPACE = CSS_DIR / "airspace.css"
LOGIN = CSS_DIR / "login.css"

_spec = importlib.util.spec_from_file_location(
    "contrast_tool",
    ROOT / ".claude" / "skills" / "diseno-ui" / "scripts" / "contrast.py",
)
contrast_tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(contrast_tool)

THEMES = {"claro": "claro", "oscuro": "oscuro"}
# Superficies donde aparecen los campos y el foco.
SURFACES = ("ac-bg", "ac-surface", "ac-surface-raised", "id-tile")


def _tokens(theme):
    return contrast_tool.load([APP, IDENTITY])[theme]


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("token", ["ac-control-border", "ac-focus-ring"])
@pytest.mark.parametrize("surface", SURFACES)
def test_token_reaches_3_to_1_in_both_themes(theme, token, surface):
    ratio, why = contrast_tool.measure(_tokens(theme), token, surface)
    assert ratio is not None, why
    assert ratio >= 3, f"--{token} sobre --{surface} en {theme}: {ratio:.2f}:1"


@pytest.mark.parametrize("theme", THEMES)
def test_control_border_is_the_identity_edge(theme):
    tokens = _tokens(theme)
    assert tokens["ac-control-border"].lower() == tokens["id-edge"].lower()


def test_the_navbar_keeps_a_ring_that_reads_on_navy():
    """Sobre `--ac-navy` el anillo claro no llega a 3:1, asi que la barra lo redefine."""
    css = APP.read_text(encoding="utf-8")
    match = re.search(
        r"\.navbar-dark\.navy\s*\{\s*--ac-focus-ring:\s*(#[0-9a-fA-F]{6})", css
    )
    assert match, "la barra azul marino debe redefinir --ac-focus-ring"
    navy = _tokens("claro")["ac-navy"]
    ratio = contrast_tool.ratio(
        contrast_tool.to_rgb(match.group(1)), contrast_tool.to_rgb(navy)
    )
    assert ratio >= 3, f"anillo sobre la barra: {ratio:.2f}:1"


def _rules(path):
    css = re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.S)
    return re.findall(r"([^{}]+)\{([^{}]*)\}", css)


@pytest.mark.parametrize("path", [APP, IDENTITY, AIRSPACE, LOGIN], ids=lambda p: p.name)
def test_every_focus_rule_uses_the_one_ring(path):
    """Toda regla `:focus-visible` que dibuja un contorno lo hace con `--ac-focus-ring`."""
    offenders = []
    for selector, body in _rules(path):
        if ":focus-visible" not in selector:
            continue
        for outline in re.findall(r"outline(?:-color)?\s*:\s*([^;]+)", body):
            if outline.strip() in ("none", "0"):
                continue
            if "outline-offset" in outline:
                continue
            if "var(--ac-focus-ring)" not in outline:
                offenders.append((selector.strip(), outline.strip()))
    assert not offenders, offenders


@pytest.mark.parametrize("path", [APP, IDENTITY, AIRSPACE, LOGIN], ids=lambda p: p.name)
def test_bootstrap_blue_is_gone(path):
    assert "#0d6efd" not in path.read_text(encoding="utf-8").lower()


def test_form_control_uses_the_control_border_token():
    declarations = {}
    for selector, body in _rules(APP):
        names = [s.strip() for s in selector.split(",")]
        if ".form-control" in names and ".form-select" in names and "border:" in body:
            declarations["base"] = body
        if ".form-check-input" in names:
            declarations["check"] = body
        if '[data-theme="dark"] .form-control' in names:
            declarations["dark"] = body
    assert "var(--ac-control-border)" in declarations["base"]
    assert "var(--ac-control-border)" in declarations["check"]
    assert "var(--ac-control-border)" in declarations["dark"]
    assert "var(--ac-border)" not in declarations["base"]
    assert "var(--ac-border)" not in declarations["dark"]
