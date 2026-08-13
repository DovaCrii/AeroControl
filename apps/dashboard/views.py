from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.db.models.functions import TruncMonth
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.compliance.digest import bucket_for
from apps.compliance.models import Alert, AlertRule, Document, DocumentType
from apps.maintenance.models import MaintenanceRecord
from apps.operations.models import FlightPermission, FlightRecord
from apps.registry.models import Aircraft, CostCenter, Operator, Qualification
from apps.workboard.models import KanbanStage, KanbanTask


def upcoming_expirations(today, cutoff, cost_center=None):
    """The real expiries in the [today, cutoff] window across the three things
    that actually expire (T5.4/U4): operator qualifications, compliance
    documents and flight permissions -- not just qualifications as before. Each
    item carries a link so the dashboard lands the user on the record to act.

    Qualifications and permissions honour the cost-center filter; documents hang
    off a generic relation with no direct cost center, so they are always
    included (they are also watched by the alert engine and the report).

    R1.1: each item's "bucket" reuses digest.bucket_for -- the same
    overdue/due_7/due_15/due_30 scale as the compliance report and the Kanban
    card (B3.3), instead of a fourth scale. The panel is a flat gray badge
    today regardless of how soon something expires, which is exactly why the
    live review flagged it as "pasa desapercibida" (easy to miss).
    """
    items = []

    quals = Qualification.objects.filter(
        is_active=True, expiry_date__gte=today, expiry_date__lte=cutoff
    ).select_related("operator", "qualification_type")
    if cost_center:
        quals = quals.filter(operator__cost_center=cost_center)
    for qual in quals:
        items.append(
            {
                "kind": _("Qualification"),
                "label": f"{qual.operator} — {qual.qualification_type}",
                "date": qual.expiry_date,
                "bucket": bucket_for(qual.expiry_date, today),
                "url": reverse("operator-detail", args=[qual.operator_id]),
            }
        )

    # LV-29: the DGAC vigencias join the same window -- a lapsing credential or
    # JAC insurance is exactly what "upcoming expirations" is for.
    credentials = Operator.objects.filter(
        is_active=True, credential_expiry__gte=today, credential_expiry__lte=cutoff
    )
    if cost_center:
        credentials = credentials.filter(cost_center=cost_center)
    for operator in credentials:
        items.append(
            {
                "kind": _("DGAC credential"),
                "label": operator.full_name,
                "date": operator.credential_expiry,
                "bucket": bucket_for(operator.credential_expiry, today),
                "url": reverse("operator-detail", args=[operator.pk]),
            }
        )

    insured = Aircraft.objects.filter(
        is_active=True, insurance_expiry__gte=today, insurance_expiry__lte=cutoff
    )
    if cost_center:
        insured = insured.filter(cost_center=cost_center)
    for aircraft in insured:
        items.append(
            {
                "kind": _("JAC insurance"),
                "label": aircraft.registration,
                "date": aircraft.insurance_expiry,
                "bucket": bucket_for(aircraft.insurance_expiry, today),
                "url": reverse("aircraft-detail", args=[aircraft.pk]),
            }
        )

    documents = Document.objects.filter(
        is_active=True,
        is_current_version=True,
        expiry_date__isnull=False,
        expiry_date__gte=today,
        expiry_date__lte=cutoff,
    ).select_related("doc_type")
    for document in documents:
        items.append(
            {
                "kind": _("Document"),
                "label": document.title,
                "date": document.expiry_date,
                "bucket": bucket_for(document.expiry_date, today),
                "url": reverse("document-detail", args=[document.pk]),
            }
        )

    permissions = FlightPermission.objects.filter(
        is_active=True, valid_until__gte=today, valid_until__lte=cutoff
    )
    if cost_center:
        permissions = permissions.filter(cost_center=cost_center)
    for permission in permissions:
        items.append(
            {
                "kind": _("Flight permission"),
                # R1.2/R2.2/R2.3: used to be `permission_number or "Pending
                # DGAC folio"` -- permission_number is None until the DGAC
                # folio arrives (LV-39), and rendered as-is the row read
                # "Flight permission None" (verified live on the demo).
                # internal_folio is assigned at creation and never blank.
                "label": permission.internal_folio,
                "date": permission.valid_until,
                "bucket": bucket_for(permission.valid_until, today),
                "url": reverse("permission-detail", args=[permission.pk]),
            }
        )

    items.sort(key=lambda item: item["date"])
    return items


def panel_forecast(today, cost_center=None, user=None):
    """R8.4: the weather for the operation's next flight, for the panel.

    Until now the forecast only existed on a geo plan's page, and only when that
    plan had an area *and* a linked permit with a date -- buried, for something
    that gets consulted before every flight. What makes it reachable here is
    OPS-4: the permit carries its own `latitude`/`longitude`, so no geo plan is
    needed.

    **One call, never N.** The panel is opened by everyone, every day, so this
    resolves a single location and asks for a single (coordinate, day) -- the
    same cached entry the whole office shares. Showing every upcoming permit
    would be one outgoing request per permit per page load, which is the shape
    this project already paid for twice (V.18/V.19).

    Where the location comes from, in order:

    1. the next permit that is not finished or denied and does carry
       coordinates -- the actual next flight, and the day is clamped to today so
       a permit whose window is already open forecasts today rather than a start
       date in the past;
    2. failing that, the selected cost center's own site coordinates (R8.4
       option (c)) -- which is what makes the panel's cost-center filter double
       as the location selector.

    Returns a dict with `weather` set to None whenever the feature is off, no
    location is on file, or the provider did not answer; the card then does not
    render at all. Never raises: this feeds the page every login lands on.

    Each source is gated on the `view_*` of the model it reads (AGENTS.md's
    read contract): the card names a permit folio, its site and its aircraft, so
    it must not become a way around `view_flightpermission`.
    """
    from apps.core.weather import forecast_for

    def may_see(permission_codename):
        return user is None or user.has_perm(permission_codename)

    permissions = FlightPermission.objects.filter(
        is_active=True,
        latitude__isnull=False,
        longitude__isnull=False,
        valid_until__gte=today,
    ).exclude(
        # None of these has a flight left to plan for: one already happened,
        # one is not going to, and one ran out of time (LV-83). The date filter
        # above already rules the expired ones out; listing the status keeps the
        # intent readable rather than relying on that coincidence.
        status__in=[
            FlightPermission.STATUS_COMPLETED,
            FlightPermission.STATUS_DENIED,
            FlightPermission.STATUS_EXPIRED,
        ]
    )
    if cost_center:
        permissions = permissions.filter(cost_center=cost_center)
    permission = (
        permissions.select_related("cost_center").order_by("valid_from").first()
        if may_see("operations.view_flightpermission")
        else None
    )

    if permission is not None:
        # Bounded on purpose (one query, three values): the card names what is
        # flying, but a permit with a large fleet must not turn into a wall.
        fleet = list(
            permission.aircraft_fleet.filter(is_active=True).values_list(
                "registration", flat=True
            )[:3]
        )
        return {
            "weather": forecast_for(
                permission.latitude,
                permission.longitude,
                max(permission.valid_from, today),
            ),
            "weather_date": max(permission.valid_from, today),
            "weather_source": "permission",
            "weather_place": permission.area_name or permission.location,
            "weather_folio": permission.internal_folio,
            "weather_fleet": ", ".join(fleet),
            "weather_url": reverse("permission-detail", args=[permission.pk]),
        }

    coordinates = (
        cost_center.coordinates
        if cost_center and may_see("registry.view_costcenter")
        else None
    )
    if coordinates is None:
        # No upcoming located flight and no site on file. Deliberately not a
        # guessed location: a forecast for the wrong place, next to a real date,
        # is worse than no card.
        return {"weather": None}
    latitude, longitude = coordinates
    return {
        "weather": forecast_for(latitude, longitude, today),
        "weather_date": today,
        "weather_source": "cost_center",
        "weather_place": str(cost_center),
        "weather_url": reverse("costcenter-detail", args=[cost_center.pk]),
    }


@login_required
def dashboard(request):
    # OPS-8: an optional global filter by cost center. Silently ignored if it
    # does not resolve to a real, active cost center -- same "malformed filter
    # is a no-op, not an error" convention SearchMixin already uses.
    selected_cost_center = None
    cost_center_id = request.GET.get("cost_center")
    if cost_center_id:
        selected_cost_center = CostCenter.objects.filter(
            pk=cost_center_id, is_active=True
        ).first()
    cost_centers = CostCenter.objects.filter(is_active=True).order_by("code")

    # --- Summary counts ---
    aircraft_qs = Aircraft.objects.filter(is_active=True)
    operator_qs = Operator.objects.filter(is_active=True)
    if selected_cost_center:
        aircraft_qs = aircraft_qs.filter(cost_center=selected_cost_center)
        operator_qs = operator_qs.filter(cost_center=selected_cost_center)
    aircraft_count = aircraft_qs.filter(status="active").count()
    operator_count = operator_qs.count()
    alert_count = Alert.objects.filter(is_active=True, is_resolved=False).count()

    # --- Compliance module setup state ---
    # The old onboarding card required *everything* to be empty, so with the
    # registry loaded it could never fire again - while compliance sat at zero
    # and the tiles read "0 alerts" as if all was well. These three steps are
    # what turns the digest, the alerts and the report from built to working.
    compliance_setup = {
        "doc_types": DocumentType.objects.filter(is_active=True).exists(),
        "documents": Document.objects.filter(is_active=True).exists(),
        "rules": AlertRule.objects.filter(is_active=True).exists(),
    }
    compliance_incomplete = not all(compliance_setup.values())

    # --- Expirations ---
    # Bounded on both ends: without the floor this listed every historically
    # expired qualification, on a page opened at every login. The summary tile
    # keeps the real count; only the visible list is capped.
    today = timezone.localdate()
    cutoff = today + timedelta(days=30)
    all_expirations = upcoming_expirations(today, cutoff, selected_cost_center)
    expiring_count = len(all_expirations)
    expirations = all_expirations[:10]

    # --- LV-30: monthly compliance snapshot (latest period on record) ---
    # Compliant / total cost centers for the most recent reviewed month, with a
    # link into the monthly-review page. Absent (card hidden) until the first
    # month closes and check_monthly_records creates reviews.
    from django.db.models import Max

    from apps.compliance.models import MonthlyComplianceReview

    monthly_records = None
    review_qs = MonthlyComplianceReview.objects.filter(is_active=True)
    if selected_cost_center:
        review_qs = review_qs.filter(cost_center=selected_cost_center)
    latest_period = review_qs.aggregate(latest=Max("period"))["latest"]
    if latest_period:
        period_reviews = review_qs.filter(period=latest_period)
        monthly_records = {
            "period": latest_period.strftime("%Y-%m"),
            "total": period_reviews.count(),
            "compliant": period_reviews.filter(
                status=MonthlyComplianceReview.STATUS_COMPLETED
            ).count(),
            "pending": period_reviews.filter(
                status=MonthlyComplianceReview.STATUS_PENDING
            ).count(),
        }

    # --- Kanban stages (archived tasks must not inflate the counts) ---
    stages = KanbanStage.objects.filter(is_active=True).annotate(
        active_task_count=Count("tasks", filter=Q(tasks__is_active=True))
    )
    tasks_by_stage = [
        {"name": stage.name, "count": stage.active_task_count} for stage in stages
    ]

    # Charts label their slices with the human-readable choice, not the raw
    # database value (the legend used to read "active"/"in_progress"), and the
    # aggregations exclude archived rows like the rest of the app.
    def labelled(rows, field, choices):
        labels = dict(choices)
        return [
            {field: str(labels.get(row[field], row[field])), "count": row["count"]}
            for row in rows
        ]

    # --- Chart: Aircraft by status ---
    aircraft_by_status = labelled(
        aircraft_qs.values("status").annotate(count=Count("id")).order_by("status"),
        "status",
        Aircraft.STATUS_CHOICES,
    )

    # --- Chart: Permissions by status ---
    permissions_qs = FlightPermission.objects.filter(is_active=True)
    if selected_cost_center:
        permissions_qs = permissions_qs.filter(cost_center=selected_cost_center)
    perms_by_status = labelled(
        permissions_qs.values("status").annotate(count=Count("id")).order_by("status"),
        "status",
        FlightPermission.STATUS_CHOICES,
    )

    # --- Chart: Maintenance by type ---
    maintenance_qs = MaintenanceRecord.objects.filter(is_active=True)
    if selected_cost_center:
        maintenance_qs = maintenance_qs.filter(
            aircraft__cost_center=selected_cost_center
        )
    maint_by_type = labelled(
        maintenance_qs.values("maintenance_type")
        .annotate(count=Count("id"))
        .order_by("maintenance_type"),
        "maintenance_type",
        MaintenanceRecord.TYPES,
    )

    # --- LV-8e: maintenance that still needs planning ---
    # "To be defined" or missing a scheduled date, and not yet completed. The
    # alert engine only watches date *expiry*, so this absence is surfaced here
    # (and in the compliance report) instead of as an Alert object.
    incomplete_maintenance_count = (
        maintenance_qs.filter(status__in=["pending", "in_progress"])
        .filter(Q(maintenance_type="to_be_defined") | Q(scheduled_date__isnull=True))
        .count()
    )

    # --- Chart: Tasks by priority ---
    # Not filtered by cost center: Kanban boards scope by tenant/board access,
    # a different axis (apps/core/views.py's calendar keeps the same split),
    # not every task has an assignee with a cost center.
    tasks_by_priority = labelled(
        KanbanTask.objects.filter(is_active=True)
        .values("priority")
        .annotate(count=Count("id"))
        .order_by("priority"),
        "priority",
        KanbanTask.PRIORITIES,
    )

    # --- Chart: Monthly flight records (last 6 months) ---
    six_months_ago = timezone.localdate() - timedelta(days=180)
    flight_records_qs = FlightRecord.objects.filter(
        is_active=True, actual_date__gte=six_months_ago
    )
    if selected_cost_center:
        flight_records_qs = flight_records_qs.filter(
            aircraft__cost_center=selected_cost_center
        )
    monthly_flights = list(
        flight_records_qs.annotate(month=TruncMonth("actual_date"))
        .values("month")
        .annotate(count=Count("id"))
        .order_by("month")
    )

    chart_data = {
        "permissions_by_status": perms_by_status,
        "maintenance_by_type": maint_by_type,
        "aircraft_by_status": aircraft_by_status,
        "tasks_by_priority": tasks_by_priority,
        "tasks_by_stage": tasks_by_stage,
        "monthly_flights": monthly_flights,
    }

    context = {
        "aircraft_count": aircraft_count,
        "operator_count": operator_count,
        "alert_count": alert_count,
        "incomplete_maintenance_count": incomplete_maintenance_count,
        "expirations": expirations,
        "expiring_count": expiring_count,
        "stages": stages,
        "chart_data": chart_data,
        "compliance_setup": compliance_setup,
        "compliance_incomplete": compliance_incomplete,
        "cost_centers": cost_centers,
        "selected_cost_center": selected_cost_center,
        "monthly_records": monthly_records,
    }
    # R8.4: after the rest of the context, so a provider hiccup cannot get in
    # the way of anything the panel already showed.
    context.update(panel_forecast(today, selected_cost_center, request.user))
    return render(request, "dashboard/index.html", context)
