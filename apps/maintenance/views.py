from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from django.views.generic import ListView, CreateView
from .models import MaintenanceRecord, MaintenanceHistory
from .forms import MaintenanceRecordForm, MaintenanceHistoryForm


class MList(LoginRequiredMixin, ListView):
    template_name = "generic/list.html"
    context_object_name = "objects"
    paginate_by = 25

    def get_context_data(self, **kwargs):
        c = super().get_context_data(**kwargs)
        c["title"] = self.model._meta.verbose_name_plural.title()
        return c


class MCreate(LoginRequiredMixin, CreateView):
    template_name = "generic/form.html"

    def get_success_url(self):
        return reverse(f"{self.model._meta.model_name}-list")

    def get_context_data(self, **kwargs):
        c = super().get_context_data(**kwargs)
        c["title"] = f"New {self.model._meta.verbose_name.title()}"
        return c


MaintenanceRecordList = type("MaintenanceRecordList", (MList,), {"model": MaintenanceRecord})
MaintenanceRecordCreate = type("MaintenanceRecordCreate", (MCreate,), {"model": MaintenanceRecord, "form_class": MaintenanceRecordForm})
MaintenanceHistoryList = type("MaintenanceHistoryList", (MList,), {"model": MaintenanceHistory})
MaintenanceHistoryCreate = type("MaintenanceHistoryCreate", (MCreate,), {"model": MaintenanceHistory, "form_class": MaintenanceHistoryForm})
