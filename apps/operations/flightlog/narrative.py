"""LV-429: el párrafo de resumen de un vuelo, escrito con hechos del log y sin afirmar causas."""

from __future__ import annotations

from django.utils.formats import number_format
from django.utils.translation import gettext as _

from .types import FlightTrack

LOW_BATTERY_PCT = 20


def _final_battery(track: FlightTrack):
    for point in reversed(track.points):
        if point.battery_pct is not None:
            return point.battery_pct
    return None


def _minute(seconds: float) -> int:
    return int(round(seconds / 60))


def build_narrative(track: FlightTrack) -> dict:
    """`{"text": párrafo, "low_battery": aviso o ""}`; el texto va ya traducido."""
    s = track.summary
    sentences = []
    minutes = None if s.duration_s is None else _minute(s.duration_s)
    km = None if s.distance_m is None else number_format(s.distance_m / 1000, 1)
    height = None if s.max_height_m is None else number_format(s.max_height_m, 0)
    if None not in (minutes, km, height):
        sentences.append(
            _(
                "The flight lasted %(minutes)s min, covered %(km)s km and reached "
                "%(height)s m above the takeoff point."
            )
            % {"minutes": minutes, "km": km, "height": height}
        )
    else:
        if minutes is not None:
            sentences.append(
                _("The flight lasted %(minutes)s min.") % {"minutes": minutes}
            )
        if km is not None:
            sentences.append(_("It covered %(km)s km.") % {"km": km})
        if height is not None:
            sentences.append(
                _("It reached %(height)s m above the takeoff point.")
                % {"height": height}
            )
    warned = next(
        (
            e
            for e in track.events
            if e.code in ("tip:low_battery_rth", "warn:low_battery_rth")
        ),
        None,
    )
    leg = track.return_leg
    if warned is not None:
        key = {"minute": _minute(warned.t)}
        if leg:
            sentences.append(
                _(
                    "At minute %(minute)s the aircraft warned that the battery was only "
                    "enough to return, and it flew back in automatic mode."
                )
                % key
            )
        else:
            sentences.append(
                _(
                    "At minute %(minute)s the aircraft warned that the battery was only "
                    "enough to return."
                )
                % key
            )
    elif leg:
        sentences.append(
            _("At minute %(minute)s the aircraft started an automatic return.")
            % {"minute": _minute(leg[0])}
        )
    battery = _final_battery(track)
    warning = ""
    if battery is not None:
        shown = number_format(battery, 0)
        sentences.append(_("It landed with %(pct)s%% battery.") % {"pct": shown})
        if battery < LOW_BATTERY_PCT:
            warning = _("Low battery at landing: %(pct)s%%, under %(limit)s%%.") % {
                "pct": shown,
                "limit": LOW_BATTERY_PCT,
            }
    return {"text": " ".join(sentences), "low_battery": warning}
