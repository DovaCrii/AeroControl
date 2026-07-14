from datetime import date, timedelta
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from apps.registry.models import Aircraft, Operator
from apps.compliance.models import Alert
from apps.workboard.models import KanbanStage

@login_required
def dashboard(request):
    expirations = []
    from apps.registry.models import Qualification
    expirations = Qualification.objects.filter(is_active=True, expiry_date__isnull=False, expiry_date__lte=date.today()+timedelta(days=30)).order_by("expiry_date")
    return render(request, "dashboard/index.html", {"aircraft_count": Aircraft.objects.filter(is_active=True,status="active").count(), "operator_count": Operator.objects.filter(is_active=True).count(), "alert_count": Alert.objects.filter(is_active=True,is_resolved=False).count(), "expirations": expirations, "stages": KanbanStage.objects.filter(is_active=True).prefetch_related("tasks")})
