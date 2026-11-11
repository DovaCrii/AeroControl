"""LV-430: la línea de tiempo del vuelo en SVG generado en el servidor (sin librerías ni JS).

Las fases se **infieren** de la altura y del tramo de regreso automático que ya trae el análisis:

* despegue: hasta que la altura sobre el punto de partida supera `CLIMB_M` (o la mitad del máximo,
  si el vuelo nunca llegó tan alto);
* regreso automático: el tramo `return_leg` del log (y todo lo que sigue es aterrizaje);
* aterrizaje: desde el último punto sobre esa misma altura hasta el final;
* trabajo: el resto.

Si el log no trae altura no hay despegue ni aterrizaje, y el vuelo es todo «trabajo». Sólo entran
números del log y rótulos ya traducidos que se escapan.
"""

from __future__ import annotations

from django.utils.html import escape
from django.utils.safestring import mark_safe

from .types import FlightTrack

CLIMB_M = 10.0
W, H = 640, 92
LEFT, RIGHT = 8, 8
BAR_TOP, BAR_H = 36, 24
FLAG_H = 6
PHASES = ("takeoff", "work", "return", "landing")


def _clock(seconds: float) -> str:
    seconds = int(round(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def _climb_limits(track: FlightTrack):
    heights = [(p.t, p.height_m) for p in track.points if p.height_m is not None]
    peak = max((h for _t, h in heights), default=0)
    if peak <= 0:
        return None, None
    threshold = min(CLIMB_M, peak / 2)
    above = [t for t, h in heights if h > threshold]
    if not above:
        return None, None
    return above[0], above[-1]


def phase_segments(track: FlightTrack) -> list[tuple[str, float, float]]:
    """`[(fase, t_inicio, t_fin)]` contiguas y sin tramos vacíos."""
    if len(track.points) < 2:
        return []
    t0, t1 = track.points[0].t, track.points[-1].t
    climbed, landing_from = _climb_limits(track)
    leg = track.return_leg
    cuts = {t0, t1}
    for value in (climbed, landing_from, *(leg or ())):
        if value is not None and t0 < value < t1:
            cuts.add(value)
    edges = sorted(cuts)
    segments: list[tuple[str, float, float]] = []
    for start, end in zip(edges, edges[1:]):
        mid = (start + end) / 2
        if climbed is not None and mid < climbed:
            phase = "takeoff"
        elif leg and leg[0] <= mid <= leg[1]:
            phase = "return"
        elif (leg and mid > leg[1]) or (
            landing_from is not None and mid >= landing_from
        ):
            phase = "landing"
        else:
            phase = "work"
        if segments and segments[-1][0] == phase:
            segments[-1] = (phase, segments[-1][1], end)
        else:
            segments.append((phase, start, end))
    return segments


def warning_marks(track: FlightTrack):
    """Los avisos `warning` y `critical`: `[(t, nivel, texto)]`."""
    return [
        (e.t, e.level, e.raw_text)
        for e in track.events
        if e.level in ("warning", "critical")
    ]


def timeline_svg(track: FlightTrack, labels: dict, mark_text, flags=None):
    """El `<svg>` (SafeString) o `None` sin tramo medible.

    `labels`: nombre traducido de cada fase y `time`; `mark_text(t, nivel, texto)` da el texto
    que acompaña a cada marca (ya traducido). LV-432: `flags` = `[(inicio, fin, 'area'|'height')]`
    marca con una banda roja los tramos fuera del área (borde inferior de la barra) o sobre la
    altura autorizada (borde superior); `labels` puede traer `area` y `height` como título.
    """
    segments = phase_segments(track)
    if not segments:
        return None
    t0, t1 = track.points[0].t, track.points[-1].t
    span = (t1 - t0) or 1
    width = W - LEFT - RIGHT

    def px(t):
        return LEFT + (t - t0) / span * width

    parts = [
        f'<svg class="fr-timeline" viewBox="0 0 {W} {H}" role="img" '
        f'aria-label="{escape(labels["title"])}">'
    ]
    for phase, start, end in segments:
        x, w = px(start), px(end) - px(start)
        parts.append(
            f'<rect class="fr-ph fr-ph-{phase}" data-phase="{phase}" x="{x:.1f}" '
            f'y="{BAR_TOP}" width="{w:.1f}" height="{BAR_H}"/>'
        )
        if w >= 70:
            parts.append(
                f'<text class="fr-ph-label fr-pl-{phase}" x="{x + w / 2:.1f}" '
                f'y="{BAR_TOP + BAR_H / 2 + 4}" text-anchor="middle">'
                f"{escape(labels[phase])}</text>"
            )
    for start, end, kind in flags or ():
        x = px(start)
        w = max(px(end) - x, 3.0)
        y = BAR_TOP + BAR_H - FLAG_H if kind == "area" else BAR_TOP
        parts.append(
            f'<rect class="fr-flag fr-flag-{kind}" data-flag="{kind}" x="{x:.1f}" '
            f'y="{y}" width="{w:.1f}" height="{FLAG_H}"><title>'
            f"{escape(labels.get(kind, kind))} {_clock(start - t0)}-{_clock(end - t0)}"
            "</title></rect>"
        )
    for t, level, text in warning_marks(track):
        x = px(t)
        parts.append(
            f'<g class="fr-mk fr-mk-{level}" data-level="{level}">'
            f"<title>{escape(mark_text(t, level, text))}</title>"
            f'<line x1="{x:.1f}" y1="{BAR_TOP - 12}" x2="{x:.1f}" y2="{BAR_TOP + BAR_H}"/>'
            f'<polygon points="{x - 6:.1f},{BAR_TOP - 24} {x + 6:.1f},{BAR_TOP - 24} '
            f'{x:.1f},{BAR_TOP - 10}"/></g>'
        )
    for t in (t0, (t0 + t1) / 2, t1):
        anchor = "start" if t == t0 else "end" if t == t1 else "middle"
        parts.append(
            f'<text class="fr-tick" x="{px(t):.1f}" y="{BAR_TOP + BAR_H + 16}" '
            f'text-anchor="{anchor}">{_clock(t - t0)}</text>'
        )
    parts.append(
        f'<text class="fr-tick" x="{W / 2:.0f}" y="{H - 2}" text-anchor="middle">'
        f"{escape(labels['time'])}</text></svg>"
    )
    # Sólo números formateados (`:.1f`) y rótulos escapados con `escape`.
    return mark_safe("".join(parts))  # noqa: S308  # nosec B308 B703
