"""R5.4/R7.1: cumulative flight time per aircraft.

FlightRecord.duration is a Python property (departure/arrival time combined
with the flight's date, midnight-crossing handled) rather than a stored DB
column, so the total is summed in Python. Fine at the scale this is used at
-- one aircraft's own flight history on its fiche, not a fleet-wide report.
"""

from datetime import timedelta


def format_duration(duration):
    """ "1h 05min" (or "05min" under an hour) for a `timedelta` -- shared by
    FlightRecord.duration_display (a single flight, always under a day) and
    the aggregate below (which can exceed a day, so this uses
    `total_seconds()`, not `.seconds`, which wraps at 24h)."""
    total_minutes = int(duration.total_seconds() // 60)
    hours, minutes = divmod(total_minutes, 60)
    if hours:
        return f"{hours}h {minutes:02d}min"
    return f"{minutes}min"


def total_flight_duration(aircraft):
    """This aircraft's cumulative flight time (R7.1: ISO clause 7.1.3)."""
    from .models import FlightRecord

    records = FlightRecord.objects.filter(aircraft=aircraft, is_active=True)
    return sum((record.duration for record in records), timedelta())


# R7.5 (ISO 45001 6.1.2/8.1.2): pilot fatigue is one of the hazards the field
# IPER has to control, and a duty limit is the control the guide names. 8 hours
# of flight time in one day, decided with the user on 2026-08-12.
#
# This counts *flight* time, not time on site: it is what the records actually
# hold. A pilot's real duty day is longer (travel, setup, waiting on weather),
# so treat this as a floor -- crossing it certainly exceeds the limit, staying
# under it does not prove the day was within it.
DAILY_FLIGHT_LIMIT = timedelta(hours=8)


def duty_time_for(pilot, day):
    """Total flight time this pilot logged on `day`.

    Summed in Python for the same reason as total_flight_duration above:
    `FlightRecord.duration` is a property, not a column.
    """
    from .models import FlightRecord

    records = FlightRecord.objects.filter(pilot=pilot, actual_date=day, is_active=True)
    return sum((record.duration for record in records), timedelta())


def pilots_over_daily_limit(day):
    """[(pilot, duty_time), ...] for everyone past the limit on `day`.

    One query for the day's records, then grouped in Python -- the alternative
    (a query per pilot) is the shape that made the Kanban board slow (V.19).
    """
    from .models import FlightRecord

    totals = {}
    records = FlightRecord.objects.filter(
        actual_date=day, is_active=True
    ).select_related("pilot")
    for record in records:
        totals[record.pilot] = totals.get(record.pilot, timedelta()) + record.duration
    return sorted(
        (
            (pilot, total)
            for pilot, total in totals.items()
            if total > DAILY_FLIGHT_LIMIT
        ),
        key=lambda pair: pair[1],
        reverse=True,
    )
