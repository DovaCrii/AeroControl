from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from django.views.generic import ListView, CreateView
from .models import DocumentType, Document, AlertRule, Alert
from .forms import DocumentTypeForm, DocumentForm, AlertRuleForm, AlertForm


class ComplianceList(LoginRequiredMixin, ListView):
    template_name = "generic/list.html"
    context_object_name = "objects"
    paginate_by = 25

    def get_context_data(self, **kwargs):
        c = super().get_context_data(**kwargs)
        c["title"] = self.model._meta.verbose_name_plural.title()
        return c


class ComplianceCreate(LoginRequiredMixin, CreateView):
    template_name = "generic/form.html"

    def get_success_url(self):
        return reverse(f"{self.model._meta.model_name}-list")

    def get_context_data(self, **kwargs):
        c = super().get_context_data(**kwargs)
        c["title"] = f"New {self.model._meta.verbose_name.title()}"
        return c


for model, form, name in (
    (DocumentType, DocumentTypeForm, "DocumentType"),
    (Document, DocumentForm, "Document"),
    (AlertRule, AlertRuleForm, "AlertRule"),
    (Alert, AlertForm, "Alert"),
):
    globals()[f"{name}List"] = type(f"{name}List", (ComplianceList,), {"model": model})
    globals()[f"{name}Create"] = type(f"{name}Create", (ComplianceCreate,), {"model": model, "form_class": form})
