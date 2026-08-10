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
