"""LV-324 (ola F, F2): cabecera por módulo y fondos.

Garantías:

1. **Cada módulo de la barra tiene su máscara** y es sólo decoración (<= 6 KB, sin scripts ni
   recursos externos).
2. **Nada permanente**: la entrada es de una sola vez y F2 no define ninguna animación repetida.
3. **El tema manda**: F2 no redefine ningún token `--ac-*`/`--sev-*`; el color sale de
   `--ac-text-secondary`.
4. **El título y el rótulo se leen** sobre la mezcla más desfavorable, en claro y oscuro.
   Decisión explícita de la ola H (LV-331): el dibujo pasó de 0,11/0,18 a 0,16/0,24 (claro/oscuro)
   porque se veía tenue y «descolgado»; el rango del guardián se recalculó con él (0,15-0,17 /
   0,22-0,26) y título y rótulo siguen exigiendo >= 4,5:1 con la mezcla más desfavorable.
5. El context processor `nav_module` mapea las seis secciones y las pantallas genéricas lo pintan.
6. La barra punteada bajo cada título ya no existe.
"""

import re
from pathlib import Path

import pytest
from django.test import RequestFactory
from django.urls import reverse

from apps.core.context_processors import (
    NAV_MODULE_STEMS,
    module_for_url_name,
    nav_module,
)
from apps.dashboard.test_lv312_hero import _contrast, _lum_rgb, _luminance, _tokens

ROOT = Path(__file__).resolve().parents[2]
IDENTITY = (ROOT / "static/css/identity.css").read_text(encoding="utf-8")
BASE = (ROOT / "templates/base.html").read_text(encoding="utf-8")
MODULES = ("flight", "compliance", "reports", "maintenance", "registry", "inventory")


def _f2_css():
    """Las dos regiones de F2: la estática y la de entradas dentro del bloque `no-preference`."""
    static = IDENTITY[
        IDENTITY.index("/* F2: cabecera por módulo") : IDENTITY.index(
            "/* ── Movimiento"
        )
    ]
    motion = IDENTITY[IDENTITY.index("/* F2: entradas") :]
    return static, motion


class TestEveryModuleHasItsMask:
    def test_the_modules_are_the_ones_of_the_sidebar(self):
        # `LV-381` F1: los grupos viven en el registro del menú, no en `base.html`.
        from apps.core.navigation import NAV_GROUPS

        groups = {group.key for group in NAV_GROUPS}
        assert set(MODULES) <= groups
        assert set(NAV_MODULE_STEMS) == set(MODULES)

    @pytest.mark.parametrize("module", MODULES)
    def test_the_mask_exists_is_light_and_is_only_a_drawing(self, module):
        path = ROOT / "static/img/modules" / f"{module}-bg.svg"
        raw = path.read_bytes()
        assert len(raw) <= 6 * 1024, module
        assert len(raw) <= 2560, (
            module
        )  # ola H: enriquecidas pero siguen siendo ligeras
        svg = raw.decode("utf-8")
        assert not re.search(
            r"<script|href=|<image|<foreignObject|url\(\s*['\"]?http|on\w+=", svg, re.I
        )
        assert f"modules/{module}-bg.svg" in IDENTITY

    @pytest.mark.parametrize("module", MODULES)
    def test_the_css_applies_it_to_its_module(self, module):
        assert re.search(
            rf'\.page-header--module\[data-module="{module}"\]::before\s*\{{[^}}]*'
            rf"mask-image: url\(\"\.\./img/modules/{module}-bg\.svg\"\)",
            IDENTITY,
        )


def _opacities():
    light = re.search(r":root \{ --id-module-bg-opacity: ([\d.]+); \}", IDENTITY)
    dark = re.search(
        r'\[data-theme="dark"\] \{ --id-module-bg-opacity: ([\d.]+); \}', IDENTITY
    )
    return float(light.group(1)), float(dark.group(1))


class TestNothingMovesForeverInF2:
    def test_the_entrance_is_a_single_300ms_fade(self):
        _, motion = _f2_css()
        assert "300ms" in motion
        assert "infinite" not in motion
        assert "infinite" not in _f2_css()[0]

    def test_f2_animations_live_inside_the_single_no_preference_block(self):
        assert IDENTITY.count("prefers-reduced-motion: no-preference") >= 1
        first_block = IDENTITY.index("@media (prefers-reduced-motion: no-preference)")
        assert IDENTITY.index("/* F2: entradas") > first_block
        static, _ = _f2_css()
        assert "animation" not in static and "@keyframes" not in static


class TestTheThemeStillRules:
    def test_f2_redefines_no_theme_token(self):
        for region in _f2_css():
            assert not re.search(r"--ac-[a-z-]+\s*:", region)
            assert not re.search(r"--sev-[a-z-]+\s*:", region)

    def test_the_drawing_is_painted_with_the_secondary_text_and_stays_faint(self):
        static, _ = _f2_css()
        rule = re.search(r"\.page-header--module::before\s*\{([^}]*)\}", static).group(
            1
        )
        assert "var(--ac-text-secondary)" in rule
        assert "opacity: var(--id-module-bg-opacity)" in rule
        assert re.search(r"min-height:\s*9[0-6]px", static)
        assert "mask-size: auto 100%" in rule
        # Anclado al título y cortado antes de las acciones (~270 px a la derecha).
        assert "mask-position: left" in rule
        assert re.search(r"inset:\s*0 2[6-9]\dpx 0 0", rule)
        # El dibujo no tapa botones ni enlaces de la cabecera.
        assert "pointer-events: none" in rule and "z-index: -1" in rule
        light, dark = _opacities()
        assert 0.15 <= light <= 0.17 and 0.22 <= dark <= 0.26


class TestTheTitleAndTagStayReadable:
    @pytest.mark.parametrize("theme", ["light", "dark"])
    def test_contrast_on_the_worst_case_mix(self, theme):
        tokens = _tokens(theme)
        sec, surface = tokens["text-secondary"], tokens["surface"]
        # Peor caso: el trazo cubre justo debajo del texto, a la opacidad de reposo del tema.
        share = _opacities()[0 if theme == "light" else 1]
        worst = tuple(
            round(
                int(sec[i : i + 2], 16) * share
                + int(surface[i : i + 2], 16) * (1 - share)
            )
            for i in (1, 3, 5)
        )
        for name in ("text", "text-secondary"):
            ratio = _contrast(_luminance(tokens[name]), _lum_rgb(worst))
            assert ratio >= 4.5, (theme, name, ratio)


class TestNavModule:
    def test_it_maps_the_six_sections(self):
        got = {
            module_for_url_name(name)
            for name in (
                "permission-list",
                "document-list",
                "compliance-report",
                "maintenance-list",
                "aircraft-list",
                "battery-list",
            )
        }
        assert got == set(MODULES)

    def test_forms_and_details_inherit_their_list_module(self):
        assert module_for_url_name("aircraft-update") == "registry"
        assert module_for_url_name("flight-request-update") == "flight"
        assert module_for_url_name("monthly-report-approve") == "reports"
        assert module_for_url_name("maintenance-detail") == "maintenance"

    def test_unknown_screens_have_no_module(self):
        assert module_for_url_name("dashboard") == ""
        assert module_for_url_name(None) == ""
        request = RequestFactory().get("/")
        assert nav_module(request) == {"nav_module": ""}


@pytest.mark.django_db
class TestGenericScreensCarryTheHeader:
    @pytest.mark.parametrize(
        ("url_name", "module"),
        [
            ("aircraft-list", "registry"),
            ("permission-list", "flight"),
            ("maintenance-list", "maintenance"),
            ("battery-list", "inventory"),
        ],
    )
    def test_the_list_header_has_its_module_and_tag(
        self, admin_client, url_name, module
    ):
        html = admin_client.get(reverse(url_name)).content.decode()
        assert f'class="page-header page-header--module" data-module="{module}"' in html
        assert 'class="module-tag mb-1"' in html

    def test_a_form_header_has_its_module_and_tag(self, admin_client):
        html = admin_client.get(reverse("aircraft-create")).content.decode()
        assert 'class="page-header page-header--module" data-module="registry"' in html
        assert 'class="module-tag mb-1"' in html

    def test_the_dashboard_has_no_module_header(self, admin_client):
        html = admin_client.get(reverse("dashboard")).content.decode()
        assert "page-header--module" not in html


def test_the_dotted_bar_under_titles_is_gone():
    assert "h1::after" not in IDENTITY
    assert (
        "repeating-linear-gradient(\n    90deg,\n    var(--ac-primary)" not in IDENTITY
    )
