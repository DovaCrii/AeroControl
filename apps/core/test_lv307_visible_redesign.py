"""LV-307: el rediseño visible (portada, indicadores del panel y tipografía).

Pedido del usuario (2026-10-13, con capturas): «el cambio visual no se nota, es lo mismo». Estos
guardianes fijan lo que **no** puede degradarse: que la fuente propia exista con su licencia, que el
panel de marca de la portada sea sólo decorativo (el formulario sigue siendo lo único operable) y
que cada indicador lleve su barra con la meta que le corresponde.
"""

import re
from pathlib import Path

import pytest
from django.urls import reverse

ROOT = Path(__file__).resolve().parents[2]
CSS = ROOT / "static" / "css" / "identity.css"
FONTS = ROOT / "static" / "fonts"


class TestTheFont:
    def test_the_font_and_its_licence_are_shipped_together(self):
        assert (FONTS / "Archivo.woff2").stat().st_size > 100_000
        licence = (FONTS / "OFL-Archivo.txt").read_text(encoding="utf-8")
        assert "SIL OPEN FONT LICENSE" in licence.upper()

    def test_the_font_face_points_at_a_file_that_exists(self):
        css = CSS.read_text(encoding="utf-8")
        match = re.search(r'@font-face\s*\{[^}]*url\("([^"]+)"\)', css)

        assert match, "falta el @font-face"
        assert (CSS.parent / match.group(1)).resolve().exists()

    def test_it_is_served_from_this_server_never_from_a_cdn(self):
        css = CSS.read_text(encoding="utf-8")

        assert "fonts.googleapis" not in css
        assert not re.search(r"url\(\s*[\"']?https?:", css)

    def test_a_missing_file_still_falls_back_to_the_system_font(self):
        css = CSS.read_text(encoding="utf-8")

        assert "font-display: swap" in css
        assert re.search(r"--id-display:\s*\"Archivo\",\s*system-ui", css)


@pytest.mark.django_db
class TestTheLoginShowcase:
    def _html(self, client):
        return client.get(reverse("login")).content.decode()

    def test_the_brand_panel_is_decorative_only(self, client):
        html = self._html(client)
        aside = html.split('<aside class="login-showcase"')[1].split("</aside>")[0]

        assert (
            'aria-hidden="true"' in html.split('<aside class="login-showcase"')[1][:60]
        )
        for operable in ("<a ", "<input", "<button", "<form", "<select", "<textarea"):
            assert operable not in aside, operable

    def test_the_form_still_exists_outside_the_panel(self, client):
        html = self._html(client)
        after_panel = html.split("</aside>")[1]

        assert 'name="username"' in after_panel
        assert 'name="password"' in after_panel
        assert "login-main" in after_panel

    def test_the_old_floating_sticker_is_gone(self, client):
        assert "login-art" not in self._html(client)

    def test_the_motion_of_the_drone_respects_reduced_motion(self):
        """El dron vuela y sus hélices giran: toda `animation` va dentro de `no-preference`."""
        css = CSS.read_text(encoding="utf-8")
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
        inside = css[start:end]
        outside = css[:start] + css[end:]

        assert "ac-fly" in inside and "ac-spin" in inside
        assert not re.search(r"\banimation(-[a-z]+)?\s*:", outside)


@pytest.mark.django_db
class TestTheDashboardIndicators:
    @pytest.fixture
    def page(self, admin_client):
        from apps.registry.models import Aircraft, CostCenter

        centre = CostCenter.objects.create(
            code="CC1", name="Uno", operates_flights=True
        )
        Aircraft.objects.create(
            registration="RPA-1",
            type="RPA",
            model="Mavic 3",
            manufacturer="DJI",
            cost_center=centre,
        )
        return admin_client.get(reverse("dashboard")).content.decode()

    def test_each_indicator_has_its_icon_and_its_bar(self, page):
        for key in ("fleet", "insurance", "credentials", "permits"):
            assert f"kpi-{key}" in page, key
        assert page.count("kpi-ico") >= 4
        # Una barra por cada indicador que tiene porcentaje: sin registros no hay porcentaje, y
        # dibujar una barra vacía afirmaría un 0 % que nadie midió.
        assert page.count("<meter") == page.count('class="readiness-pct')
        assert page.count("<meter") >= 1

    def test_the_fleet_bar_carries_the_target_the_card_declares(self, page):
        meter = re.search(r'<meter class="kpi-meter"[^>]*>', page).group(0)

        assert 'high="90"' in meter  # «meta 90 %» de la tarjeta de flota
        assert 'low="1"' in meter
        assert 'optimum="100"' in meter

    def test_the_bar_is_decorative_so_the_number_is_not_read_twice(self, page):
        assert re.search(r'<meter class="kpi-meter"[^>]*aria-hidden="true"', page)

    def test_the_bar_needs_no_inline_style(self, page):
        meters = re.findall(r'<meter class="kpi-meter"[^>]*>', page)

        assert meters and not any("style=" in meter for meter in meters)
