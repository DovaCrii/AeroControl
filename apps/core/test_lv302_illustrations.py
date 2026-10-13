"""LV-302: ilustraciones y capa visual (`identity.css`).

Pedido del usuario (2026-10-13): que la app deje de verse plana, más cercana a
AeroAcademy, con dibujos de drones y animaciones. Estos guardianes fijan lo que **no**
puede degradarse con el tiempo: que cada dibujo referenciado exista, que ninguno traiga
código ni enlaces externos, que todo movimiento respete «reducir movimiento» y que la
capa visual se cargue **después** de `app.css`.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ILLUSTRATIONS = ROOT / "static" / "img" / "illustrations"
IDENTITY_CSS = ROOT / "static" / "css" / "identity.css"
TEMPLATES = ROOT / "templates"

REFERENCE = re.compile(r"img/illustrations/([\w.-]+\.svg)")
FORBIDDEN = re.compile(
    r"<script|onload\s*=|onclick\s*=|href\s*=\s*[\"']https?:|<foreignObject|@import",
    re.IGNORECASE,
)


def _svgs():
    return sorted(ILLUSTRATIONS.glob("*.svg"))


def _referenced():
    found = {}
    for template in TEMPLATES.rglob("*.html"):
        for name in REFERENCE.findall(template.read_text(encoding="utf-8")):
            found.setdefault(name, []).append(template.relative_to(ROOT).as_posix())
    return found


class TestTheIllustrationFiles:
    def test_there_are_illustrations(self):
        assert len(_svgs()) >= 8

    @pytest.mark.parametrize("path", _svgs(), ids=lambda p: p.name)
    def test_no_svg_carries_code_or_external_links(self, path):
        assert not FORBIDDEN.search(path.read_text(encoding="utf-8")), path.name

    @pytest.mark.parametrize("path", _svgs(), ids=lambda p: p.name)
    def test_no_svg_is_heavy(self, path):
        """Se cargan en cada lista vacía: un dibujo de cientos de KB sería un costo oculto."""
        assert path.stat().st_size <= 40_000, path.name

    def test_every_referenced_illustration_exists(self):
        missing = {
            name: where
            for name, where in _referenced().items()
            if not (ILLUSTRATIONS / name).exists()
        }
        assert missing == {}

    def test_the_empty_states_use_real_illustrations(self):
        referenced = _referenced()
        assert "drone-scan.svg" in referenced
        assert "permit-clipboard.svg" in referenced
        assert "route-map.svg" in referenced


class TestTheVisualLayer:
    def test_it_loads_after_app_css(self):
        for name in ("base.html", "registration/login.html"):
            html = (TEMPLATES / name).read_text(encoding="utf-8")
            assert html.index("css/identity.css") > html.index("css/app.css"), name

    def test_every_animation_lives_inside_no_preference(self):
        """Toda `animation` declarada, dentro de `prefers-reduced-motion: no-preference`."""
        css = IDENTITY_CSS.read_text(encoding="utf-8")
        marker = "@media (prefers-reduced-motion: no-preference) {"
        start = css.index(marker)
        depth, end = 0, None
        for index in range(start + len(marker) - 1, len(css)):
            if css[index] == "{":
                depth += 1
            elif css[index] == "}":
                depth -= 1
                if depth == 0:
                    end = index
                    break
        assert end is not None
        outside = css[:start] + css[end:]
        assert not re.search(r"\banimation(-[a-z]+)?\s*:", outside)
        assert "@keyframes" not in outside

    def test_the_layer_does_not_redefine_the_state_colours(self):
        """Sólo suma relieve: no toca los tokens medidos de severidad ni del tema."""
        css = IDENTITY_CSS.read_text(encoding="utf-8")
        assert "--sev-" not in css
        assert not re.search(r"--ac-[a-z-]+\s*:", css)
        # Lo único que el tema oscuro puede definir aquí son las variables propias `--id-*`.
        for block in re.findall(r"\[data-theme[^\]]*\]\s*\{([^}]*)\}", css):
            assert set(re.findall(r"(--[\w-]+)\s*:", block)) <= {"--id-lift"}

    def test_the_global_layer_hooks_onto_shared_classes(self):
        """«Toda la app» se logra con las clases compartidas, no pantalla por pantalla."""
        css = IDENTITY_CSS.read_text(encoding="utf-8")
        for selector in (
            ".card",
            ".page-header h1::after",
            ".btn",
            ".sidebar a.active",
        ):
            assert selector in css, selector


class TestEveryListHasAnIllustratedEmptyState:
    """La lista que nazca mañana sin ilustración en su fila vacía hace fallar esto."""

    def test_every_rows_partial_with_an_empty_row_uses_the_shared_art(self):
        partials = [
            *TEMPLATES.rglob("_*rows*.html"),
            *TEMPLATES.rglob("*table_body*.html"),
        ]
        assert len(partials) >= 20
        lacking = [
            p.relative_to(TEMPLATES).as_posix()
            for p in partials
            if "{% empty %}" in p.read_text(encoding="utf-8")
            and "generic/_empty_art.html" not in p.read_text(encoding="utf-8")
        ]
        assert lacking == []

    def test_it_uses_no_external_resources(self):
        css = IDENTITY_CSS.read_text(encoding="utf-8")
        assert not re.search(r"url\(\s*[\"']?https?:", css)
        assert "@import" not in css
