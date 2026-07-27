from django.contrib import messages
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
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
from .models import (
    CostCenter,
    Aircraft,
    AircraftAssignment,
    Operator,
    OperatorAssignment,
    Assignment,
    Qualification,
    ResourceMovementLog,
)
from apps.core.audit import set_audit_context
from apps.core.models import ImportBatch
from apps.core.imports import CsvImportSpec
from .forms import (
    CostCenterForm,
    AircraftForm,
    OperatorForm,
    AssignmentForm,
    OperatorAssignmentForm,
    AircraftAssignmentForm,
    QualificationForm,
)


class RegistryList(
    CsvExportMixin, SearchMixin, ModelViewPermissionRequiredMixin, ListView
):
    template_name = "generic/list.html"
    context_object_name = "objects"
    paginate_by = 25

    page_titles = {
        "costcenter": _("Cost centers"),
        "aircraft": _("Aircraft"),
        "operator": _("Operators"),
        "assignment": _("Resource planning"),
        "operatorassignment": _("Operator assignments"),
        "aircraftassignment": _("Aircraft assignments"),
        "qualification": _("Qualifications"),
    }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = self.page_titles.get(
            self.model._meta.model_name,
            _(self.model._meta.verbose_name_plural.title()),
        )
        return context


class RegistryDetail(ModelViewPermissionRequiredMixin, DetailView):
    template_name = "generic/detail.html"

    def get_context_data(self, **kwargs):
        """Give the detail page its actions.

        It used to offer only `javascript:history.back()`, which does nothing
        when the page is reached from a digest email or a bookmark (and dies
        under an enforcing CSP), and no way to edit or archive: retiring an
        operator or aircraft required the technical admin.
        """
        context = super().get_context_data(**kwargs)
        meta = self.model._meta
        user = self.request.user
        context["list_url"] = reverse(f"{meta.model_name}-list")
        context["update_url"] = reverse(
            f"{meta.model_name}-update", args=[self.object.pk]
        )
        context["archive_url"] = reverse(
            f"{meta.model_name}-archive", args=[self.object.pk]
        )
        context["restore_url"] = reverse(
            f"{meta.model_name}-restore", args=[self.object.pk]
        )
        context["can_change"] = user.has_perm(
            f"{meta.app_label}.change_{meta.model_name}"
        )
        context["can_archive"] = user.has_perm(
            f"{meta.app_label}.delete_{meta.model_name}"
        )
        return context


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


class RegistryArchive(ModelPermissionRequiredMixin, View):
    """Soft-archive an active record (V.30).

    Uses the delete permission because archiving is this project's delete:
    rows are never removed, only hidden (AGENTS.md). The record disappears
    from every active listing and can be restored from the archived filter.
    """

    permission_action = "delete"

    def post(self, request, pk):
        obj = get_object_or_404(self.model, pk=pk, is_active=True)
        obj.is_active = False
        obj.save(update_fields=["is_active", "updated_at"])
        set_audit_context(request, obj, action="archived")
        messages.success(
            request,
            _("%(name)s archived. It can be restored from the archived filter.")
            % {"name": self.model._meta.verbose_name.capitalize()},
        )
        return redirect(f"{self.model._meta.model_name}-list")


class RegistryRestore(ModelPermissionRequiredMixin, View):
    """Bring an archived record back (V.30). The change permission suffices:
    restoring re-activates data that already existed."""

    permission_action = "change"

    def post(self, request, pk):
        obj = get_object_or_404(self.model, pk=pk, is_active=False)
        obj.is_active = True
        obj.save(update_fields=["is_active", "updated_at"])
        set_audit_context(request, obj, action="restored")
        messages.success(
            request,
            _("%(name)s restored.")
            % {"name": self.model._meta.verbose_name.capitalize()},
        )
        return redirect(f"{self.model._meta.model_name}-list")


class CostCenterArchive(RegistryArchive):
    """Archiving a cost center silently drops it from the digest and the
    report (V.31), so it never happens without seeing the dependents first."""

    model = CostCenter

    def post(self, request, pk):
        obj = get_object_or_404(CostCenter, pk=pk, is_active=True)
        dependents = {
            "operators": obj.operators.filter(is_active=True).count(),
            "aircraft": obj.aircraft.filter(is_active=True).count(),
        }
        if any(dependents.values()) and request.POST.get("confirm") != "1":
            return render(
                request,
                "registry/costcenter_archive_confirm.html",
                {"object": obj, "dependents": dependents},
            )
        return super().post(request, pk)


# One archive/restore pair per registry model, same pattern as make_views.
# CostCenterArchive above is the hand-written exception (dependent check).
for _model, _name in (
    (Aircraft, "Aircraft"),
    (Operator, "Operator"),
    (Assignment, "Assignment"),
    (OperatorAssignment, "OperatorAssignment"),
    (AircraftAssignment, "AircraftAssignment"),
    (Qualification, "Qualification"),
):
    globals()[f"{_name}Archive"] = type(
        f"{_name}Archive", (RegistryArchive,), {"model": _model}
    )
for _model, _name in (
    (CostCenter, "CostCenter"),
    (Aircraft, "Aircraft"),
    (Operator, "Operator"),
    (Assignment, "Assignment"),
    (OperatorAssignment, "OperatorAssignment"),
    (AircraftAssignment, "AircraftAssignment"),
    (Qualification, "Qualification"),
):
    globals()[f"{_name}Restore"] = type(
        f"{_name}Restore", (RegistryRestore,), {"model": _model}
    )


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


CostCenterList, _CostCenterAutoDetail, CostCenterCreate, CostCenterUpdate = make_views(
    CostCenter, CostCenterForm, "CostCenter"
)


class CostCenterDetail(RegistryDetail):
    """OPS-2: the contract's own page, with equipment/fleet/permits/documents/
    history as tabs instead of one mixed table (the SIGO screen this mirrors
    dumps every entity's history into a single list; here each stays separate,
    see docs/dev/ops-contract-tracking-plan.md).

    Overrides the make_views()-generated CostCenterDetail above (same name,
    later in module execution order, so the URL wiring in urls.py -- which does
    getattr(views, "CostCenterDetail") -- picks up this richer view).

    Each tab is gated by the permission that already governs its own data (the
    calendar's CALENDAR_EVENT_PERMISSIONS convention): a user missing that
    permission does not get a 403 for the whole page, the tab is simply absent,
    same as a source with no view permission never appearing on the calendar.
    """

    model = CostCenter
    template_name = "registry/costcenter_detail.html"

    def get_context_data(self, **kwargs):
        from django.contrib.contenttypes.models import ContentType

        from apps.compliance.models import Document
        from apps.operations.models import FlightPermission

        from .selectors import movements_for_cost_center

        context = super().get_context_data(**kwargs)
        cost_center = self.object
        user = self.request.user
        today = timezone.localdate()

        if user.has_perm("registry.view_operatorassignment"):
            assignments = list(
                OperatorAssignment.objects.filter(
                    cost_center=cost_center, is_active=True
                )
                .select_related("operator")
                .order_by("operator__full_name")
            )
            expired_operator_ids = set(
                Qualification.objects.filter(
                    operator_id__in=[a.operator_id for a in assignments],
                    expiry_date__lt=today,
                ).values_list("operator_id", flat=True)
            )
            context["operator_assignments"] = assignments
            context["expired_operator_ids"] = expired_operator_ids
        else:
            context["operator_assignments"] = None

        if user.has_perm("registry.view_aircraftassignment"):
            context["aircraft_assignments"] = (
                AircraftAssignment.objects.filter(
                    cost_center=cost_center, is_active=True
                )
                .select_related("aircraft")
                .order_by("aircraft__registration")
            )
        else:
            context["aircraft_assignments"] = None

        if user.has_perm("operations.view_flightpermission"):
            context["flight_permissions"] = FlightPermission.objects.filter(
                cost_center=cost_center, is_active=True
            ).order_by("-valid_from")
        else:
            context["flight_permissions"] = None

        if user.has_perm("compliance.view_document"):
            cc_type = ContentType.objects.get_for_model(CostCenter)
            context["documents"] = Document.objects.filter(
                content_type=cc_type,
                object_id=cost_center.pk,
                is_current_version=True,
                is_active=True,
            ).order_by("-issue_date")
        else:
            context["documents"] = None

        if user.has_perm("registry.view_resourcemovementlog"):
            context["movements"] = movements_for_cost_center(cost_center)
        else:
            context["movements"] = None

        return context


AircraftList, _AircraftAutoDetail, AircraftCreate, AircraftUpdate = make_views(
    Aircraft, AircraftForm, "Aircraft"
)
AircraftList.template_name = "registry/aircraft_list.html"
AircraftList.search_fields = ["registration", "model", "manufacturer"]
OperatorList, _OperatorAutoDetail, OperatorCreate, OperatorUpdate = make_views(
    Operator, OperatorForm, "Operator"
)


class AircraftDetail(RegistryDetail):
    """OPS-6: this aircraft's own movement timeline (cost-center reassignments
    from OPS-1 and location changes from OPS-3 both land in
    ResourceMovementLog, so one query surfaces both kinds)."""

    model = Aircraft
    template_name = "registry/aircraft_detail.html"

    def get_context_data(self, **kwargs):
        from .selectors import movements_for_resource

        context = super().get_context_data(**kwargs)
        if self.request.user.has_perm("registry.view_resourcemovementlog"):
            context["movements"] = movements_for_resource("aircraft", self.object.pk)
        else:
            context["movements"] = None
        return context


class OperatorDetail(RegistryDetail):
    """OPS-6: this operator's own assignment timeline."""

    model = Operator
    template_name = "registry/operator_detail.html"

    def get_context_data(self, **kwargs):
        from .selectors import movements_for_resource

        context = super().get_context_data(**kwargs)
        if self.request.user.has_perm("registry.view_resourcemovementlog"):
            context["movements"] = movements_for_resource("operator", self.object.pk)
        else:
            context["movements"] = None
        return context


class AssignmentList(RegistryList):
    model = Assignment
    template_name = "registry/assignment_list.html"
    search_fields = [
        "operator__full_name",
        "operator__employee_id",
        "aircraft__registration",
        "aircraft__model",
        "cost_center__code",
    ]

    def get_queryset(self):
        from django.db.models import Q
        from apps.core.models import OperationalTenant

        queryset = (
            super().get_queryset().select_related("operator", "aircraft", "cost_center")
        )
        if not self.request.user.is_superuser:
            tenant_ids = OperationalTenant.objects.filter(
                members=self.request.user, is_active=True
            ).values_list("id", flat=True)
            queryset = queryset.filter(
                Q(operator__tenant_id__in=tenant_ids)
                | Q(aircraft__tenant_id__in=tenant_ids)
                | Q(cost_center__tenant_id__in=tenant_ids)
            )
        status = self.request.GET.get("status")
        if status in {"planned", "confirmed", "completed", "cancelled"}:
            queryset = queryset.filter(status=status)
        if self.request.GET.get("review") == "needs_review":
            queryset = queryset.filter(is_active=True, cost_center__isnull=True)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        queryset = self.get_queryset()
        context["assignment_summary"] = {
            "active": queryset.filter(
                is_active=True, status__in=["planned", "confirmed"]
            ).count(),
            "confirmed": queryset.filter(is_active=True, status="confirmed").count(),
            "review": queryset.filter(is_active=True, cost_center__isnull=True).count(),
        }
        return context


AssignmentDetail, AssignmentCreate, AssignmentUpdate = (
    type("AssignmentDetail", (RegistryDetail,), {"model": Assignment}),
    type(
        "AssignmentCreate",
        (RegistryCreate,),
        {"model": Assignment, "form_class": AssignmentForm},
    ),
    type(
        "AssignmentUpdate",
        (RegistryUpdate,),
        {"model": Assignment, "form_class": AssignmentForm},
    ),
)


class OperatorAssignmentList(RegistryList):
    """OPS-1: an operator anchored to a cost center over a period."""

    model = OperatorAssignment
    search_fields = [
        "operator__full_name",
        "operator__employee_id",
        "cost_center__code",
    ]

    def get_queryset(self):
        return super().get_queryset().select_related("operator", "cost_center")


class AircraftAssignmentList(RegistryList):
    """OPS-1: an aircraft anchored to a cost center over a period."""

    model = AircraftAssignment
    search_fields = ["aircraft__registration", "aircraft__model", "cost_center__code"]

    def get_queryset(self):
        return super().get_queryset().select_related("aircraft", "cost_center")


OperatorAssignmentDetail, OperatorAssignmentCreate, OperatorAssignmentUpdate = (
    type("OperatorAssignmentDetail", (RegistryDetail,), {"model": OperatorAssignment}),
    type(
        "OperatorAssignmentCreate",
        (RegistryCreate,),
        {"model": OperatorAssignment, "form_class": OperatorAssignmentForm},
    ),
    type(
        "OperatorAssignmentUpdate",
        (RegistryUpdate,),
        {"model": OperatorAssignment, "form_class": OperatorAssignmentForm},
    ),
)
AircraftAssignmentDetail, AircraftAssignmentCreate, AircraftAssignmentUpdate = (
    type("AircraftAssignmentDetail", (RegistryDetail,), {"model": AircraftAssignment}),
    type(
        "AircraftAssignmentCreate",
        (RegistryCreate,),
        {"model": AircraftAssignment, "form_class": AircraftAssignmentForm},
    ),
    type(
        "AircraftAssignmentUpdate",
        (RegistryUpdate,),
        {"model": AircraftAssignment, "form_class": AircraftAssignmentForm},
    ),
)


class ResourceMovementLogList(ModelViewPermissionRequiredMixin, ListView):
    """OPS-1: the read-only movement trail -- never a create/edit surface.

    resource_id is a bare UUID (it can point at an Operator or an Aircraft
    depending on resource_kind), so this resolves a display label per row
    instead of asking the template to know which model to look up.
    """

    model = ResourceMovementLog
    template_name = "registry/resourcemovementlog_list.html"
    context_object_name = "objects"
    paginate_by = 50

    def get_queryset(self):
        queryset = (
            super()
            .get_queryset()
            .select_related("from_cost_center", "to_cost_center", "changed_by_user")
        )
        kind = self.request.GET.get("resource_kind")
        if kind in {"operator", "aircraft"}:
            queryset = queryset.filter(resource_kind=kind)
        return queryset

    def get_context_data(self, **kwargs):
        from .selectors import label_movements

        context = super().get_context_data(**kwargs)
        context["title"] = _("Resource movements")
        context["selected_kind"] = self.request.GET.get("resource_kind", "")
        context["objects"] = label_movements(context["objects"])
        return context


QualificationList, QualificationDetail, QualificationCreate, QualificationUpdate = (
    make_views(Qualification, QualificationForm, "Qualification")
)


class CostCenterImportView(ModelPermissionRequiredMixin, View):
    model = CostCenter
    permission_action = "add"
    entity_key = "registry.costcenter"

    def last_applied_batch(self):
        """Most recent applied batch of this entity, for the revert offer."""
        return (
            ImportBatch.objects.filter(entity=self.entity_key, status="applied")
            .order_by("-created_at")
            .first()
        )

    def _apply_feedback(self, request, created_count):
        # Applying used to redirect with no confirmation, and the revert that
        # exists precisely for this batch was linked nowhere in the UI.
        messages.success(
            request,
            _("%(count)s %(name)s imported. You can undo this from the import page.")
            % {
                "count": created_count,
                "name": self.model._meta.verbose_name_plural,
            },
        )

    def get(self, request):
        if request.GET.get("template") == "1":
            response = HttpResponse(
                "code,name\r\n", content_type="text/csv; charset=utf-8"
            )
            response["Content-Disposition"] = (
                'attachment; filename="cost-centers-template.csv"'
            )
            return response
        return render(
            request,
            "registry/costcenter_import.html",
            {"rows": [], "errors": [], "last_batch": self.last_applied_batch()},
        )

    @staticmethod
    def parse(upload):
        spec = CsvImportSpec(("code", "name"), "code")
        existing = set(CostCenter.objects.values_list("code", flat=True))
        return spec.parse(
            upload,
            existing,
            lambda raw, _line: {
                "code": raw["code"].strip(),
                "name": raw["name"].strip(),
            }
            if raw["name"].strip()
            else "code y name son obligatorios.",
        )

    def post(self, request):
        rows, errors = self.parse(request.FILES.get("file"))
        if errors or request.POST.get("apply") != "1":
            return render(
                request,
                "registry/costcenter_import.html",
                {"rows": rows, "errors": errors, "preview": True},
            )
        with transaction.atomic():
            batch = ImportBatch.objects.create(
                actor=request.user, entity="registry.costcenter", rows=rows
            )
            created = [CostCenter.objects.create(**row) for row in rows]
            batch.created_ids = [str(obj.pk) for obj in created]
            batch.save(update_fields=["created_ids", "updated_at"])
        self._apply_feedback(request, len(created))
        return redirect("costcenter-list")


class CostCenterImportRevertView(ModelPermissionRequiredMixin, View):
    model = ImportBatch
    permission_action = "change"

    def post(self, request, pk):
        with transaction.atomic():
            batch = get_object_or_404(
                ImportBatch.objects.select_for_update(),
                pk=pk,
                entity__in=[
                    "registry.costcenter",
                    "registry.aircraft",
                    "registry.operator",
                ],
                status="applied",
            )
            model = {
                "registry.costcenter": CostCenter,
                "registry.aircraft": Aircraft,
                "registry.operator": Operator,
            }[batch.entity]
            model.objects.filter(pk__in=batch.created_ids).update(is_active=False)
            batch.status = "reverted"
            batch.reverted_at = timezone.now()
            batch.save(update_fields=["status", "reverted_at", "updated_at"])
        # A browser does nothing with a 204, so the form on the import page
        # appeared to have no effect. Non-HTMX callers get a redirect with a
        # message instead.
        if request.headers.get("HX-Request") == "true":
            return HttpResponse(status=204)
        messages.success(
            request,
            _("%(count)s imported records archived.")
            % {"count": len(batch.created_ids)},
        )
        referer = request.META.get("HTTP_REFERER", "")
        if referer and url_has_allowed_host_and_scheme(
            referer,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(referer)
        return redirect("costcenter-list")


class AircraftImportView(CostCenterImportView):
    model = Aircraft
    entity_key = "registry.aircraft"

    def get(self, request):
        if request.GET.get("template") == "1":
            response = HttpResponse(
                "registration,type,model,manufacturer,year,cost_center,status\r\n",
                content_type="text/csv; charset=utf-8",
            )
            response["Content-Disposition"] = (
                'attachment; filename="aircraft-template.csv"'
            )
            return response
        return render(
            request,
            "registry/costcenter_import.html",
            {
                "rows": [],
                "errors": [],
                "entity": "aircraft",
                "last_batch": self.last_applied_batch(),
            },
        )

    @staticmethod
    def parse(upload):
        spec = CsvImportSpec(
            (
                "registration",
                "type",
                "model",
                "manufacturer",
                "year",
                "cost_center",
                "status",
            ),
            "registration",
        )
        existing = set(Aircraft.objects.values_list("registration", flat=True))
        centers = dict(
            CostCenter.objects.filter(is_active=True).values_list("code", "pk")
        )

        def build(raw, _line):
            center = centers.get(raw["cost_center"].strip())
            if not center:
                return "centro de costo inexistente."
            return {
                "registration": raw["registration"].strip(),
                "type": raw["type"].strip(),
                "model": raw["model"].strip(),
                "manufacturer": raw["manufacturer"].strip(),
                "year": int(raw["year"]) if raw["year"].strip().isdigit() else None,
                "cost_center_id": str(center),
                "status": raw["status"].strip() or "active",
            }

        return spec.parse(upload, existing, build)

    def post(self, request):
        rows, errors = self.parse(request.FILES.get("file"))
        if errors or request.POST.get("apply") != "1":
            return render(
                request,
                "registry/costcenter_import.html",
                {"rows": rows, "errors": errors, "preview": True, "entity": "aircraft"},
            )
        with transaction.atomic():
            batch = ImportBatch.objects.create(
                actor=request.user, entity="registry.aircraft", rows=rows
            )
            created = [Aircraft.objects.create(**row) for row in rows]
            batch.created_ids = [str(obj.pk) for obj in created]
            batch.save(update_fields=["created_ids", "updated_at"])
        self._apply_feedback(request, len(created))
        return redirect("aircraft-list")


class OperatorImportView(CostCenterImportView):
    model = Operator
    entity_key = "registry.operator"

    def get(self, request):
        if request.GET.get("template") == "1":
            response = HttpResponse(
                "employee_id,full_name,email,phone,cost_center\r\n",
                content_type="text/csv; charset=utf-8",
            )
            response["Content-Disposition"] = (
                'attachment; filename="operators-template.csv"'
            )
            return response
        return render(
            request,
            "registry/costcenter_import.html",
            {
                "rows": [],
                "errors": [],
                "entity": "operator",
                "last_batch": self.last_applied_batch(),
            },
        )

    @staticmethod
    def parse(upload):
        spec = CsvImportSpec(
            ("employee_id", "full_name", "email", "phone", "cost_center"), "employee_id"
        )
        existing = set(Operator.objects.values_list("employee_id", flat=True))
        centers = dict(
            CostCenter.objects.filter(is_active=True).values_list("code", "pk")
        )

        def build(raw, _line):
            if not raw["full_name"].strip():
                return "full_name es obligatorio."
            center = centers.get(raw["cost_center"].strip())
            if not center:
                return "centro de costo inexistente."
            return {
                "employee_id": raw["employee_id"].strip(),
                "full_name": raw["full_name"].strip(),
                "email": raw["email"].strip(),
                "phone": raw["phone"].strip(),
                "cost_center_id": str(center),
            }

        return spec.parse(upload, existing, build)

    def post(self, request):
        rows, errors = self.parse(request.FILES.get("file"))
        if errors or request.POST.get("apply") != "1":
            return render(
                request,
                "registry/costcenter_import.html",
                {"rows": rows, "errors": errors, "preview": True, "entity": "operator"},
            )
        with transaction.atomic():
            batch = ImportBatch.objects.create(
                actor=request.user, entity="registry.operator", rows=rows
            )
            created = [Operator.objects.create(**row) for row in rows]
            batch.created_ids = [str(obj.pk) for obj in created]
            batch.save(update_fields=["created_ids", "updated_at"])
        self._apply_feedback(request, len(created))
        return redirect("operator-list")
