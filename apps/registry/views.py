from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.db.models.functions import Length
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.utils import timezone
from django.views import View
from django.views.generic import ListView, DetailView, CreateView, UpdateView, FormView
from apps.core.views import (
    CsvExportMixin,
    HtmxFormMixin,
    ModelPermissionRequiredMixin,
    ModelViewPermissionRequiredMixin,
    SearchMixin,
    TenantScopedQuerysetMixin,
)
from .models import (
    CostCenter,
    Aircraft,
    AircraftAssignment,
    Operator,
    OperatorAssignment,
    Assignment,
    Qualification,
    QualificationType,
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
    OperatorBulkAssignForm,
    AircraftAssignmentForm,
    QualificationForm,
    QualificationTypeForm,
)
from .services import bulk_assign_operators


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

    def scope_by_tenant(self, queryset, field="tenant_id"):
        """T3.2 Fase 2: restrict a list to the user's tenant(s).

        Only for models with a direct `tenant` FK (CostCenter/Operator/Aircraft);
        lists that scope through a relation (the assignment list, via the cost
        center) filter themselves. `None` (superuser) means no restriction.
        """
        from apps.core.tenancy import visible_tenant_ids

        tenant_ids = visible_tenant_ids(self.request.user)
        if tenant_ids is not None:
            queryset = queryset.filter(**{f"{field}__in": tenant_ids})
        return queryset


class RegistryDetail(
    TenantScopedQuerysetMixin, ModelViewPermissionRequiredMixin, DetailView
):
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

    def form_valid(self, form):
        # R5.2: apps/registry/signals.py logs a ResourceMovementLog on every
        # AircraftAssignment/OperatorAssignment save and every Aircraft
        # location change, attributed to `instance._changed_by_user` when
        # set. Only bulk_assign_operators (services.py) was setting it --
        # every plain CRUD save through this base view left it blank, so a
        # movement created or edited from the ordinary form had no author.
        form.instance._changed_by_user = self.request.user
        return super().form_valid(form)


class RegistryUpdate(
    TenantScopedQuerysetMixin, HtmxFormMixin, ModelPermissionRequiredMixin, UpdateView
):
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

    def form_valid(self, form):
        # R5.2: see RegistryCreate.form_valid above -- same gap on update
        # (an edited AircraftAssignment/OperatorAssignment, or an Aircraft
        # whose current_location changed through the ordinary edit form).
        form.instance._changed_by_user = self.request.user
        return super().form_valid(form)


class RegistryArchive(ModelPermissionRequiredMixin, View):
    """Soft-archive an active record (V.30).

    Uses the delete permission because archiving is this project's delete:
    rows are never removed, only hidden (AGENTS.md). The record disappears
    from every active listing and can be restored from the archived filter.
    """

    permission_action = "delete"

    def post(self, request, pk):
        from apps.core.tenancy import scope_queryset_to_tenant

        obj = get_object_or_404(
            scope_queryset_to_tenant(self.model._default_manager.all(), request.user),
            pk=pk,
            is_active=True,
        )
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
        from apps.core.tenancy import scope_queryset_to_tenant

        obj = get_object_or_404(
            scope_queryset_to_tenant(self.model._default_manager.all(), request.user),
            pk=pk,
            is_active=False,
        )
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


_CostCenterAutoList, _CostCenterAutoDetail, CostCenterCreate, CostCenterUpdate = (
    make_views(CostCenter, CostCenterForm, "CostCenter")
)
# LV-36: the cost-center form is grouped into labelled sections (Identification
# / Responsible / Notes) instead of one flat list. Both entry points are
# covered: full page (Edit from the detail) and HTMX modal (Edit from the list).
for _cc_view in (CostCenterCreate, CostCenterUpdate):
    _cc_view.template_name = "registry/costcenter_form.html"
    _cc_view.htmx_template_name = "registry/_costcenter_form_content.html"


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
        from apps.compliance.attachments import attached_documents_context
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
            # LV-33: when operators were linked by cost_center directly (a bulk
            # import that never ran backfill_resource_assignments), there are no
            # assignment rows and the tab was empty though the contract has a
            # team. Fall back to those operators as in-memory assignments -- same
            # template interface, no fabricated DB rows.
            if not assignments:
                assignments = [
                    OperatorAssignment(
                        operator=operator, cost_center=cost_center, status="active"
                    )
                    for operator in Operator.objects.filter(
                        cost_center=cost_center, is_active=True
                    ).order_by("full_name")
                ]
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
            aircraft_assignments = list(
                AircraftAssignment.objects.filter(
                    cost_center=cost_center, is_active=True
                )
                .select_related("aircraft")
                .order_by("aircraft__registration")
            )
            if not aircraft_assignments:
                # LV-33: same fallback for the fleet tab.
                aircraft_assignments = [
                    AircraftAssignment(
                        aircraft=aircraft, cost_center=cost_center, status="active"
                    )
                    for aircraft in Aircraft.objects.filter(
                        cost_center=cost_center, is_active=True
                    ).order_by("registration")
                ]
            context["aircraft_assignments"] = aircraft_assignments
        else:
            context["aircraft_assignments"] = None

        if user.has_perm("operations.view_flightpermission"):
            context["flight_permissions"] = FlightPermission.objects.filter(
                cost_center=cost_center, is_active=True
            ).order_by("-valid_from")
        else:
            context["flight_permissions"] = None

        context.update(attached_documents_context(user, cost_center))

        if user.has_perm("registry.view_resourcemovementlog"):
            context["movements"] = movements_for_cost_center(cost_center)
        else:
            context["movements"] = None

        return context


_AircraftAutoList, _AircraftAutoDetail, AircraftCreate, AircraftUpdate = make_views(
    Aircraft, AircraftForm, "Aircraft"
)
_OperatorAutoList, _OperatorAutoDetail, OperatorCreate, OperatorUpdate = make_views(
    Operator, OperatorForm, "Operator"
)


class OperatorList(RegistryList):
    """LV-9: a useful operator list instead of Name/Created/Status.

    Shows RUT, DGAC credential, cost center and a qualification badge
    (current / expired), all resolved in one annotated query.
    """

    model = Operator
    template_name = "registry/operator_list.html"
    # T5.6/F-13: the live-search/pagination partial must carry this list's own
    # columns, or an HTMX search collapsed them to the generic Name/Created/Status.
    htmx_template_name = "registry/_operator_rows.html"
    search_fields = ["full_name", "employee_id", "rut", "dgac_credential"]

    def get_queryset(self):
        today = timezone.localdate()
        return self.scope_by_tenant(
            super()
            .get_queryset()
            .select_related("cost_center")
            .annotate(
                current_quals=Count(
                    "qualifications",
                    filter=Q(qualifications__is_active=True)
                    & (
                        Q(qualifications__expiry_date__isnull=True)
                        | Q(qualifications__expiry_date__gte=today)
                    ),
                    distinct=True,
                ),
                expired_quals=Count(
                    "qualifications",
                    filter=Q(
                        qualifications__is_active=True,
                        qualifications__expiry_date__lt=today,
                    ),
                    distinct=True,
                ),
            )
            # R3.2: no Meta.ordering fell back to created_at (SearchMixin's
            # fallback), i.e. insertion order -- alphabetical by full name.
            .order_by("full_name")
        )


class CostCenterList(RegistryList):
    """LV-9: contract-oriented columns (administrator, assigned resources)
    instead of Name/Created/Status. Counts annotated in one query."""

    model = CostCenter
    template_name = "registry/costcenter_list.html"
    htmx_template_name = "registry/_costcenter_rows.html"
    search_fields = ["code", "name", "responsible"]

    def get_queryset(self):
        return self.scope_by_tenant(
            super()
            .get_queryset()
            # LV-58: day_to_day_contact reads responsible_operator per row.
            .select_related("responsible_operator")
            .annotate(
                operator_count=Count(
                    "operators", filter=Q(operators__is_active=True), distinct=True
                ),
                aircraft_count=Count(
                    "aircraft", filter=Q(aircraft__is_active=True), distinct=True
                ),
            )
            # R3.2: `code` is a CharField, so plain alphabetical sorting puts
            # "CC110" before "CC2" -- ordering by length first groups codes
            # with the same digit count together, which sorts a same-prefix
            # numeric series (CC1, CC2, ..., CC99, CC100, CC110, ...)
            # correctly without a DB-specific regex/substring function.
            # R3.3(b): "contract_status" first so closed cost centers group
            # after the active ones instead of interleaving with them --
            # "active" < "closed" alphabetically already gives that order.
            .order_by("contract_status", Length("code"), "code")
        )


class AircraftList(RegistryList):
    """LV-4 / LV-29: surface each aircraft's JAC insurance expiry as a column.

    LV-29 made `insurance_expiry` a real field on Aircraft (the user enters it
    from the DGAC/SIGO capture), so this no longer derives the date from an
    is_insurance Document -- the field is the canonical source, and
    `insurance_is_overdue` is a model property. The supporting file may still
    be attached as a document, but the column reads the field.
    """

    model = Aircraft
    template_name = "registry/aircraft_list.html"
    htmx_template_name = "registry/_aircraft_rows.html"
    search_fields = ["registration", "model", "manufacturer"]

    def get_queryset(self):
        # R3.2: no Meta.ordering fell back to created_at.
        return self.scope_by_tenant(super().get_queryset()).order_by("registration")


class AircraftDetail(RegistryDetail):
    """OPS-6/R5.4: the aircraft fiche as expediente -- documents, movement
    timeline (cost-center reassignments from OPS-1 and location changes from
    OPS-3 both land in ResourceMovementLog, so one query surfaces both
    kinds), maintenance (open and historical) and cumulative flight hours,
    all on the one page instead of scattered across separate lists."""

    model = Aircraft
    template_name = "registry/aircraft_detail.html"

    def get_context_data(self, **kwargs):
        from apps.compliance.attachments import attached_documents_context

        from .selectors import movements_for_resource

        context = super().get_context_data(**kwargs)
        if self.request.user.has_perm("registry.view_resourcemovementlog"):
            context["movements"] = movements_for_resource("aircraft", self.object.pk)
        else:
            context["movements"] = None
        context.update(attached_documents_context(self.request.user, self.object))
        # LV-26: open maintenance for this aircraft, so the detail shows "this
        # M300 is due for / in maintenance" until it is resolved.
        if self.request.user.has_perm("maintenance.view_maintenancerecord"):
            from apps.maintenance.models import MaintenanceRecord

            context["open_maintenance"] = MaintenanceRecord.objects.filter(
                aircraft=self.object,
                is_active=True,
                status__in=["pending", "in_progress"],
            ).order_by("scheduled_date")
            # R5.4: the completed side of the same record set -- open_maintenance
            # above already covers "due for/in maintenance", so this is
            # deliberately just the closed ones, not the full unfiltered set,
            # to avoid showing every open record twice on the same page.
            context["maintenance_history"] = MaintenanceRecord.objects.filter(
                aircraft=self.object, is_active=True, status="completed"
            ).order_by("-completed_date")[:20]
        else:
            context["open_maintenance"] = None
            context["maintenance_history"] = None
        # R5.4/R7.1: cumulative flight time -- FlightRecord.duration is a
        # property (departure/arrival + midnight-crossing), not a DB column,
        # so this sums in Python; fine at one-aircraft scale.
        if self.request.user.has_perm("operations.view_flightrecord"):
            from apps.operations.selectors import (
                format_duration,
                total_flight_duration,
            )

            context["total_flight_hours"] = format_duration(
                total_flight_duration(self.object)
            )
        else:
            context["total_flight_hours"] = None
        return context


class OperatorDetail(RegistryDetail):
    """OPS-6: this operator's own assignment timeline."""

    model = Operator
    template_name = "registry/operator_detail.html"

    def get_context_data(self, **kwargs):
        from apps.compliance.attachments import attached_documents_context

        from .selectors import movements_for_resource

        context = super().get_context_data(**kwargs)
        if self.request.user.has_perm("registry.view_resourcemovementlog"):
            context["movements"] = movements_for_resource("operator", self.object.pk)
        else:
            context["movements"] = None
        context.update(attached_documents_context(self.request.user, self.object))
        return context


class AssignmentList(RegistryList):
    model = Assignment
    template_name = "registry/assignment_list.html"
    htmx_template_name = "registry/_assignment_table_body.html"
    search_fields = [
        "operator__full_name",
        "operator__employee_id",
        "aircraft__registration",
        "aircraft__model",
        "cost_center__code",
    ]

    def get_queryset(self):
        from django.db.models import Q
        from apps.core.tenancy import visible_tenant_ids

        queryset = (
            super().get_queryset().select_related("operator", "aircraft", "cost_center")
        )
        # T3.2 Fase 1/2: shared tenant resolution + canonical scope by the cost
        # center's tenant (operator fallback only when the legacy Assignment has
        # no cost center), instead of the OR-any-FK that leaked across tenants.
        tenant_ids = visible_tenant_ids(self.request.user)
        if tenant_ids is not None:
            queryset = queryset.filter(
                Q(cost_center__tenant_id__in=tenant_ids)
                | Q(cost_center__isnull=True, operator__tenant_id__in=tenant_ids)
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


# Derived models reach the tenant through their cost center, so the object-level
# scoping (F-03/F-06) needs the explicit path.
_CC_TENANT_PATH = "cost_center__tenant_id"

AssignmentDetail, AssignmentCreate, AssignmentUpdate = (
    type(
        "AssignmentDetail",
        (RegistryDetail,),
        {"model": Assignment, "tenant_path": _CC_TENANT_PATH},
    ),
    type(
        "AssignmentCreate",
        (RegistryCreate,),
        {"model": Assignment, "form_class": AssignmentForm},
    ),
    type(
        "AssignmentUpdate",
        (RegistryUpdate,),
        {
            "model": Assignment,
            "form_class": AssignmentForm,
            "tenant_path": _CC_TENANT_PATH,
        },
    ),
)


class OperatorAssignmentList(RegistryList):
    """OPS-1 / LV-31: an operator anchored to a cost center over a period, with
    its own columns (Operator / Cost center / Status / Purpose / Since) instead
    of the generic Name/Created/Status table."""

    model = OperatorAssignment
    template_name = "registry/operatorassignment_list.html"
    htmx_template_name = "registry/_operatorassignment_rows.html"
    search_fields = [
        "operator__full_name",
        "operator__employee_id",
        "cost_center__code",
    ]

    def get_queryset(self):
        return super().get_queryset().select_related("operator", "cost_center")


class AircraftAssignmentList(RegistryList):
    """OPS-1 / LV-31: an aircraft anchored to a cost center over a period, with
    its own columns (mirror of the operator-assignment list)."""

    model = AircraftAssignment
    template_name = "registry/aircraftassignment_list.html"
    htmx_template_name = "registry/_aircraftassignment_rows.html"
    search_fields = ["aircraft__registration", "aircraft__model", "cost_center__code"]

    def get_queryset(self):
        return super().get_queryset().select_related("aircraft", "cost_center")


class OperatorBulkAssign(HtmxFormMixin, ModelPermissionRequiredMixin, FormView):
    """LV-18: assign many operators to one cost center in a single submit.

    Takes over the operator-assignment "+ New" entry point so the common case
    (drop 5-10 operators onto a contract) is one action, not one per operator.
    Editing a single existing assignment still goes through the ModelForm.
    """

    model = OperatorAssignment
    permission_action = "add"
    template_name = "generic/form.html"
    form_class = OperatorBulkAssignForm

    def get_success_url(self):
        return reverse("operatorassignment-list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = _("Assign operators to a cost center")
        return context

    def form_valid(self, form):
        bulk_assign_operators(
            operators=form.cleaned_data["operators"],
            cost_center=form.cleaned_data["cost_center"],
            status=form.cleaned_data["status"],
            purpose=form.cleaned_data["purpose"],
            purpose_detail=form.cleaned_data["purpose_detail"],
            user=self.request.user,
        )
        return super().form_valid(form)


OperatorAssignmentDetail, OperatorAssignmentCreate, OperatorAssignmentUpdate = (
    type(
        "OperatorAssignmentDetail",
        (RegistryDetail,),
        {"model": OperatorAssignment, "tenant_path": _CC_TENANT_PATH},
    ),
    OperatorBulkAssign,
    type(
        "OperatorAssignmentUpdate",
        (RegistryUpdate,),
        {
            "model": OperatorAssignment,
            "form_class": OperatorAssignmentForm,
            "tenant_path": _CC_TENANT_PATH,
        },
    ),
)
AircraftAssignmentDetail, AircraftAssignmentCreate, AircraftAssignmentUpdate = (
    type(
        "AircraftAssignmentDetail",
        (RegistryDetail,),
        {"model": AircraftAssignment, "tenant_path": _CC_TENANT_PATH},
    ),
    type(
        "AircraftAssignmentCreate",
        (RegistryCreate,),
        {"model": AircraftAssignment, "form_class": AircraftAssignmentForm},
    ),
    type(
        "AircraftAssignmentUpdate",
        (RegistryUpdate,),
        {
            "model": AircraftAssignment,
            "form_class": AircraftAssignmentForm,
            "tenant_path": _CC_TENANT_PATH,
        },
    ),
)


class ResourceMovementLogList(
    CsvExportMixin, SearchMixin, ModelViewPermissionRequiredMixin, ListView
):
    """OPS-1: the read-only movement trail -- never a create/edit surface.

    resource_id is a bare UUID (it can point at an Operator or an Aircraft
    depending on resource_kind), so this resolves a display label per row
    instead of asking the template to know which model to look up. That same
    bare UUID is why this is the one padrón list that cannot use
    TenantScopedQuerysetMixin's plain `tenant_path` (R5.3): there is no ORM
    join from this model to a tenant, so scoping and "search by aircraft
    registration / operator name" are both done here by resolving matching
    resource ids first, then filtering on (resource_kind, resource_id).
    """

    model = ResourceMovementLog
    template_name = "registry/resourcemovementlog_list.html"
    htmx_template_name = "registry/_resourcemovementlog_rows.html"
    context_object_name = "objects"
    paginate_by = 50
    search_fields = [
        "detail",
        "from_cost_center__code",
        "from_cost_center__name",
        "to_cost_center__code",
        "to_cost_center__name",
        "changed_by_user__username",
    ]

    def get_queryset(self):
        from apps.core.tenancy import visible_tenant_ids

        # Bypasses SearchMixin.get_queryset() on purpose: it would AND its own
        # search_fields filter with whatever runs here, but resource-label
        # search (below) needs to OR into the same query, not stack on top of
        # it as a second, narrower one.
        queryset = ListView.get_queryset(self).select_related(
            "from_cost_center", "to_cost_center", "changed_by_user"
        )

        kind = self.request.GET.get("resource_kind")
        if kind in {"operator", "aircraft"}:
            queryset = queryset.filter(resource_kind=kind)

        tenant_ids = visible_tenant_ids(self.request.user)
        if tenant_ids is not None:
            aircraft_ids = Aircraft.objects.filter(
                tenant_id__in=tenant_ids
            ).values_list("pk", flat=True)
            operator_ids = Operator.objects.filter(
                tenant_id__in=tenant_ids
            ).values_list("pk", flat=True)
            queryset = queryset.filter(
                Q(resource_kind="aircraft", resource_id__in=aircraft_ids)
                | Q(resource_kind="operator", resource_id__in=operator_ids)
            )

        query_text = self.request.GET.get("q", "").strip()
        if query_text:
            matching_aircraft_ids = Aircraft.objects.filter(
                registration__icontains=query_text
            ).values_list("pk", flat=True)
            matching_operator_ids = Operator.objects.filter(
                full_name__icontains=query_text
            ).values_list("pk", flat=True)
            field_query = Q()
            for field in self.search_fields:
                field_query |= Q(**{f"{field}__icontains": query_text})
            queryset = queryset.filter(
                field_query
                | Q(resource_kind="aircraft", resource_id__in=matching_aircraft_ids)
                | Q(resource_kind="operator", resource_id__in=matching_operator_ids)
            )

        return queryset

    def get_context_data(self, **kwargs):
        from .selectors import label_movements

        context = super().get_context_data(**kwargs)
        context["title"] = _("Resource movements")
        context["selected_kind"] = self.request.GET.get("resource_kind", "")
        context["objects"] = label_movements(context["objects"])
        return context


(
    _QualificationAutoList,
    QualificationDetail,
    QualificationCreate,
    QualificationUpdate,
) = make_views(Qualification, QualificationForm, "Qualification")
# Qualification reaches the tenant through its operator (F-03/F-06).
QualificationDetail.tenant_path = "operator__tenant_id"
QualificationUpdate.tenant_path = "operator__tenant_id"


class QualificationList(RegistryList):
    """LV-14: operator-centric habilitations list.

    One row per operator (not per qualification, which repeated the operator's
    name across rows), with the operator's qualification types as chips in one
    column. Search/is_active still filter the underlying qualifications; the
    CSV export keeps exporting the individual qualifications (the real data).
    """

    model = Qualification
    template_name = "registry/qualification_list.html"
    htmx_template_name = "registry/_qualification_rows.html"
    search_fields = [
        "operator__full_name",
        "operator__employee_id",
        "qualification_type__name",
    ]

    def _qualifications_queryset(self):
        """The Qualification rows after search/is_active (used for the CSV and
        to derive which operators to show)."""
        return super().get_queryset()

    def get_queryset(self):
        operator_ids = list(
            self._qualifications_queryset()
            .values_list("operator_id", flat=True)
            .distinct()
        )
        return (
            Operator.objects.filter(pk__in=operator_ids)
            .order_by("full_name")
            # LV-57 added a cost-center column to this list; without this the
            # row partial costs one query per operator.
            .select_related("cost_center")
            .prefetch_related(
                Prefetch(
                    "qualifications",
                    queryset=Qualification.objects.filter(is_active=True)
                    .select_related("qualification_type")
                    .order_by("qualification_type__name"),
                    to_attr="active_qualifications",
                )
            )
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["today"] = timezone.localdate()
        return context

    def get(self, request, *args, **kwargs):
        # Export the underlying qualifications (render_csv_response builds its
        # columns from self.model == Qualification), not the grouped operators.
        if request.GET.get("export") == "csv":
            queryset = self._qualifications_queryset().select_related(
                "operator", "qualification_type"
            )
            return self.render_csv_response(queryset)
        return super().get(request, *args, **kwargs)


# B4.3: the qualification-type catalog. Config model like compliance's
# DocumentType -- list/create/update only, no detail/archive/restore.
class QualificationTypeList(RegistryList):
    model = QualificationType
    search_fields = ["name", "code", "model_keywords"]


class QualificationTypeCreate(RegistryCreate):
    model = QualificationType
    form_class = QualificationTypeForm


class QualificationTypeUpdate(RegistryUpdate):
    model = QualificationType
    form_class = QualificationTypeForm


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
            lambda raw, _line: (
                {
                    "code": raw["code"].strip(),
                    "name": raw["name"].strip(),
                }
                if raw["name"].strip()
                else "code y name son obligatorios."
            ),
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
