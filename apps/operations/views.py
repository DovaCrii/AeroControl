from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from django.views.generic import ListView, CreateView
from apps.core.views import SearchMixin
from .models import FlightPermission, FlightRecord
from .forms import FlightPermissionForm, FlightRecordForm


class OList(SearchMixin, LoginRequiredMixin, ListView):
    template_name = "generic/list.html"
    context_object_name = "objects"
    paginate_by = 25

    def get_context_data(self, **kwargs):
        c = super().get_context_data(**kwargs)
        c["title"] = self.model._meta.verbose_name_plural.title()
        return c


class OCreate(LoginRequiredMixin, CreateView):
    template_name = "generic/form.html"

    def get_success_url(self):
        return reverse(f"{self.model._meta.model_name}-list")

    def get_context_data(self, **kwargs):
        c = super().get_context_data(**kwargs)
        c["title"] = f"New {self.model._meta.verbose_name.title()}"
        return c


FlightPermissionList = type("FlightPermissionList", (OList,), {"model": FlightPermission})
FlightPermissionCreate = type("FlightPermissionCreate", (OCreate,), {"model": FlightPermission, "form_class": FlightPermissionForm})
FlightRecordList = type("FlightRecordList", (OList,), {"model": FlightRecord})
FlightRecordCreate = type("FlightRecordCreate", (OCreate,), {"model": FlightRecord, "form_class": FlightRecordForm})
