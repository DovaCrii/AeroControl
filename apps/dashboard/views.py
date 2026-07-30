from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.db.models.functions import TruncMonth
from django.shortcuts import render
from django.utils import timezone

from apps.compliance.models import Alert, AlertRule, Document, DocumentType
from apps.maintenance.models import MaintenanceRecord
from apps.operations.models import FlightPermission, FlightRecord
from apps.registry.models import Aircraft, CostCenter, Operator, Qualification
from apps.workboard.models import KanbanStage, KanbanTask


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
    expiring = Qualification.objects.filter(
        is_active=True,
        expiry_date__isnull=False,
        expiry_date__gte=today,
        expiry_date__lte=cutoff,
    )
    if selected_cost_center:
        expiring = expiring.filter(operator__cost_center=selected_cost_center)
    expiring_count = expiring.count()
    expirations = expiring.select_related("operator", "qualification_type").order_by(
        "expiry_date"
    )[:10]

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
    }
    return render(request, "dashboard/index.html", context)
