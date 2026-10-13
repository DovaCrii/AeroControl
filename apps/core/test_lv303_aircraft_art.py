"""LV-303: ilustración de la aeronave según su serie, con foto opcional.

Pedido del usuario (2026-10-13): drones más detallados y, si se puede, fotos de equipos. Las
fotos de terceros no se descargan: hay un dibujo propio por serie y un lugar para fotos que la
persona aporte con derecho de uso.
"""

import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.contrib.staticfiles import finders
from django.contrib.staticfiles.storage import staticfiles_storage

from apps.core.templatetags.aero_tags import (
    AIRCRAFT_ART_SERIES,
    aircraft_art,
)

ROOT = Path(__file__).resolve().parents[2]
AIRCRAFT_DIR = ROOT / "static" / "img" / "aircraft"
FORBIDDEN = re.compile(
    r"<script|onload\s*=|onclick\s*=|href\s*=\s*[\"']https?:|<foreignObject|@import",
    re.IGNORECASE,
)


def _aircraft(model):
    return SimpleNamespace(model=model)


class TestThePerSeriesDrawings:
    def test_there_is_a_drawing_per_series_and_a_generic_one(self):
        for name in (*AIRCRAFT_ART_SERIES, "generic"):
            assert (AIRCRAFT_DIR / f"{name}.svg").exists(), name

    @pytest.mark.parametrize(
        "path", sorted(AIRCRAFT_DIR.glob("*.svg")), ids=lambda p: p.name
    )
    def test_a_drawing_has_no_code_or_external_links(self, path):
        assert not FORBIDDEN.search(path.read_text(encoding="utf-8")), path.name

    @pytest.mark.parametrize(
        "path", sorted(AIRCRAFT_DIR.glob("*.svg")), ids=lambda p: p.name
    )
    def test_every_animation_respects_reduced_motion(self, path):
        """Las hélices giran y las luces parpadean: todo se apaga con «reducir movimiento»."""
        svg = path.read_text(encoding="utf-8")
        assert "@keyframes" in svg
        assert "prefers-reduced-motion:reduce" in svg.replace(" ", ""), path.name

    @pytest.mark.parametrize(
        "path", sorted(AIRCRAFT_DIR.glob("*.svg")), ids=lambda p: p.name
    )
    def test_a_drawing_is_light(self, path):
        assert path.stat().st_size <= 12_000, path.name


class TestWhichDrawingAnAircraftGets:
    @pytest.mark.parametrize(
        ("model", "series"),
        [
            ("Mavic 3 Enterprise", "mavic"),
            ("MATRICE 300 RTK", "matrice"),
            ("Phantom 4 Pro", "phantom"),
            ("Elios 3", "elios"),
        ],
    )
    def test_each_series_gets_its_own_drawing(self, model, series):
        art = aircraft_art(_aircraft(model))

        assert art["series"] == series
        assert art["photo"] is False
        assert f"img/aircraft/{series}" in art["url"]

    @pytest.mark.parametrize(
        ("model", "series"),
        [
            ("M3", "mavic"),
            ("M3E", "mavic"),
            ("m3t", "mavic"),
            ("M2EA", "mavic"),
            ("M300 RTK", "matrice"),
            ("M30T", "matrice"),
            ("M350 RTK", "matrice"),
        ],
    )
    def test_the_manufacturers_abbreviations_are_recognised(self, model, series):
        """«M3» es Mavic 3 y «M300» es Matrice 300: no deben caer en el dibujo genérico."""
        assert aircraft_art(_aircraft(model))["series"] == series

    @pytest.mark.parametrize("model", ["M4", "M4E", "M4T", "M30X"])
    def test_an_ambiguous_abbreviation_is_not_guessed(self, model):
        """Hay un Matrice 4 y un Mavic 4: adivinar mostraría el dibujo equivocado."""
        assert aircraft_art(_aircraft(model))["series"] == "generic"

    @pytest.mark.parametrize("model", ["Autel EVO II", "", "M", "Parrot Anafi"])
    def test_an_unknown_series_gets_the_generic_one_never_another_series(self, model):
        art = aircraft_art(_aircraft(model))

        assert art["series"] == "generic"
        assert "img/aircraft/generic" in art["url"]


class TestAPhotoWinsWhenProvided:
    def test_a_photo_for_the_series_replaces_the_drawing(self, monkeypatch):
        monkeypatch.setattr(
            finders,
            "find",
            lambda path, *a, **k: "x" if path == "img/equipment/mavic.webp" else None,
        )

        art = aircraft_art(_aircraft("Mavic 3 Enterprise"))

        assert art["photo"] is True
        assert "img/equipment/mavic.webp" in art["url"]

    def test_a_photo_for_another_series_does_not_apply(self, monkeypatch):
        monkeypatch.setattr(
            finders,
            "find",
            lambda path, *a, **k: "x" if path == "img/equipment/matrice.webp" else None,
        )

        art = aircraft_art(_aircraft("Mavic 3 Enterprise"))

        assert art["photo"] is False

    def test_a_photo_without_collectstatic_falls_back_to_the_drawing(self, monkeypatch):
        """Con estáticos hasheados, una foto sin `collectstatic` no tiene URL: no rompe la ficha."""
        monkeypatch.setattr(
            finders,
            "find",
            lambda path, *a, **k: "x" if path.startswith("img/equipment/") else None,
        )
        real_url = staticfiles_storage.url

        def url(path):
            if path.startswith("img/equipment/"):
                raise ValueError("Missing staticfiles manifest entry")
            return real_url(path)

        monkeypatch.setattr(staticfiles_storage, "url", url)

        art = aircraft_art(_aircraft("Phantom 4"))

        assert art["photo"] is False
        assert "img/aircraft/phantom" in art["url"]


@pytest.mark.django_db
class TestTheDetailPageShowsIt:
    def test_the_aircraft_page_shows_the_drawing_of_its_series(self):
        from apps.core.testing import login_as
        from apps.registry.models import Aircraft, CostCenter

        centre = CostCenter.objects.create(code="CC1", name="Uno")
        aircraft = Aircraft.objects.create(
            registration="RPA-1",
            type="RPA",
            model="Matrice 300 RTK",
            manufacturer="DJI",
            cost_center=centre,
        )
        from django.urls import reverse

        html = (
            login_as("view_aircraft")
            .get(reverse("aircraft-detail", args=[aircraft.pk]))
            .content.decode()
        )

        assert "img/aircraft/matrice" in html
        # La aeronave se muestra a lo grande con sus datos clave, no como una miniatura.
        hero = html.split('class="fleet-hero"')[1].split("</dl>")[0]
        assert "Matrice 300 RTK" in hero
        assert "DJI" in hero
