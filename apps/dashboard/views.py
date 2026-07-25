from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.db.models.functions import TruncMonth
from django.shortcuts import render
from django.utils import timezone

from apps.compliance.models import Alert
from apps.maintenance.models import MaintenanceRecord
from apps.operations.models import FlightPermission, FlightRecord
from apps.registry.models import Aircraft, Operator, Qualification
from apps.workboard.models import KanbanStage, KanbanTask


@login_required
def dashboard(request):
    # --- Summary counts ---
    aircraft_count = Aircraft.objects.filter(is_active=True, status="active").count()
    operator_count = Operator.objects.filter(is_active=True).count()
    alert_count = Alert.objects.filter(is_active=True, is_resolved=False).count()

    # --- Expirations ---
    cutoff = timezone.localdate() + timedelta(days=30)
    expirations = Qualification.objects.filter(
        is_active=True,
        expiry_date__isnull=False,
        expiry_date__lte=cutoff,
    ).order_by("expiry_date")

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
        Aircraft.objects.filter(is_active=True)
        .values("status")
        .annotate(count=Count("id"))
        .order_by("status"),
        "status",
        Aircraft.STATUS_CHOICES,
    )

    # --- Chart: Permissions by status ---
    perms_by_status = labelled(
        FlightPermission.objects.filter(is_active=True)
        .values("status")
        .annotate(count=Count("id"))
        .order_by("status"),
        "status",
        FlightPermission.STATUS_CHOICES,
    )

    # --- Chart: Maintenance by type ---
    maint_by_type = labelled(
        MaintenanceRecord.objects.filter(is_active=True)
        .values("maintenance_type")
        .annotate(count=Count("id"))
        .order_by("maintenance_type"),
        "maintenance_type",
        MaintenanceRecord.TYPES,
    )

    # --- Chart: Tasks by priority ---
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
    monthly_flights = list(
        FlightRecord.objects.filter(is_active=True, actual_date__gte=six_months_ago)
        .annotate(month=TruncMonth("actual_date"))
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
        "expirations": expirations,
        "stages": stages,
        "chart_data": chart_data,
    }
    return render(request, "dashboard/index.html", context)
