import json
from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.db.models.functions import TruncMonth
from django.shortcuts import render

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
    cutoff = date.today() + timedelta(days=30)
    expirations = Qualification.objects.filter(
        is_active=True,
        expiry_date__isnull=False,
        expiry_date__lte=cutoff,
    ).order_by("expiry_date")

    # --- Kanban stages ---
    stages = KanbanStage.objects.filter(is_active=True).prefetch_related("tasks")
    tasks_by_stage = [
        {"name": stage.name, "count": stage.tasks.count()} for stage in stages
    ]

    # --- Chart: Aircraft by status ---
    aircraft_by_status = list(
        Aircraft.objects.values("status")
        .annotate(count=Count("id"))
        .order_by("status")
    )

    # --- Chart: Permissions by status ---
    perms_by_status = list(
        FlightPermission.objects.values("status")
        .annotate(count=Count("id"))
        .order_by("status")
    )

    # --- Chart: Maintenance by type ---
    maint_by_type = list(
        MaintenanceRecord.objects.values("maintenance_type")
        .annotate(count=Count("id"))
        .order_by("maintenance_type")
    )

    # --- Chart: Tasks by priority ---
    tasks_by_priority = list(
        KanbanTask.objects.values("priority")
        .annotate(count=Count("id"))
        .order_by("priority")
    )

    # --- Chart: Monthly flight records (last 6 months) ---
    six_months_ago = date.today() - timedelta(days=180)
    monthly_flights = list(
        FlightRecord.objects.filter(created_at__gte=six_months_ago)
        .annotate(month=TruncMonth("created_at"))
        .values("month")
        .annotate(count=Count("id"))
        .order_by("month")
    )

    chart_data = {
        "permissions_by_status": perms_by_status,
        "maintenance_by_type": maint_by_type,
        "alerts_by_severity": [],
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
        "chart_data": json.dumps(chart_data, default=str),
    }
    return render(request, "dashboard/index.html", context)
