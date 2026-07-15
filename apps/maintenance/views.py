from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import CreateView, DetailView, ListView

from apps.core.views import SearchMixin, StatusTransitionView
from .forms import MaintenanceCompletionForm, MaintenanceRecordForm
from .models import MaintenanceHistory, MaintenanceRecord


class MList(SearchMixin, LoginRequiredMixin, ListView):
    template_name = "generic/list.html"
    context_object_name = "objects"
    paginate_by = 25

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = self.model._meta.verbose_name_plural.title()
        return context


class MCreate(LoginRequiredMixin, CreateView):
    template_name = "generic/form.html"

    def get_success_url(self):
        return reverse("maintenance-list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = f"New {self.model._meta.verbose_name.title()}"
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


class MaintenanceRecordDetail(LoginRequiredMixin, DetailView):
    model = MaintenanceRecord
    template_name = "maintenance/record_detail.html"
    context_object_name = "record"

    def get_queryset(self):
        return super().get_queryset().filter(is_active=True).select_related("aircraft")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["history"] = self.object.history.all()
        context["completion_form"] = MaintenanceCompletionForm(instance=self.object)
        context["status_actions"] = (
            [("start", "Start Maintenance", "btn-warning")]
            if self.object.status == "pending"
            else [("complete", "Complete", "btn-success")]
            if self.object.status == "in_progress"
            else []
        )
        return context


class MaintenanceStart(StatusTransitionView):
    model = MaintenanceRecord
    target_status = "in_progress"
    valid_from_statuses = ["pending"]
    success_message = "Maintenance started."


class MaintenanceComplete(StatusTransitionView):
    model = MaintenanceRecord
    target_status = "completed"
    valid_from_statuses = ["in_progress"]
    success_message = "Maintenance completed."

    def post(self, request, pk):
        record = get_object_or_404(self.model, pk=pk, is_active=True)
        if record.status not in self.valid_from_statuses:
            return super().post(request, pk)
        form = MaintenanceCompletionForm(request.POST, instance=record)
        if not form.is_valid():
            return render(request, "maintenance/record_detail.html", {
                "record": record,
                "history": record.history.all(),
                "status_actions": [("complete", "Complete", "btn-success")],
                "completion_form": form,
            })
        record._changed_by = request.user.get_username()
        record._transition_notes = form.cleaned_data.get("notes", "")
        completed = form.save(commit=False)
        completed.status = self.target_status
        completed.save(update_fields=["completed_date", "performed_by", "cost", "notes", "status", "updated_at"])
        messages.success(request, self.success_message)
        return redirect(record)


MaintenanceHistoryList = type("MaintenanceHistoryList", (MList,), {"model": MaintenanceHistory})
MaintenanceHistoryCreate = type("MaintenanceHistoryCreate", (MCreate,), {"model": MaintenanceHistory})
