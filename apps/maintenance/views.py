from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.generic import CreateView, DetailView, ListView, View

from apps.core.audit import set_audit_context
from apps.core.views import (
    CsvExportMixin,
    HtmxFormMixin,
    ModelPermissionRequiredMixin,
    ModelViewPermissionRequiredMixin,
    SearchMixin,
    StatusTransitionView,
    TenantScopedQuerysetMixin,
)
from apps.core.tenancy import scope_queryset_to_tenant
from apps.registry.models import Aircraft
from .forms import MaintenanceCompletionForm, MaintenanceRecordForm
from .models import MaintenanceHistory, MaintenanceRecord


class MList(CsvExportMixin, SearchMixin, ModelViewPermissionRequiredMixin, ListView):
    template_name = "generic/list.html"
    context_object_name = "objects"
    paginate_by = 25

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = _(self.model._meta.verbose_name_plural.title())
        return context


class MCreate(HtmxFormMixin, ModelPermissionRequiredMixin, CreateView):
    permission_action = "add"
    template_name = "generic/form.html"

    def get_success_url(self):
        return reverse("maintenance-list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = _("New %(record)s") % {
            "record": _(self.model._meta.verbose_name.title())
        }
        return context


class MaintenanceRecordList(MList):
    model = MaintenanceRecord
    template_name = "maintenance/record_list.html"
    search_fields = ["aircraft__registration", "description", "performed_by"]

    def get_queryset(self):
        queryset = super().get_queryset()
        status = self.request.GET.get("status", "")
        maintenance_type = self.request.GET.get("maintenance_type", "")
        if status in dict(MaintenanceRecord.STATUSES):
            queryset = queryset.filter(status=status)
        if maintenance_type in dict(MaintenanceRecord.TYPES):
            queryset = queryset.filter(maintenance_type=maintenance_type)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            status_choices=MaintenanceRecord.STATUSES,
            type_choices=MaintenanceRecord.TYPES,
            current_status=self.request.GET.get("status", ""),
            current_type=self.request.GET.get("maintenance_type", ""),
        )
        return context


class MaintenanceRecordCreate(MCreate):
    model = MaintenanceRecord
    form_class = MaintenanceRecordForm

    def get_initial(self):
        # LV-26: "Send to maintenance" from an aircraft's detail prefills it.
        initial = super().get_initial()
        aircraft = self.request.GET.get("aircraft")
        if aircraft:
            initial["aircraft"] = aircraft
        return initial


class MaintenanceRecordDetail(
    TenantScopedQuerysetMixin, ModelViewPermissionRequiredMixin, DetailView
):
    model = MaintenanceRecord
    template_name = "maintenance/record_detail.html"
    context_object_name = "record"
    tenant_path = "aircraft__tenant_id"

    def get_queryset(self):
        return super().get_queryset().filter(is_active=True).select_related("aircraft")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["history"] = self.object.history.all()
        context["completion_form"] = MaintenanceCompletionForm(instance=self.object)
        context["status_actions"] = (
            [("start", _("Start maintenance"), "btn-warning")]
            if self.object.status == "pending"
            else [("complete", _("Complete"), "btn-success")]
            if self.object.status == "in_progress"
            else []
        )
        return context


class MaintenanceStart(StatusTransitionView):
    model = MaintenanceRecord
    target_status = "in_progress"
    valid_from_statuses = ["pending"]
    success_message = gettext_lazy("Maintenance started.")


class MaintenanceComplete(StatusTransitionView):
    model = MaintenanceRecord
    target_status = "completed"
    valid_from_statuses = ["in_progress"]
    success_message = gettext_lazy("Maintenance completed.")

    def post(self, request, pk):
        record = get_object_or_404(
            scope_queryset_to_tenant(
                self.model._default_manager.all(), request.user, "aircraft__tenant_id"
            ),
            pk=pk,
            is_active=True,
        )
        if record.status not in self.valid_from_statuses:
            return super().post(request, pk)
        form = MaintenanceCompletionForm(request.POST, instance=record)
        if not form.is_valid():
            return render(
                request,
                "maintenance/record_detail.html",
                {
                    "record": record,
                    "history": record.history.all(),
                    "status_actions": [("complete", _("Complete"), "btn-success")],
                    "completion_form": form,
                },
            )
        with transaction.atomic():
            record._changed_by = request.user.get_username()
            record._changed_by_user = request.user
            record._transition_notes = form.cleaned_data.get("notes", "")
            completed = form.save(commit=False)
            completed.status = self.target_status
            completed.save(
                update_fields=[
                    "completed_date",
                    "performed_by",
                    "notes",
                    "status",
                    "updated_at",
                ]
            )
            # LV-26: completing the maintenance closes its open alert, so the
            # "aircraft needs maintenance" warning does not linger once resolved.
            from apps.compliance.alerts import resolve_open_alerts_for

            resolve_open_alerts_for(completed)
        messages.success(request, self.success_message)
        return redirect(record)


class AircraftReportIncident(ModelPermissionRequiredMixin, View):
    """LV-46: one-click flag for an aircraft that just crashed or was damaged
    and has not yet been formally sent to maintenance.

    Sets the aircraft's own status (the "Mal estado" badge on the list/detail
    pages) and opens an emergency maintenance record in the same click --
    reusing the existing "Mantenciones abiertas" alert rule (LV-26, watches
    maintenance.maintenancerecord/status) so the alert fires on the next
    generate_alerts run without a new rule. No form to fill in first: an
    accident report should not wait on a scheduled date or an assignee.
    """

    model = MaintenanceRecord
    permission_action = "add"

    def post(self, request, pk):
        aircraft = get_object_or_404(
            scope_queryset_to_tenant(Aircraft._default_manager.all(), request.user),
            pk=pk,
            is_active=True,
        )
        aircraft.status = "damaged"
        aircraft.save(update_fields=["status", "updated_at"])
        MaintenanceRecord.objects.create(
            aircraft=aircraft,
            maintenance_type="emergency",
            status="pending",
            description=_(
                "Incident reported from the aircraft fiche. Pending assessment."
            ),
        )
        set_audit_context(request, aircraft, action="incident_reported")
        messages.success(
            request,
            _(
                "Incident logged: aircraft marked as damaged and an emergency "
                "maintenance record was opened."
            ),
        )
        return redirect(reverse("aircraft-detail", kwargs={"pk": aircraft.pk}))


MaintenanceHistoryList = type(
    "MaintenanceHistoryList", (MList,), {"model": MaintenanceHistory}
)
MaintenanceHistoryCreate = type(
    "MaintenanceHistoryCreate", (MCreate,), {"model": MaintenanceHistory}
)
