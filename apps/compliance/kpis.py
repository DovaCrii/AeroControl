"""R7.7: the five operational KPIs the audit guide asks for (ISO 9001 9.1.1).

Two of them (fleet availability, on-time execution) were derivable from what
the operation already recorded. The other three -- precision achieved vs.
required, reflight rate, incident-free flight hours -- waited on `Deliverable`
(R7.4) and `NonConformity` (R7.6); both landed on 2026-08-12, so the list is
now complete. See docs/dev/iso-r7-design-plan.md, "De qué dependen los KPI
operacionales".

9.1.1 asks for a **target**, a **trend** and **action when it is missed**. This
module provides the value and the comparison against the target; the trend for
document KPIs comes from `ComplianceSnapshot` (R7.7's first half, already
built). Targets live here as documented constants rather than in the
`KpiTarget` model the design sketches: one number is a constant, and a
configuration table with a single row in it is a table nobody maintains. When a
second target with a different owner appears, that is when the model earns its
place.

Two things every reader of this module has to keep straight, and which are
therefore declared per KPI rather than inferred: **which direction is good**
(the reflight rate is the only one where lower wins) and **what the figure is**
(all percentages except the incident-free counter, which is a duration).
"""

from datetime import timedelta

from django.utils.translation import gettext_lazy as _

# Decided with the user on 2026-08-12. Tolerates roughly one aircraft of a
# ~16-strong fleet being out at any moment.
FLEET_AVAILABILITY_TARGET = 90.0

# No target set yet: the value and its trend are shown, and nothing is flagged
# as a miss. A target invented here would be a threshold nobody agreed to, and
# 9.1.1 wants action on a missed target -- action on an arbitrary line is how a
# KPI turns into noise people learn to ignore. Same for the rest below.
ON_TIME_EXECUTION_TARGET = None
SURVEY_ACCURACY_TARGET = None
REFLIGHT_RATE_TARGET = None

# Which way is good. Every KPI here is "higher is better" except the reflight
# rate, and leaving that to be inferred from the name is how a red badge ends
# up on the best month of the year.
HIGHER_IS_BETTER = "higher"
LOWER_IS_BETTER = "lower"

# How to render the figure. Most are percentages; the incident-free counter is
# an accumulated duration, which has no target and no "out of" denominator.
UNIT_PERCENT = "percent"
UNIT_DURATION = "duration"


def _met(value, target, direction):
    """None when there is nothing to judge -- no value, or no agreed target."""
    if value is None or target is None:
        return None
    return value <= target if direction == LOWER_IS_BETTER else value >= target


def fleet_availability():
    """Percentage of the fleet that is flyable right now.

    `Aircraft.status` is the condition axis (OPS-3 separated it from
    `current_location`): "active" is flyable, "damaged" and "maintenance" are
    not. **"retired" is excluded from the denominator entirely** -- a
    decommissioned aircraft is not unavailable, it left the fleet, and counting
    it would make the number sag permanently for a good decision.
    """
    from apps.registry.models import Aircraft

    fleet = Aircraft.objects.filter(is_active=True).exclude(status="retired")
    total = fleet.count()
    if not total:
        return {
            "total": 0,
            "available": 0,
            "pct": None,
            "target": FLEET_AVAILABILITY_TARGET,
        }
    available = fleet.filter(status="active").count()
    return {
        "total": total,
        "available": available,
        "pct": round(available * 100 / total, 1),
        "target": FLEET_AVAILABILITY_TARGET,
    }


def on_time_execution(start, end):
    """Percentage of committed work that was flown inside its own window.

    Measured over the **approved permits whose validity ended within the
    period**, asking whether each one has at least one flight recorded against
    it. A permit that expired with nothing flown is committed work that did not
    happen on time; that is the failure this KPI is for.

    Deliberately *not* "flights outside the permit's date range": the flight
    form already refuses those (`FlightRecordForm.clean`), so that reading is
    ~100% by construction, and a KPI whose value cannot move is not a KPI --
    the same trap R6.4 documented for the document counters.

    Only permits already past their window are counted: one still open has not
    failed anything yet, and including it would score the period lower the
    earlier you look at it.
    """
    from apps.operations.models import FlightPermission

    permits = FlightPermission.objects.filter(
        is_active=True,
        status__in=("approved", "completed"),
        valid_until__gte=start,
        valid_until__lte=end,
    )
    total = permits.count()
    if not total:
        return {
            "total": 0,
            "on_time": 0,
            "pct": None,
            "target": ON_TIME_EXECUTION_TARGET,
        }
    on_time = permits.filter(records__is_active=True).distinct().count()
    return {
        "total": total,
        "on_time": on_time,
        "pct": round(on_time * 100 / total, 1),
        "target": ON_TIME_EXECUTION_TARGET,
    }


def survey_accuracy(start, end):
    """Share of assessed deliverables that met the contract's criteria.

    This is the guide's "precision achieved vs. required", aggregated. Only
    deliverables that could actually be judged count: one whose contract set no
    thresholds is not a pass and not a failure, and folding it into either
    direction would make the number describe how many contracts have criteria
    rather than how good the work was.
    """
    from apps.compliance.models import Deliverable

    assessed, met = 0, 0
    candidates = Deliverable.objects.filter(
        is_active=True,
        validated_at__date__gte=start,
        validated_at__date__lte=end,
    ).select_related("cost_center")
    for deliverable in candidates:
        verdict = deliverable.meets_acceptance_criteria
        if verdict is None:
            continue
        assessed += 1
        met += 1 if verdict else 0
    if not assessed:
        return {"total": 0, "met": 0, "pct": None}
    return {"total": assessed, "met": met, "pct": round(met * 100 / assessed, 1)}


def reflight_rate(start, end):
    """Reflights as a share of the flights actually flown in the period.

    Denominator is flights, not deliverables: a reflight is a flight that had
    to be repeated, so "out of how many flights" is the question it answers.
    **Lower is better here**, unlike every other KPI in this module -- which is
    why `operational_kpis` marks its direction explicitly instead of leaving
    the reader to infer it from the name.
    """
    from apps.compliance.models import NonConformity
    from apps.operations.models import FlightRecord

    flights = FlightRecord.objects.filter(
        is_active=True, actual_date__gte=start, actual_date__lte=end
    ).count()
    reflights = NonConformity.objects.filter(
        is_active=True,
        source=NonConformity.SOURCE_REFLIGHT,
        detected_on__gte=start,
        detected_on__lte=end,
    ).count()
    if not flights:
        return {"flights": 0, "reflights": reflights, "pct": None}
    return {
        "flights": flights,
        "reflights": reflights,
        "pct": round(reflights * 100 / flights, 1),
    }


def incident_free_flight_hours():
    """Flight hours accumulated since the last recorded incident.

    A running counter, not a percentage -- the "N days without an accident"
    shape, which is how this figure is read in practice. Counts from the day
    after the incident was detected, and over the whole history when there has
    never been one, which is the honest reading of "no incidents so far".
    """
    from apps.compliance.models import NonConformity
    from apps.operations.models import FlightRecord
    from apps.operations.selectors import format_duration

    last_incident = (
        NonConformity.objects.filter(
            is_active=True, source=NonConformity.SOURCE_INCIDENT
        )
        .order_by("-detected_on")
        .first()
    )
    records = FlightRecord.objects.filter(is_active=True)
    if last_incident is not None:
        records = records.filter(actual_date__gt=last_incident.detected_on)
    total = sum((record.duration for record in records), timedelta())
    return {
        "since": last_incident.detected_on if last_incident else None,
        "hours": round(total.total_seconds() / 3600, 1),
        "display": format_duration(total),
    }


def operational_kpis(start, end):
    """Both KPIs, shaped for the report template and the executive email.

    `pct is None` means "nothing to measure in this period" -- an empty fleet,
    or no permit whose window closed. Rendered as "—", never as 0%: zero would
    read as total failure where the honest answer is that the question does not
    apply.
    """
    availability = fleet_availability()
    execution = on_time_execution(start, end)
    accuracy = survey_accuracy(start, end)
    reflights = reflight_rate(start, end)
    incident_free = incident_free_flight_hours()
    return [
        {
            "code": "fleet_availability",
            "label": _("Fleet availability"),
            "help": _("Aircraft flyable now, excluding retired ones."),
            "value": availability["pct"],
            "detail": f"{availability['available']}/{availability['total']}",
            "target": availability["target"],
            "unit": UNIT_PERCENT,
            "direction": HIGHER_IS_BETTER,
            "met": _met(availability["pct"], availability["target"], HIGHER_IS_BETTER),
        },
        {
            "code": "on_time_execution",
            "label": _("On-time execution"),
            "help": _(
                "Approved permits whose validity ended in this period with at "
                "least one flight recorded."
            ),
            "value": execution["pct"],
            "detail": f"{execution['on_time']}/{execution['total']}",
            "target": execution["target"],
            "unit": UNIT_PERCENT,
            "direction": HIGHER_IS_BETTER,
            "met": _met(execution["pct"], execution["target"], HIGHER_IS_BETTER),
        },
        {
            "code": "survey_accuracy",
            "label": _("Survey accuracy"),
            "help": _(
                "Deliverables validated in this period that met the contract's "
                "criteria, out of those that could be assessed."
            ),
            "value": accuracy["pct"],
            "detail": f"{accuracy['met']}/{accuracy['total']}",
            "target": SURVEY_ACCURACY_TARGET,
            "unit": UNIT_PERCENT,
            "direction": HIGHER_IS_BETTER,
            "met": _met(accuracy["pct"], SURVEY_ACCURACY_TARGET, HIGHER_IS_BETTER),
        },
        {
            "code": "reflight_rate",
            "label": _("Reflight rate"),
            "help": _("Reflights recorded in this period, out of flights flown."),
            "value": reflights["pct"],
            "detail": f"{reflights['reflights']}/{reflights['flights']}",
            "target": REFLIGHT_RATE_TARGET,
            "unit": UNIT_PERCENT,
            "direction": LOWER_IS_BETTER,
            "met": _met(reflights["pct"], REFLIGHT_RATE_TARGET, LOWER_IS_BETTER),
        },
        {
            # A running counter, not a percentage: `unit` says so explicitly
            # rather than leaving the template to infer it from a null value --
            # which would also swallow the "nothing to measure" case of the
            # percentages above and print their bare "0/0".
            "code": "incident_free_flight_hours",
            "label": _("Incident-free flight hours"),
            "help": (
                _("Flight time accumulated since the incident of %(date)s.")
                % {"date": incident_free["since"].isoformat()}
                if incident_free["since"]
                else _("Flight time accumulated with no incident on record.")
            ),
            "value": None,
            "detail": incident_free["display"],
            "target": None,
            "unit": UNIT_DURATION,
            "direction": HIGHER_IS_BETTER,
            "met": None,
        },
    ]
