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
from apps.core.imports import CsvImportSpec
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
        if request.GET.get("template") == "1":
            response = HttpResponse("code,name\r\n", content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = 'attachment; filename="cost-centers-template.csv"'
            return response
        return render(request, "registry/costcenter_import.html", {"rows": [], "errors": []})

    @staticmethod
    def parse(upload):
        spec = CsvImportSpec(("code", "name"), "code")
        existing = set(CostCenter.objects.values_list("code", flat=True))
        return spec.parse(
            upload,
            existing,
            lambda raw, _line: {"code": raw["code"].strip(), "name": raw["name"].strip()}
            if raw["name"].strip()
            else "code y name son obligatorios.",
        )

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
        with transaction.atomic():
            batch = get_object_or_404(
                ImportBatch.objects.select_for_update(),
                pk=pk,
                entity__in=["registry.costcenter", "registry.aircraft", "registry.operator"],
                status="applied",
            )
            model = {"registry.costcenter": CostCenter, "registry.aircraft": Aircraft, "registry.operator": Operator}[batch.entity]
            model.objects.filter(pk__in=batch.created_ids).update(is_active=False)
            batch.status = "reverted"
            batch.reverted_at = timezone.now()
            batch.save(update_fields=["status", "reverted_at", "updated_at"])
        return HttpResponse(status=204)


class AircraftImportView(CostCenterImportView):
    model = Aircraft

    def get(self, request):
        if request.GET.get("template") == "1":
            response = HttpResponse("registration,type,model,manufacturer,year,cost_center,status\r\n", content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = 'attachment; filename="aircraft-template.csv"'
            return response
        return render(request, "registry/costcenter_import.html", {"rows": [], "errors": [], "entity": "aircraft"})

    @staticmethod
    def parse(upload):
        spec = CsvImportSpec(("registration", "type", "model", "manufacturer", "year", "cost_center", "status"), "registration")
        existing = set(Aircraft.objects.values_list("registration", flat=True))
        centers = dict(CostCenter.objects.filter(is_active=True).values_list("code", "pk"))
        def build(raw, _line):
            center = centers.get(raw["cost_center"].strip())
            if not center:
                return "centro de costo inexistente."
            return {"registration": raw["registration"].strip(), "type": raw["type"].strip(), "model": raw["model"].strip(), "manufacturer": raw["manufacturer"].strip(), "year": int(raw["year"]) if raw["year"].strip().isdigit() else None, "cost_center_id": str(center), "status": raw["status"].strip() or "active"}
        return spec.parse(upload, existing, build)

    def post(self, request):
        rows, errors = self.parse(request.FILES.get("file"))
        if errors or request.POST.get("apply") != "1":
            return render(request, "registry/costcenter_import.html", {"rows": rows, "errors": errors, "preview": True, "entity": "aircraft"})
        with transaction.atomic():
            batch = ImportBatch.objects.create(actor=request.user, entity="registry.aircraft", rows=rows)
            created = [Aircraft.objects.create(**row) for row in rows]
            batch.created_ids = [str(obj.pk) for obj in created]
            batch.save(update_fields=["created_ids", "updated_at"])
        return redirect("aircraft-list")


class OperatorImportView(CostCenterImportView):
    model = Operator

    def get(self, request):
        if request.GET.get("template") == "1":
            response = HttpResponse("employee_id,full_name,email,phone,cost_center\r\n", content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = 'attachment; filename="operators-template.csv"'
            return response
        return render(request, "registry/costcenter_import.html", {"rows": [], "errors": [], "entity": "operator"})

    @staticmethod
    def parse(upload):
        spec = CsvImportSpec(("employee_id", "full_name", "email", "phone", "cost_center"), "employee_id")
        existing = set(Operator.objects.values_list("employee_id", flat=True))
        centers = dict(CostCenter.objects.filter(is_active=True).values_list("code", "pk"))
        def build(raw, _line):
            if not raw["full_name"].strip():
                return "full_name es obligatorio."
            center = centers.get(raw["cost_center"].strip())
            if not center:
                return "centro de costo inexistente."
            return {"employee_id": raw["employee_id"].strip(), "full_name": raw["full_name"].strip(), "email": raw["email"].strip(), "phone": raw["phone"].strip(), "cost_center_id": str(center)}
        return spec.parse(upload, existing, build)

    def post(self, request):
        rows, errors = self.parse(request.FILES.get("file"))
        if errors or request.POST.get("apply") != "1":
            return render(request, "registry/costcenter_import.html", {"rows": rows, "errors": errors, "preview": True, "entity": "operator"})
        with transaction.atomic():
            batch = ImportBatch.objects.create(actor=request.user, entity="registry.operator", rows=rows)
            created = [Operator.objects.create(**row) for row in rows]
            batch.created_ids = [str(obj.pk) for obj in created]
            batch.save(update_fields=["created_ids", "updated_at"])
        return redirect("operator-list")
