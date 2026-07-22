import calendar
from datetime import datetime

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.generic import CreateView, DetailView, ListView

from apps.core.views import (
    CsvExportMixin,
    HtmxFormMixin,
    ModelPermissionRequiredMixin,
    ModelViewPermissionRequiredMixin,
    SearchMixin,
    StatusTransitionView,
)
from .forms import FlightPermissionForm, FlightRecordForm
from .models import FlightPermission, FlightRecord


class OList(CsvExportMixin, SearchMixin, ModelViewPermissionRequiredMixin, ListView):
    template_name = "generic/list.html"
    context_object_name = "objects"
    paginate_by = 25

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = _(self.model._meta.verbose_name_plural.title())
        return context


class OCreate(HtmxFormMixin, ModelPermissionRequiredMixin, CreateView):
    permission_action = "add"
    template_name = "generic/form.html"

    def get_success_url(self):
        return reverse(f"{self.model._meta.model_name}-list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = _("New %(record)s") % {
            "record": _(self.model._meta.verbose_name.title())
        }
        return context


class FlightPermissionList(
    CsvExportMixin, SearchMixin, ModelViewPermissionRequiredMixin, ListView
):
    model = FlightPermission
    template_name = "operations/permission_list.html"
    context_object_name = "objects"
    paginate_by = 25
    search_fields = ["permission_number"]

    def get_queryset(self):
        queryset = super().get_queryset()
        status = self.request.GET.get("status", "")
        if status in dict(FlightPermission.STATUS_CHOICES):
            queryset = queryset.filter(status=status)
        if self.request.GET.get("date_from"):
            queryset = queryset.filter(flight_date__gte=self.request.GET["date_from"])
        if self.request.GET.get("date_to"):
            queryset = queryset.filter(flight_date__lte=self.request.GET["date_to"])
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            title=_("Permissions"),
            status_choices=FlightPermission.STATUS_CHOICES,
            current_status=self.request.GET.get("status", ""),
        )
        return context


FlightPermissionCreate = type(
    "FlightPermissionCreate",
    (OCreate,),
    {"model": FlightPermission, "form_class": FlightPermissionForm},
)


class FlightPermissionDetail(ModelViewPermissionRequiredMixin, DetailView):
    model = FlightPermission
    template_name = "operations/permission_detail.html"
    context_object_name = "permission"

    def get_queryset(self):
        return super().get_queryset().filter(is_active=True)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["history"] = self.object.history.all()
        context["flight_records"] = self.object.records.filter(is_active=True)
        if self.object.status == "requested" and self.request.user.has_perm(
            "operations.change_flightpermission"
        ):
            actions = [
                ("approve", _("Approve"), "btn-success"),
                ("deny", _("Deny"), "btn-danger"),
            ]
        elif self.object.status == "approved" and self.request.user.has_perm(
            "operations.change_flightpermission"
        ):
            actions = [("complete", _("Complete"), "btn-primary")]
        else:
            actions = []
        context["status_actions"] = actions
        return context


class FlightPermissionApprove(StatusTransitionView):
    model = FlightPermission
    target_status = "approved"
    valid_from_statuses = ["requested"]
    success_message = "Permission approved."


class FlightPermissionDeny(StatusTransitionView):
    model = FlightPermission
    target_status = "denied"
    valid_from_statuses = ["requested"]
    success_message = "Permission denied."


class FlightPermissionComplete(StatusTransitionView):
    model = FlightPermission
    target_status = "completed"
    valid_from_statuses = ["approved"]
    success_message = "Permission completed."


FlightRecordList = type(
    "FlightRecordList",
    (OList,),
    {
        "model": FlightRecord,
        "search_fields": [
            "permission__permission_number",
            "pilot__full_name",
            "aircraft__registration",
        ],
    },
)


class FlightRecordCreate(OCreate):
    model = FlightRecord
    form_class = FlightRecordForm
    template_name = "operations/flightrecord_form.html"

    def get_initial(self):
        initial = super().get_initial()
        for field in ("permission", "pilot", "aircraft"):
            value = self.request.GET.get(field)
            if value:
                initial[field] = value
        return initial


class FlightRecordDetail(ModelViewPermissionRequiredMixin, DetailView):
    model = FlightRecord
    template_name = "operations/flightrecord_detail.html"
    context_object_name = "record"

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(is_active=True)
            .select_related("permission", "pilot", "aircraft")
        )


class FlightRecordDelete(ModelPermissionRequiredMixin, DetailView):
    model = FlightRecord
    permission_action = "delete"
    context_object_name = "object"

    def post(self, request, *args, **kwargs):
        record = self.get_object()
        record.is_active = False
        record.save(update_fields=["is_active", "updated_at"])
        messages.success(request, _("Flight record archived."))
        return redirect("record-list")


class CalendarView(LoginRequiredMixin, ListView):
    template_name = "core/calendar.html"
    context_object_name = "events_by_date"

    def get_queryset(self):
        return []

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.now().date()
        try:
            selected = datetime.strptime(
                self.request.GET.get("month", ""), "%Y-%m"
            ).date()
        except ValueError:
            selected = today.replace(day=1)
        year, month = selected.year, selected.month

        from apps.maintenance.models import MaintenanceRecord

        events = {}
        for permission in FlightPermission.objects.filter(
            flight_date__year=year, flight_date__month=month, is_active=True
        ).select_related("operator", "aircraft"):
            events.setdefault(permission.flight_date, []).append(
                ("permission", permission)
            )
        for record in MaintenanceRecord.objects.filter(
            scheduled_date__year=year, scheduled_date__month=month, is_active=True
        ).select_related("aircraft"):
            events.setdefault(record.scheduled_date, []).append(("maintenance", record))

        previous = selected.replace(day=1)
        if month == 1:
            previous = previous.replace(year=year - 1, month=12)
        else:
            previous = previous.replace(month=month - 1)
        if month == 12:
            following = selected.replace(year=year + 1, month=1)
        else:
            following = selected.replace(month=month + 1)

        context.update(
            month_name=selected,
            month_days=calendar.Calendar(firstweekday=0).monthdayscalendar(year, month),
            events=events,
            month_value=selected.strftime("%Y-%m"),
            prev_month=previous.strftime("%Y-%m"),
            next_month=following.strftime("%Y-%m"),
            today=today,
            cal_year=year,
            cal_month=month,
        )
        return context
