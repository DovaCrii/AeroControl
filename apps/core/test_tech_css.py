"""LV-446: guardián de la capa técnica (`static/css/tech.css`, `static/css/sheet.css`).

Pesos en bytes LF (como el CI), sólo `--id-*`, sin redefinir `--ac-`/`--sev-`, sin recursos externos,
animación sólo bajo `prefers-reduced-motion: no-preference` y orden de carga tras `identity.css`.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TECH = ROOT / "static" / "css" / "tech.css"
SHEET = ROOT / "static" / "css" / "sheet.css"
BASE = ROOT / "templates" / "base.html"
LOGIN = ROOT / "templates" / "registration" / "login.html"


def _lf(path):
    return path.read_bytes().replace(b"\r\n", b"\n")


def _css(path):
    return _lf(path).decode("utf-8")


def test_the_sheets_stay_under_their_ceilings_in_lf_bytes():
    assert len(_lf(TECH)) < 8 * 1024
    assert len(_lf(SHEET)) < 12 * 1024


def test_the_sheets_define_only_id_tokens():
    for path in (TECH, SHEET):
        defined = set(re.findall(r"(?m)^\s*(--[\w-]+)\s*:", _css(path)))
        assert {n for n in defined if not n.startswith("--id-")} == set(), path.name
    assert "--id-tk-plate" in _css(TECH)


def test_the_layer_does_not_redefine_the_app_or_state_colours():
    for path in (TECH, SHEET):
        css = _css(path)
        assert not re.search(r"(?m)^\s*--(ac|sev)-[\w-]+\s*:", css), path.name


def test_no_external_resources():
    for path in (TECH, SHEET):
        css = _css(path)
        assert "url(http" not in css and "@import" not in css, path.name


def test_motion_only_under_no_preference():
    for path in (TECH, SHEET):
        css = _css(path)
        if re.search(r"\banimation(-[a-z]+)?\s*:|@keyframes", css):
            assert "prefers-reduced-motion: no-preference" in css, path.name


def _links(path):
    return re.findall(r"css/([\w-]+\.css)", path.read_text(encoding="utf-8"))


def test_the_layer_loads_after_identity_css():
    base = _links(BASE)
    assert base.index("tech.css") > base.index("identity.css")
    assert base.index("sheet.css") > base.index("identity.css")
    login = _links(LOGIN)
    assert login.index("tech.css") > login.index("identity.css")


def test_the_mono_font_is_served_locally_and_licensed():
    css = _css(TECH)
    font = ROOT / "static" / "fonts" / "JetBrainsMono-Latin.woff2"
    assert font.stat().st_size <= 40 * 1024
    assert (ROOT / "static" / "fonts" / "OFL-JetBrainsMono.txt").is_file()
    face = re.search(r"@font-face\s*\{[^}]*JetBrains Mono[^}]*\}", css).group(0)
    assert "font-display: swap" in face
    assert 'url("../fonts/JetBrainsMono-Latin.woff2")' in face
    assert "http" not in face
    assert re.search(r'--id-mono:\s*"JetBrains Mono",', css)
