"""LV-109: the panel's two charts were never drawn.

`LV-89` replaced "Aircraft by status" and "Permissions by status" with the
three-indicator strip and removed their `<canvas>` from the template -- but
`dashboard.js` kept building them. Chart.js throws on a missing canvas, and the
throw took down **every chart declared after it**, so the two that were still on
the page ("Mantenciones por tipo", "Vuelos por mes") never appeared: two empty
boxes and two console errors on the app's home page, on every load, in
production. Found in the browser; no ordinary test could have seen it, because
the HTML was right all along -- the failure was in the script.

The guard a test *can* keep is the contract between the two files: **the set of
canvases the template declares and the set of charts the script builds are the
same set.** Checked against the template rather than a rendered page on purpose:
each canvas only renders when its series has data, so a rendered page proves
nothing about the ones that happened to be empty that day -- which is exactly
the blind spot this defect lived in.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DASHBOARD_JS = REPO / "static" / "js" / "dashboard.js"
DASHBOARD_HTML = REPO / "templates" / "dashboard" / "index.html"

# `build('<canvas id>', ...)` is the only way the script creates a chart.
BUILD_CALL = re.compile(r"build\(\s*'([^']+)'")
CANVAS_ID = re.compile(r'<canvas[^>]*id="([^"]+)"')


def _declared_canvases():
    return set(CANVAS_ID.findall(DASHBOARD_HTML.read_text(encoding="utf-8")))


def _built_charts():
    return set(BUILD_CALL.findall(DASHBOARD_JS.read_text(encoding="utf-8")))


def test_every_canvas_on_the_panel_has_a_chart():
    missing = _declared_canvases() - _built_charts()

    assert not missing, f"canvas in the template with no chart built for it: {missing}"


def test_every_chart_the_script_builds_has_a_canvas():
    """The half that actually bit: a chart built for a canvas that was removed."""
    orphaned = _built_charts() - _declared_canvases()

    assert not orphaned, f"chart built for a canvas that is not there: {orphaned}"


def test_no_chart_is_constructed_outside_the_guard():
    """`new Chart(...)` anywhere else would skip the missing-canvas check and
    bring back the failure where one bad chart takes down the rest."""
    constructions = re.findall(r"new Chart\(", DASHBOARD_JS.read_text(encoding="utf-8"))

    assert len(constructions) == 1, (
        "every chart must go through build(), which skips a missing canvas"
    )
