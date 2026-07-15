from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse, reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from apps.core.views import HtmxFormMixin, SearchMixin
from .models import CostCenter, Aircraft, Operator, Assignment, Qualification
from .forms import CostCenterForm, AircraftForm, OperatorForm, AssignmentForm, QualificationForm


class RegistryList(SearchMixin, LoginRequiredMixin, ListView):
    template_name = "generic/list.html"
    context_object_name = "objects"
    paginate_by = 25

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = self.model._meta.verbose_name_plural.title()
        return context


class RegistryDetail(LoginRequiredMixin, DetailView):
    template_name = "generic/detail.html"


class RegistryCreate(HtmxFormMixin, LoginRequiredMixin, CreateView):
    template_name = "generic/form.html"

    def get_success_url(self):
        model_name = self.model._meta.model_name
        return reverse(f"{model_name}-list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = f"New {self.model._meta.verbose_name.title()}"
        return context


class RegistryUpdate(HtmxFormMixin, LoginRequiredMixin, UpdateView):
    template_name = "generic/form.html"

    def get_success_url(self):
        model_name = self.model._meta.model_name
        return reverse(f"{model_name}-list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = f"Edit {self.model._meta.verbose_name.title()}"
        return context


def make_views(model, form, prefix):
    return (
        type(f"{prefix}List", (RegistryList,), {"model": model}),
        type(f"{prefix}Detail", (RegistryDetail,), {"model": model}),
        type(f"{prefix}Create", (RegistryCreate,), {"model": model, "form_class": form}),
        type(f"{prefix}Update", (RegistryUpdate,), {"model": model, "form_class": form}),
    )


CostCenterList, CostCenterDetail, CostCenterCreate, CostCenterUpdate = make_views(CostCenter, CostCenterForm, "CostCenter")
AircraftList, AircraftDetail, AircraftCreate, AircraftUpdate = make_views(Aircraft, AircraftForm, "Aircraft")
OperatorList, OperatorDetail, OperatorCreate, OperatorUpdate = make_views(Operator, OperatorForm, "Operator")
AssignmentList, AssignmentDetail, AssignmentCreate, AssignmentUpdate = make_views(Assignment, AssignmentForm, "Assignment")
QualificationList, QualificationDetail, QualificationCreate, QualificationUpdate = make_views(Qualification, QualificationForm, "Qualification")
