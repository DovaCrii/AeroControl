import calendar
from datetime import date, datetime, timedelta

from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.generic import CreateView, DetailView, ListView

from apps.core.audit import set_audit_context
from apps.core.views import (
    CalendarAccessMixin,
    CsvExportMixin,
    HtmxFormMixin,
    ModelPermissionRequiredMixin,
    ModelViewPermissionRequiredMixin,
    SearchMixin,
    StatusTransitionView,
    allowed_calendar_types,
)
from .forms import FlightPermissionForm, FlightRecordForm
from .models import FlightPermission, FlightRecord
from apps.registry.models import Aircraft, CostCenter, Operator
from apps.registry.selectors import operator_aircraft_compatibility_gaps


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
    # This app's list URLs are named "permission-list"/"record-list", not the
    # "<model_name>-list" this base class assumed (a pre-existing bug: a
    # successful create crashed with NoReverseMatch, caught by OPS-4's first
    # test that POSTs all the way through FlightPermissionCreate).
    success_url_name = None

    def get_success_url(self):
        return reverse(self.success_url_name or f"{self.model._meta.model_name}-list")

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
    # Explicit override: the default (self.model._meta.fields) silently drops
    # ManyToManyFields (operators/aircraft_fleet live in _meta.many_to_many,
    # not _meta.fields), so without this the CSV export would quietly lose
    # its two most useful columns instead of erroring.
    csv_fields = [
        FlightPermission._meta.get_field(name)
        for name in (
            "permission_number",
            "operators",
            "aircraft_fleet",
            "cost_center",
            "purpose",
            "valid_from",
            "valid_until",
            "location",
            "status",
        )
    ]

    def get_queryset(self):
        queryset = (
            super().get_queryset().prefetch_related("operators", "aircraft_fleet")
        )
        status = self.request.GET.get("status", "")
        if status in dict(FlightPermission.STATUS_CHOICES):
            queryset = queryset.filter(status=status)
        # OPS-4: a permission now covers a range, so "on or after date_from" /
        # "on or before date_to" become an overlap test against that range,
        # not an equality test against a single flight_date.
        if self.request.GET.get("date_from"):
            queryset = queryset.filter(valid_until__gte=self.request.GET["date_from"])
        if self.request.GET.get("date_to"):
            queryset = queryset.filter(valid_from__lte=self.request.GET["date_to"])
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            title=_("Permissions"),
            status_choices=FlightPermission.STATUS_CHOICES,
            current_status=self.request.GET.get("status", ""),
        )
        return context


class FlightPermissionCreate(OCreate):
    model = FlightPermission
    form_class = FlightPermissionForm
    success_url_name = "permission-list"

    def form_valid(self, form):
        """B4.4: warn (do not block) when an assigned operator has no current
        qualification matching an assigned aircraft's model.

        The M2M rosters (operators, aircraft_fleet) only exist on self.object
        once form.save_m2m() has run, which happens inside
        super().form_valid() -- so the check has to come after it, not before.
        """
        response = super().form_valid(form)
        gaps = operator_aircraft_compatibility_gaps(
            self.object.operators.all(), self.object.aircraft_fleet.all()
        )
        aircraft_by_operator = {}
        for operator, aircraft in gaps:
            aircraft_by_operator.setdefault(operator, []).append(aircraft)
        for operator, aircraft_list in aircraft_by_operator.items():
            messages.warning(
                self.request,
                _(
                    "%(operator)s has no current qualification matching: "
                    "%(aircraft)s. The permission was saved; review the "
                    "operator's qualifications."
                )
                % {
                    "operator": operator,
                    "aircraft": ", ".join(str(a) for a in aircraft_list),
                },
            )
        return response


class FlightPermissionDetail(ModelViewPermissionRequiredMixin, DetailView):
    model = FlightPermission
    template_name = "operations/permission_detail.html"
    context_object_name = "permission"

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(is_active=True)
            .prefetch_related("operators", "aircraft_fleet")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["history"] = self.object.history.all()
        context["flight_records"] = self.object.records.filter(is_active=True)
        # OPS-5: attachments (additional letters/correspondence) through the
        # existing generic Document pipeline -- FlightPermission is already in
        # DOCUMENTABLE_MODELS (apps/compliance/forms.py), this just surfaces
        # them here and links to the existing upload form, pre-filled.
        if self.request.user.has_perm("compliance.view_document"):
            from django.contrib.contenttypes.models import ContentType

            from apps.compliance.models import Document

            content_type = ContentType.objects.get_for_model(FlightPermission)
            context["permission_content_type_id"] = content_type.pk
            context["documents"] = Document.objects.filter(
                content_type=content_type,
                object_id=self.object.pk,
                is_current_version=True,
                is_active=True,
            ).order_by("-issue_date")
        else:
            context["documents"] = None
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
    success_message = gettext_lazy("Permission approved.")


class FlightPermissionDeny(StatusTransitionView):
    model = FlightPermission
    target_status = "denied"
    valid_from_statuses = ["requested"]
    success_message = gettext_lazy("Permission denied.")


class FlightPermissionComplete(StatusTransitionView):
    model = FlightPermission
    target_status = "completed"
    valid_from_statuses = ["approved"]
    success_message = gettext_lazy("Permission completed.")


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
    success_url_name = "record-list"

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
        set_audit_context(request, record, action="archived")
        messages.success(request, _("Flight record archived."))
        return redirect("record-list")


class CalendarView(CalendarAccessMixin, ListView):
    template_name = "core/calendar.html"
    context_object_name = "events_by_date"

    def get_queryset(self):
        return []

    def filter_options(self, model, permission, order_field):
        """Active rows for a filter dropdown, empty without the permission."""
        if not self.request.user.has_perm(permission):
            return model.objects.none()
        return model.objects.filter(is_active=True).order_by(order_field)

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
        # __range instead of __year/__month: SQLite cannot use an index for the
        # extracted-part lookups, so each one was a full table scan.
        month_start = selected
        month_end = date(
            year + (month == 12), 1 if month == 12 else month + 1, 1
        ) - timedelta(days=1)

        from apps.maintenance.models import MaintenanceRecord
        from apps.workboard.selectors import visible_tasks_for_user

        allowed_types = allowed_calendar_types(self.request.user)
        events = {}
        if "permission" in allowed_types:
            # OPS-4: a permission spans a validity range, not a single day, so
            # an overlap test (not equality) selects it, and it is placed on
            # every day of the month it actually covers -- not just its
            # start. select_related -> prefetch_related: operators/aircraft
            # are now M2M, and select_related only ever worked on FK/O2O.
            for permission in FlightPermission.objects.filter(
                valid_from__lte=month_end, valid_until__gte=month_start, is_active=True
            ).prefetch_related("operators", "aircraft_fleet"):
                first_day = max(permission.valid_from, month_start)
                last_day = min(permission.valid_until, month_end)
                day = first_day
                while day <= last_day:
                    events.setdefault(day, []).append(("permission", permission))
                    day += timedelta(days=1)
        if "maintenance" in allowed_types:
            for record in MaintenanceRecord.objects.filter(
                scheduled_date__range=(month_start, month_end), is_active=True
            ).select_related("aircraft"):
                events.setdefault(record.scheduled_date, []).append(
                    ("maintenance", record)
                )
        if "task" in allowed_types:
            for task in (
                visible_tasks_for_user(self.request.user)
                .filter(due_date__range=(month_start, month_end))
                .select_related("board", "stage")
            ):
                events.setdefault(task.due_date, []).append(("task", task))

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
            selected_calendar_types=self.request.GET.get("types", "all"),
            selected_calendar_board=self.request.GET.get("board", ""),
            selected_calendar_cost_center=self.request.GET.get("cost_center", ""),
            selected_calendar_aircraft=self.request.GET.get("aircraft", ""),
            selected_calendar_operator=self.request.GET.get("operator", ""),
            # The filter dropdowns are a listing of the registry in their own
            # right, so each one needs the view permission of its model. Without
            # it they used to expose every cost center, registration and
            # operator to any authenticated user.
            calendar_cost_centers=self.filter_options(
                CostCenter, "registry.view_costcenter", "code"
            ),
            calendar_aircraft=self.filter_options(
                Aircraft, "registry.view_aircraft", "registration"
            ),
            calendar_operators=self.filter_options(
                Operator, "registry.view_operator", "full_name"
            ),
            current_language=getattr(self.request, "LANGUAGE_CODE", "es"),
            today=today,
            cal_year=year,
            cal_month=month,
        )
        return context
