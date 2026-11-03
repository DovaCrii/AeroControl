"""LV-397: imágenes de aviación — siluetas de equipos, ilustraciones propias y fotos libres.

Pedido del usuario (2026-11-03): mejorar lo visual con drones RPA, aviones y aviación, *«SVG
mezclado con imágenes de internet»*. Estos guardianes fijan lo que no puede degradarse:

- cada equipo de la flota (Matrice 4, Matrice 400, Dock, base GNSS/RTK) recibe **su** dibujo y
  no el de otro;
- las ilustraciones nuevas son livianas, sin código ni enlaces, y sólo se mueven con
  `prefers-reduced-motion: no-preference`;
- toda foto tiene su fila de licencia, pesa como máximo 150 KB, y ninguna plantilla ni CSS
  enlaza imágenes de otro dominio (el CSP las bloquearía y filtraría la IP de cada persona).
"""

import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.urls import reverse

from apps.core.templatetags.aero_tags import AIRCRAFT_ART_SERIES, aircraft_art

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "static"
TEMPLATES = ROOT / "templates"
ILLUSTRATIONS = STATIC / "img" / "illustrations"
PHOTOS = STATIC / "img" / "photos"
LICENSES = PHOTOS / "LICENSES.md"
IMAGERY_CSS = STATIC / "css" / "imagery.css"

NEW_EQUIPMENT = ("matrice-4", "matrice-400", "dock", "gnss-base")
NEW_ILLUSTRATIONS = (
    "fixed-wing-drone.svg",
    "light-aircraft.svg",
    "helicopter.svg",
    "control-tower.svg",
    "kmz-area.svg",
    "compliance-shield.svg",
)
PHOTO_EXTENSIONS = {".webp", ".jpg", ".jpeg", ".png", ".avif", ".gif"}
PHOTO_CEILING = 153_600  # 150 KB


def _aircraft(model):
    return SimpleNamespace(model=model)


def _block_end(text, start):
    depth = 0
    for index in range(text.index("{", start), len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return index
    raise AssertionError("unbalanced block")


class TestTheEquipmentDrawings:
    def test_every_new_equipment_has_its_drawing(self):
        for key in NEW_EQUIPMENT:
            assert key in AIRCRAFT_ART_SERIES, key
            assert (STATIC / "img" / "aircraft" / f"{key}.svg").exists(), key

    @pytest.mark.parametrize("key", NEW_EQUIPMENT)
    def test_no_drawing_carries_a_brand(self, key):
        """Dibujos de la forma, sin logo ni texto de marca: ni `<text>` ni el nombre del fabricante."""
        svg = (STATIC / "img" / "aircraft" / f"{key}.svg").read_text(encoding="utf-8")
        assert "<text" not in svg
        assert "dji" not in svg.lower()

    @pytest.mark.parametrize(
        ("model", "key"),
        [
            ("MATRICE 4 ENTERPRISE", "matrice-4"),
            ("Matrice 4E", "matrice-4"),
            ("Matrice 4T", "matrice-4"),
            ("Matrice 4TD", "matrice-4"),
            ("Matrice 400", "matrice-400"),
            ("MATRICE 400 RTK", "matrice-400"),
            ("M400", "matrice-400"),
            ("DJI Dock 2", "dock"),
            ("Dock 3", "dock"),
            ("D-RTK 2", "gnss-base"),
            ("D-RTK 3 Multifunctional Station", "gnss-base"),
            ("Base GNSS", "gnss-base"),
        ],
    )
    def test_each_equipment_gets_its_own_drawing(self, model, key):
        art = aircraft_art(_aircraft(model))

        assert art["series"] == key
        assert f"img/aircraft/{key}." in art["url"]

    @pytest.mark.parametrize(
        "model", ["MATRICE 300 RTK", "Matrice 350 RTK", "Matrice 30T", "M300 RTK"]
    )
    def test_the_older_matrice_keep_the_classic_drawing(self, model):
        """«300 RTK» lleva RTK y empieza por «Matrice»: no es una base GNSS ni un Matrice 4."""
        art = aircraft_art(_aircraft(model))

        assert art["series"] == "matrice"
        assert "img/aircraft/matrice." in art["url"]

    @pytest.mark.parametrize("model", ["M4", "M4E", "M4T", "Mavic 4 Pro"])
    def test_the_ambiguous_four_is_still_not_guessed(self, model):
        """«M4» puede ser Matrice 4 o Mavic 4: sólo el nombre entero elige el dibujo."""
        assert aircraft_art(_aircraft(model))["series"] in {"generic", "mavic"}
        assert aircraft_art(_aircraft(model))["series"] != "matrice-4"


class TestTheNewIllustrations:
    @pytest.mark.parametrize("name", NEW_ILLUSTRATIONS)
    def test_it_exists_and_is_light(self, name):
        path = ILLUSTRATIONS / name
        assert path.exists(), name
        assert path.stat().st_size <= 40_000, name

    @pytest.mark.parametrize("name", NEW_ILLUSTRATIONS)
    def test_it_only_moves_when_motion_is_welcome(self, name):
        """Toda animación vive dentro de `prefers-reduced-motion: no-preference`."""
        svg = (ILLUSTRATIONS / name).read_text(encoding="utf-8")
        compact = svg.replace(" ", "")
        marker = "@media(prefers-reduced-motion:no-preference){"
        if "animation" not in compact:
            return
        start = compact.index(marker)
        end = _block_end(compact, start)
        outside = compact[:start] + compact[end:]
        assert "animation" not in outside, name
        assert "@keyframes" not in outside, name

    @pytest.mark.parametrize("name", NEW_ILLUSTRATIONS)
    def test_it_draws_with_the_shared_stroke(self, name):
        """El trazo usa `currentColor`, como las demás: la lámina decide el color de la línea."""
        assert 'stroke="currentColor"' in (ILLUSTRATIONS / name).read_text(
            encoding="utf-8"
        )

    def test_the_readme_lists_them_as_own_work(self):
        readme = (ILLUSTRATIONS / "README.md").read_text(encoding="utf-8")
        for name in NEW_ILLUSTRATIONS:
            assert f"`{name}`" in readme, name
        assert "2026-11-03" in readme

    def test_two_empty_states_already_use_them(self):
        flights = (TEMPLATES / "operations" / "_flight_request_rows.html").read_text(
            encoding="utf-8"
        )
        findings = (TEMPLATES / "compliance" / "_nonconformity_rows.html").read_text(
            encoding="utf-8"
        )
        assert "img/illustrations/kmz-area.svg" in flights
        assert "img/illustrations/compliance-shield.svg" in findings


class TestThePhotos:
    def _photos(self):
        return sorted(
            p for p in PHOTOS.iterdir() if p.suffix.lower() in PHOTO_EXTENSIONS
        )

    def test_there_are_photos(self):
        assert len(self._photos()) >= 2

    def test_every_photo_has_its_licence_row(self):
        licences = LICENSES.read_text(encoding="utf-8")
        rows = [line for line in licences.splitlines() if line.startswith("| `")]
        for photo in self._photos():
            row = next((r for r in rows if r.startswith(f"| `{photo.name}`")), None)
            assert row is not None, photo.name
            # Archivo, título, origen, autor, licencia, fecha y cambios: siete columnas llenas.
            cells = [c.strip() for c in row.strip().strip("|").split("|")]
            assert len(cells) == 7 and all(cells), photo.name
            assert cells[2].startswith("https://"), photo.name
            assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", cells[5]), photo.name

    def test_every_licence_row_has_its_photo(self):
        """Una fila sin archivo es un registro que miente: se borra junto con la foto."""
        licences = LICENSES.read_text(encoding="utf-8")
        listed = re.findall(r"^\| `([^`]+)`", licences, re.MULTILINE)
        assert listed
        for name in listed:
            assert (PHOTOS / name).exists(), name

    @pytest.mark.parametrize(
        "path",
        sorted(
            p
            for p in (STATIC / "img" / "photos").iterdir()
            if p.suffix.lower() in PHOTO_EXTENSIONS
        ),
        ids=lambda p: p.name,
    )
    def test_no_photo_is_heavy(self, path):
        assert path.stat().st_size <= PHOTO_CEILING, path.name


class TestNoImageComesFromAnotherSite:
    REMOTE_IMG = re.compile(r"<img[^>]+src\s*=\s*[\"']?\s*(https?:)?//", re.IGNORECASE)
    REMOTE_URL = re.compile(r"url\(\s*[\"']?\s*(https?:)?//", re.IGNORECASE)

    def test_no_template_links_a_remote_image(self):
        offenders = [
            p.relative_to(ROOT).as_posix()
            for p in TEMPLATES.rglob("*.html")
            if self.REMOTE_IMG.search(p.read_text(encoding="utf-8"))
            or self.REMOTE_URL.search(p.read_text(encoding="utf-8"))
        ]
        assert offenders == []

    def test_no_stylesheet_links_a_remote_image(self):
        offenders = [
            p.relative_to(ROOT).as_posix()
            for p in (STATIC / "css").rglob("*.css")
            if self.REMOTE_URL.search(p.read_text(encoding="utf-8"))
        ]
        assert offenders == []


class TestTheImageryStylesheet:
    def test_it_stays_under_its_own_ceiling(self):
        assert len(IMAGERY_CSS.read_bytes()) < 16 * 1024

    def test_it_only_adds(self):
        css = IMAGERY_CSS.read_text(encoding="utf-8")
        assert not re.search(r"--(ac|sev)-[a-z-]+\s*:", css)
        assert "@import" not in css

    def test_every_image_it_uses_exists(self):
        css = IMAGERY_CSS.read_text(encoding="utf-8")
        urls = re.findall(r"url\(\s*[\"']?([^\"')]+)", css)
        assert urls
        for url in urls:
            assert (IMAGERY_CSS.parent / url).resolve().exists(), url


class TestTheLoginShowsThePhoto:
    def test_the_login_loads_the_imagery_after_identity(self, client):
        html = client.get(reverse("login")).content.decode()

        assert html.index("css/imagery.css") > html.index("css/identity.css")

    def test_the_photo_lives_only_on_wide_screens(self):
        """En un teléfono el panel no existe: la regla de la foto va dentro del `min-width`."""
        css = IMAGERY_CSS.read_text(encoding="utf-8")
        start = css.index("@media (min-width: 992px) {")
        inside = css[start : _block_end(css, start)]
        outside = css[:start] + css[_block_end(css, start) :]

        assert "img/photos/atacama-andes.webp" in inside
        assert "img/photos/" not in outside
