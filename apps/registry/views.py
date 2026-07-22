import csv
import io

from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils import timezone
from django.views import View
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from apps.core.views import (
    CsvExportMixin,
    HtmxFormMixin,
    ModelPermissionRequiredMixin,
    ModelViewPermissionRequiredMixin,
    SearchMixin,
)
from .models import CostCenter, Aircraft, Operator, Assignment, Qualification
from apps.core.models import ImportBatch
from .forms import (
    CostCenterForm,
    AircraftForm,
    OperatorForm,
    AssignmentForm,
    QualificationForm,
)


class RegistryList(CsvExportMixin, SearchMixin, ModelViewPermissionRequiredMixin, ListView):
    template_name = "generic/list.html"
    context_object_name = "objects"
    paginate_by = 25

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = _(self.model._meta.verbose_name_plural.title())
        return context


class RegistryDetail(ModelViewPermissionRequiredMixin, DetailView):
    template_name = "generic/detail.html"


class RegistryCreate(HtmxFormMixin, ModelPermissionRequiredMixin, CreateView):
    permission_action = "add"
    template_name = "generic/form.html"

    def get_success_url(self):
        model_name = self.model._meta.model_name
        return reverse(f"{model_name}-list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = _("New %(record)s") % {
            "record": _(self.model._meta.verbose_name.title())
        }
        return context


class RegistryUpdate(HtmxFormMixin, ModelPermissionRequiredMixin, UpdateView):
    permission_action = "change"
    template_name = "generic/form.html"

    def get_success_url(self):
        model_name = self.model._meta.model_name
        return reverse(f"{model_name}-list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = _("Edit %(record)s") % {
            "record": _(self.model._meta.verbose_name.title())
        }
        return context


def make_views(model, form, prefix):
    return (
        type(f"{prefix}List", (RegistryList,), {"model": model}),
        type(f"{prefix}Detail", (RegistryDetail,), {"model": model}),
        type(
            f"{prefix}Create", (RegistryCreate,), {"model": model, "form_class": form}
        ),
        type(
            f"{prefix}Update", (RegistryUpdate,), {"model": model, "form_class": form}
        ),
    )


CostCenterList, CostCenterDetail, CostCenterCreate, CostCenterUpdate = make_views(
    CostCenter, CostCenterForm, "CostCenter"
)
AircraftList, AircraftDetail, AircraftCreate, AircraftUpdate = make_views(
    Aircraft, AircraftForm, "Aircraft"
)
OperatorList, OperatorDetail, OperatorCreate, OperatorUpdate = make_views(
    Operator, OperatorForm, "Operator"
)
AssignmentList, AssignmentDetail, AssignmentCreate, AssignmentUpdate = make_views(
    Assignment, AssignmentForm, "Assignment"
)
QualificationList, QualificationDetail, QualificationCreate, QualificationUpdate = (
    make_views(Qualification, QualificationForm, "Qualification")
)


class CostCenterImportView(ModelPermissionRequiredMixin, View):
    model = CostCenter
    permission_action = "add"

    def get(self, request):
        return render(request, "registry/costcenter_import.html", {"rows": [], "errors": []})

    @staticmethod
    def parse(upload):
        if not upload or upload.size > 2 * 1024 * 1024:
            return [], ["El archivo es obligatorio y no puede superar 2 MB."]
        try:
            text = upload.read().decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(text))
        except (UnicodeDecodeError, csv.Error):
            return [], ["El archivo debe ser CSV UTF-8 válido."]
        if reader.fieldnames != ["code", "name"]:
            return [], ["Las columnas deben ser exactamente: code,name."]
        rows, errors, seen = [], [], set()
        for line, raw in enumerate(reader, start=2):
            code, name = (raw.get("code", "").strip(), raw.get("name", "").strip())
            if not code or not name:
                errors.append(f"Línea {line}: code y name son obligatorios.")
            elif code in seen or CostCenter.objects.filter(code=code).exists():
                errors.append(f"Línea {line}: el código {code} está duplicado.")
            else:
                seen.add(code)
                rows.append({"code": code, "name": name})
        if len(rows) > 500:
            errors.append("El máximo por lote es de 500 filas.")
        return rows, errors

    def post(self, request):
        rows, errors = self.parse(request.FILES.get("file"))
        if errors or request.POST.get("apply") != "1":
            return render(request, "registry/costcenter_import.html", {"rows": rows, "errors": errors, "preview": True})
        with transaction.atomic():
            batch = ImportBatch.objects.create(actor=request.user, entity="registry.costcenter", rows=rows)
            created = [CostCenter.objects.create(**row) for row in rows]
            batch.created_ids = [str(obj.pk) for obj in created]
            batch.save(update_fields=["created_ids", "updated_at"])
        return redirect("costcenter-list")


class CostCenterImportRevertView(ModelPermissionRequiredMixin, View):
    model = ImportBatch
    permission_action = "change"

    def post(self, request, pk):
        batch = get_object_or_404(ImportBatch, pk=pk, entity="registry.costcenter", status="applied")
        CostCenter.objects.filter(pk__in=batch.created_ids).update(is_active=False)
        batch.status = "reverted"
        batch.reverted_at = timezone.now()
        batch.save(update_fields=["status", "reverted_at", "updated_at"])
        return HttpResponse(status=204)
