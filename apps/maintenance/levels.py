"""Act. 19, Annex F: when is each maintenance level next due, per aircraft.

The Manual applies **whichever comes first** -- flight hours or elapsed time --
and a higher level restarts the lower ones. This module is the one place that
answers "what is due on this aircraft?" so the REG-020 sheet, its PDF and the
report read the same number (`MaintenanceRecord.last_completed_for_level` owns the
restart rule; `MaintenanceProgram.for_aircraft` owns which intervals apply).

Hours are only **displayed**: there is no alert engine on hours (the alert engine
watches dates). What does warn is the follow-up record dated by the month
interval (`MaintenanceRecord.schedule_next_in_level`).
"""

from dataclasses import dataclass
from decimal import Decimal

from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import (
    LEVEL_RANK,
    PROGRAM_LEVELS,
    AircraftLogbook,
    MaintenanceProgram,
    MaintenanceRecord,
    add_months,
)

# Same horizon as the "Mantenimiento programado" alert rule (15 days).
NOTICE_DAYS = 15
# PROVISIONAL (LV-443): the Manual does not define an hours notice threshold; this
# is a provisional 10 % of the interval (20 h of a 200 h basic maintenance) until
# the user confirms it. Configurable here, in one place.
HOURS_NOTICE_RATIO = Decimal("0.10")

OVERDUE, SOON, OK, NO_DATA = "overdue", "soon", "ok", "no_data"
STATE_LABELS = {
    OVERDUE: _("Overdue"),
    SOON: _("Due soon"),
    OK: _("Up to date"),
    NO_DATA: _("No data"),
}
# Chip tone per state, the same vocabulary as the rest of the fiches.
STATE_TONES = {OVERDUE: "critical", SOON: "warning", OK: "ok", NO_DATA: "neutral"}


@dataclass(frozen=True)
class LevelStatus:
    level: str
    level_label: str
    program: MaintenanceProgram
    last: MaintenanceRecord | None
    due_date: object  # date | None
    due_hours: Decimal | None
    hours_now: Decimal | None
    state: str
    # Which interval is the limiting one: "date", "hours" or "" (no data).
    limiting: str

    @property
    def state_label(self):
        return STATE_LABELS[self.state]

    @property
    def state_tone(self):
        return STATE_TONES[self.state]


def _state(program, due_date, due_hours, hours_now, today):
    reached, near = [], []
    if due_date is not None:
        days_left = (due_date - today).days
        reached.append(days_left <= 0)
        near.append(days_left <= NOTICE_DAYS)
    if due_hours is not None and hours_now is not None:
        left = due_hours - hours_now
        reached.append(left <= 0)
        near.append(left <= program.interval_hours * HOURS_NOTICE_RATIO)
    if not reached:
        return NO_DATA, ""
    if any(reached):
        # "Whichever comes first": the limiting interval is the one that was
        # reached (or, if both were, the one reached earlier -- dates win ties).
        limiting = (
            "date" if due_date is not None and (due_date - today).days <= 0 else "hours"
        )
        return OVERDUE, limiting
    state = SOON if any(near) else OK
    limiting = _first_to_come(program, due_date, due_hours, hours_now, today)
    return state, limiting


def _first_to_come(program, due_date, due_hours, hours_now, today):
    """Which interval will be reached first, judged by the fraction already used."""
    used = {}
    if due_date is not None and program.interval_months:
        total = (due_date - add_months(due_date, -program.interval_months)).days
        used["date"] = Decimal(total - (due_date - today).days) / Decimal(total or 1)
    if due_hours is not None and hours_now is not None and program.interval_hours:
        used["hours"] = (hours_now - (due_hours - program.interval_hours)) / Decimal(
            program.interval_hours
        )
    return max(used, key=used.get) if used else ""


def level_statuses(aircraft, today=None, hours_now=None):
    """`[LevelStatus]` for every level the aircraft's programme defines.

    A level with no completed maintenance has nothing to count from, so it is
    `no_data` -- it is never guessed from the aircraft's age. An interval whose
    base is missing (a completed record without `hours_at`) is skipped for that
    interval only; the other one still counts.
    """
    today = today or timezone.localdate()
    if hours_now is None:
        hours_now = AircraftLogbook.hours_for(aircraft)
    programs = MaintenanceProgram.for_aircraft(aircraft)
    labels = dict(PROGRAM_LEVELS)
    result = []
    for level in LEVEL_RANK:
        program = programs.get(level)
        if program is None:
            continue
        last = MaintenanceRecord.last_completed_for_level(aircraft, level)
        due_date = due_hours = None
        if last is not None:
            if program.interval_months and last.completed_date:
                due_date = add_months(last.completed_date, program.interval_months)
            if program.interval_hours and last.hours_at is not None:
                due_hours = last.hours_at + program.interval_hours
        state, limiting = _state(program, due_date, due_hours, hours_now, today)
        result.append(
            LevelStatus(
                level=level,
                level_label=str(labels[level]),
                program=program,
                last=last,
                due_date=due_date,
                due_hours=due_hours,
                hours_now=hours_now,
                state=state,
                limiting=limiting,
            )
        )
    return result


def overdue_by_level(aircraft_queryset, today=None):
    """`{level: number of aircraft with that level overdue}` -- for the report.

    `aircraft_queryset` is already scoped by the caller (tenant, cost center).
    Every programme level appears, with 0 when nothing is overdue.
    """
    counts = {level: 0 for level in LEVEL_RANK}
    for aircraft in aircraft_queryset:
        for status in level_statuses(aircraft, today):
            if status.state == OVERDUE:
                counts[status.level] += 1
    return counts
