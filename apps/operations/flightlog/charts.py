"""LV-427: gráficos de línea en SVG generado en el servidor (sin librerías ni JS).

Sólo entran números del log, así que el SVG no lleva texto libre; los rótulos de los ejes los
pone quien llama (ya traducidos) y se escapan.
"""

from __future__ import annotations

from django.utils.html import escape
from django.utils.safestring import mark_safe

W, H = 640, 190
LEFT, RIGHT, TOP, BOTTOM = 52, 12, 10, 34


def _clock(seconds: float) -> str:
    seconds = int(round(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def line_chart(series, y_label: str, x_label: str):
    """`series`: [(t_segundos, valor)]. Devuelve el `<svg>` (SafeString) o `None` sin datos."""
    if len(series) < 2:
        return None
    t0, t1 = series[0][0], series[-1][0]
    ys = [v for _, v in series]
    lo, hi = min(ys), max(ys)
    if hi == lo:
        hi = lo + 1
    span_t = (t1 - t0) or 1

    def px(t):
        return LEFT + (t - t0) / span_t * (W - LEFT - RIGHT)

    def py(v):
        return TOP + (hi - v) / (hi - lo) * (H - TOP - BOTTOM)

    path = " ".join(f"{px(t):.1f},{py(v):.1f}" for t, v in series)
    parts = [
        f'<svg class="fa-chart" viewBox="0 0 {W} {H}" role="img" '
        f'aria-label="{escape(y_label)}">',
        f'<line class="fa-axis" x1="{LEFT}" y1="{TOP}" x2="{LEFT}" y2="{H - BOTTOM}"/>',
        f'<line class="fa-axis" x1="{LEFT}" y1="{H - BOTTOM}" '
        f'x2="{W - RIGHT}" y2="{H - BOTTOM}"/>',
    ]
    for v in (lo, (lo + hi) / 2, hi):
        y = py(v)
        parts.append(
            f'<line class="fa-grid" x1="{LEFT}" y1="{y:.1f}" x2="{W - RIGHT}" y2="{y:.1f}"/>'
            f'<text class="fa-tick" x="{LEFT - 6}" y="{y + 4:.1f}" text-anchor="end">'
            f"{v:.0f}</text>"
        )
    for t in (t0, (t0 + t1) / 2, t1):
        parts.append(
            f'<text class="fa-tick" x="{px(t):.1f}" y="{H - BOTTOM + 14}" '
            f'text-anchor="middle">{_clock(t - t0)}</text>'
        )
    parts.append(
        f'<text class="fa-label" x="{(LEFT + W - RIGHT) / 2:.0f}" y="{H - 4}" '
        f'text-anchor="middle">{escape(x_label)}</text>'
    )
    parts.append(
        f'<text class="fa-label" x="12" y="{(TOP + H - BOTTOM) / 2:.0f}" text-anchor="middle" '
        f'transform="rotate(-90 12 {(TOP + H - BOTTOM) / 2:.0f})">{escape(y_label)}</text>'
    )
    parts.append(f'<polyline class="fa-line" points="{path}"/></svg>')
    # Sólo números formateados con `:.1f`/`:.0f` (fallan si no son números) y rótulos escapados.
    return mark_safe("".join(parts))  # noqa: S308  # nosec B308 B703
