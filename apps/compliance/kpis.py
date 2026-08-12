"""R7.7: the two operational KPIs that need no new data (ISO 9001 9.1.1).

The audit guide asks for five operational KPIs. Three of them
(precision achieved vs. required, reflight rate, incident-free flight hours)
depend on `Deliverable` (R7.4) and `NonConformity` (R7.6), which do not exist
yet. These two are derivable today from what the operation already records --
see docs/dev/iso-r7-design-plan.md, "De qué dependen los KPI operacionales".

9.1.1 asks for a **target**, a **trend** and **action when it is missed**. This
module provides the value and the comparison against the target; the trend for
document KPIs comes from `ComplianceSnapshot` (R7.7's first half, already
built). Targets live here as documented constants rather than in the
`KpiTarget` model the design sketches: one number is a constant, and a
configuration table with a single row in it is a table nobody maintains. When a
second target with a different owner appears, that is when the model earns its
place.
"""

from django.utils.translation import gettext_lazy as _

# Decided with the user on 2026-08-12. Tolerates roughly one aircraft of a
# ~16-strong fleet being out at any moment.
FLEET_AVAILABILITY_TARGET = 90.0

# No target set yet: the value and its trend are shown, and nothing is flagged
# as a miss. A target invented here would be a threshold nobody agreed to, and
# 9.1.1 wants action on a missed target -- action on an arbitrary line is how a
# KPI turns into noise people learn to ignore.
ON_TIME_EXECUTION_TARGET = None


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


def operational_kpis(start, end):
    """Both KPIs, shaped for the report template and the executive email.

    `pct is None` means "nothing to measure in this period" -- an empty fleet,
    or no permit whose window closed. Rendered as "—", never as 0%: zero would
    read as total failure where the honest answer is that the question does not
    apply.
    """
    availability = fleet_availability()
    execution = on_time_execution(start, end)
    return [
        {
            "code": "fleet_availability",
            "label": _("Fleet availability"),
            "help": _("Aircraft flyable now, excluding retired ones."),
            "value": availability["pct"],
            "detail": f"{availability['available']}/{availability['total']}",
            "target": availability["target"],
            "met": (
                None
                if availability["pct"] is None or availability["target"] is None
                else availability["pct"] >= availability["target"]
            ),
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
            "met": (
                None
                if execution["pct"] is None or execution["target"] is None
                else execution["pct"] >= execution["target"]
            ),
        },
    ]
