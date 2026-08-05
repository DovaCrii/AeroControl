from contextlib import contextmanager, suppress

from django.contrib import messages
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    FormView,
    ListView,
    UpdateView,
    View,
)

from django.contrib.contenttypes.models import ContentType
from django.utils.http import url_has_allowed_host_and_scheme

from apps.core.audit import set_audit_context
from apps.workboard.models import KanbanTask
from apps.core.views import (
    CsvExportMixin,
    HtmxFormMixin,
    ModelPermissionRequiredMixin,
    ModelViewPermissionRequiredMixin,
    SearchMixin,
    TenantScopedQuerysetMixin,
)
from apps.core.tenancy import scope_queryset_to_tenant
from .forms import AlertForm, AlertRuleForm, DocumentForm, DocumentTypeForm
from .models import (
    Alert,
    AlertRule,
    Document,
    DocumentType,
    MonthlyComplianceReview,
    document_upload_path,
)
from .storage import DocumentStorageNotFound, get_document_storage


def save_uploaded_file(document, uploaded):
    relative_path = document_upload_path(document, uploaded.name)
    get_document_storage().save(relative_path, uploaded)
    document.file_path = relative_path
    document.save(update_fields=["file_path", "updated_at"])
    return relative_path


@contextmanager
def uploaded_file_cleanup():
    """Delete the stored file if the surrounding transaction fails.

    Storage is not transactional: the DB rolls back, the file stays. Yields a
    dict; set `path` after the storage write so a later failure inside the
    atomic block removes the orphan instead of leaving unreferenced files for
    cleanup_documents to find.
    """
    state = {"path": None}
    try:
        yield state
    except Exception:
        if state["path"]:
            with suppress(Exception):
                get_document_storage().delete(state["path"])
        raise


class ComplianceList(
    CsvExportMixin, SearchMixin, ModelViewPermissionRequiredMixin, ListView
):
    template_name = "generic/list.html"
    context_object_name = "objects"
    paginate_by = 25

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = _(self.model._meta.verbose_name_plural.title())
        return context


class ComplianceCreate(HtmxFormMixin, ModelPermissionRequiredMixin, CreateView):
    permission_action = "add"
    template_name = "generic/form.html"

    def get_success_url(self):
        return reverse(f"{self.model._meta.model_name}-list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = _("New %(record)s") % {
            "record": _(self.model._meta.verbose_name.title())
        }
        return context


class DocumentList(ComplianceList):
    model = Document
    template_name = "compliance/document_list.html"
    search_fields = ["title"]
    htmx_template_name = "compliance/_document_rows.html"

    def get_queryset(self):
        queryset = super().get_queryset().select_related("doc_type", "content_type")
        if self.request.GET.get("doc_type"):
            queryset = queryset.filter(doc_type_id=self.request.GET["doc_type"])
        if self.request.GET.get("is_current_version") in ("true", "false"):
            queryset = queryset.filter(
                is_current_version=self.request.GET["is_current_version"] == "true"
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["document_types"] = DocumentType.objects.filter(is_active=True)
        return context


class CompanyDocumentsView(ModelViewPermissionRequiredMixin, ListView):
    """A visible, downloadable home for company-wide documents -- the AOC,
    procedures and forms that belong to the operator as a whole rather than to
    a specific aircraft or permit. They attach to the tenant and flow through
    the same upload/replace/download pipeline as any other Document.
    """

    model = Document
    template_name = "compliance/company_documents.html"
    context_object_name = "documents"
    paginate_by = 25

    def get_queryset(self):
        from apps.core.models import OperationalTenant
        from apps.core.tenancy import visible_tenant_ids

        tenant_ct = ContentType.objects.get_for_model(OperationalTenant)
        queryset = (
            Document.objects.filter(
                content_type=tenant_ct, is_current_version=True, is_active=True
            )
            .select_related("doc_type")
            .order_by("-issue_date")
        )
        tenant_ids = visible_tenant_ids(self.request.user)
        if tenant_ids is not None:
            queryset = queryset.filter(object_id__in=tenant_ids)
        return queryset

    def get_context_data(self, **kwargs):
        from apps.core.models import OperationalTenant
        from apps.core.tenancy import get_default_tenant, visible_tenant_ids

        context = super().get_context_data(**kwargs)
        context["title"] = _("Company documents")
        context["document_content_type_id"] = ContentType.objects.get_for_model(
            OperationalTenant
        ).pk
        # get_default_tenant() returns the pk; resolve the instance so the
        # template can build the upload link from tenant.pk.
        tenant_ids = visible_tenant_ids(self.request.user)
        if tenant_ids is None:
            tenant_ids = [get_default_tenant()]
        context["tenant"] = OperationalTenant.objects.filter(
            pk__in=tenant_ids, is_active=True
        ).first()
        return context


class OperationalRecordsView(ModelViewPermissionRequiredMixin, ListView):
    """LV-30: the per-flight operational records (flight logs, checklists,
    inspections) filed against each cost center, month by month.

    A different category from the company-wide documents (CompanyDocumentsView):
    those are the operator's procedures, these are the many records generated by
    flying. Same Document pipeline, filtered to the types flagged
    `is_operational_record` and hung off a CostCenter.
    """

    model = Document
    template_name = "compliance/operational_records.html"
    context_object_name = "documents"
    paginate_by = 25

    def _cost_center_ct(self):
        from apps.registry.models import CostCenter

        return ContentType.objects.get_for_model(CostCenter)

    @staticmethod
    def _parse_month(value):
        """A 'YYYY-MM' filter value as a date (day 1), or None when absent/bad."""
        from datetime import datetime

        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y-%m").date()
        except ValueError:
            return None

    def get_queryset(self):
        from apps.core.tenancy import visible_tenant_ids

        queryset = (
            Document.objects.filter(
                content_type=self._cost_center_ct(),
                doc_type__is_operational_record=True,
                is_current_version=True,
                is_active=True,
            )
            .select_related("doc_type")
            .order_by("-issue_date")
        )
        tenant_ids = visible_tenant_ids(self.request.user)
        if tenant_ids is not None:
            queryset = queryset.filter(tenant_id__in=tenant_ids)
        if self.request.GET.get("cost_center"):
            queryset = queryset.filter(object_id=self.request.GET["cost_center"])
        if self.request.GET.get("doc_type"):
            queryset = queryset.filter(doc_type_id=self.request.GET["doc_type"])
        month = self._parse_month(self.request.GET.get("month"))
        if month:
            queryset = queryset.filter(
                issue_date__year=month.year, issue_date__month=month.month
            )
        return queryset

    def get_context_data(self, **kwargs):
        from apps.registry.models import CostCenter

        context = super().get_context_data(**kwargs)
        context["title"] = _("Operational records")
        cost_centers = self._scoped_cost_centers()
        context["cost_centers"] = cost_centers
        context["operational_doc_types"] = DocumentType.objects.filter(
            is_operational_record=True, is_active=True
        ).order_by("name")
        context["cost_center_content_type_id"] = self._cost_center_ct().pk
        context["selected_cost_center"] = self.request.GET.get("cost_center", "")
        context["selected_doc_type"] = self.request.GET.get("doc_type", "")
        context["selected_month"] = self.request.GET.get("month", "")
        # Attach the owning cost center to each row without a per-row GFK query.
        by_id = {str(cc.pk): cc for cc in CostCenter.objects.all()}
        for document in context["documents"]:
            document.cost_center = by_id.get(str(document.object_id))
        return context

    def _scoped_cost_centers(self):
        from apps.core.tenancy import visible_tenant_ids
        from apps.registry.models import CostCenter

        queryset = CostCenter.objects.filter(is_active=True)
        tenant_ids = visible_tenant_ids(self.request.user)
        if tenant_ids is not None:
            queryset = queryset.filter(tenant_id__in=tenant_ids)
        return queryset.order_by("code")


class DocumentCreate(ComplianceCreate):
    model = Document
    form_class = DocumentForm
    template_name = "compliance/document_form.html"
    htmx_template_name = "compliance/_document_form_content.html"

    def get_initial(self):
        # Pre-fill from an entity's own page (OPS-5: the flight permission
        # detail's "Upload document" link, LV-30: the operational-records
        # repository), same GET-param idiom as FlightRecordCreate.get_initial().
        initial = super().get_initial()
        for field in ("entity_type", "object_id", "doc_type", "issue_date"):
            value = self.request.GET.get(field)
            if value:
                initial[field] = value
        return initial

    def get_success_url(self):
        """LV-40: return to the entity's own fiche (its Documents tab), not the
        general document list -- which is off the menu (LV-D8) and left the user
        stranded after uploading from a fiche."""
        from django.urls import NoReverseMatch

        obj = self.object
        content_type = obj.content_type
        key = f"{content_type.app_label}.{content_type.model}"
        if key == "core.operationaltenant":
            return reverse("company-documents")
        detail_name = {
            "registry.costcenter": "costcenter-detail",
            "registry.aircraft": "aircraft-detail",
            "registry.operator": "operator-detail",
            "operations.flightpermission": "permission-detail",
        }.get(key)
        if detail_name:
            try:
                return f"{reverse(detail_name, args=[obj.object_id])}#tab-documents"
            except NoReverseMatch:
                pass
        # Operational records live in their own repository; everything else that
        # is left falls back to the company documents view rather than the
        # unlisted general document list.
        if obj.doc_type.is_operational_record:
            return reverse("operational-records")
        return reverse("company-documents")

    def form_valid(self, form):
        with uploaded_file_cleanup() as stored:
            with transaction.atomic():
                response = super().form_valid(form)
                stored["path"] = save_uploaded_file(
                    self.object, form.cleaned_data["file"]
                )
        return response


class DocumentEntityOptions(ModelPermissionRequiredMixin, View):
    model = Document
    permission_action = "add"

    def get(self, request):
        try:
            content_type_id = int(request.GET.get("entity_type", ""))
        except (TypeError, ValueError):
            return HttpResponseBadRequest()
        form = DocumentForm(data={"entity_type": content_type_id})
        if not form.fields["entity_type"].queryset.filter(pk=content_type_id).exists():
            return HttpResponseBadRequest()
        return render(request, "compliance/_document_object_field.html", {"form": form})


class DocumentDetail(
    TenantScopedQuerysetMixin, ModelViewPermissionRequiredMixin, DetailView
):
    model = Document
    template_name = "compliance/document_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["versions"] = (
            Document.objects.filter(
                content_type=self.object.content_type,
                object_id=self.object.object_id,
                is_current_version=False,
            )
            .exclude(pk=self.object.pk)
            .order_by("-created_at")
        )
        return context


class DocumentDownload(ModelPermissionRequiredMixin, View):
    model = Document
    permission_action = "view"

    def get(self, request, pk):
        document = get_object_or_404(
            scope_queryset_to_tenant(Document.objects.all(), request.user),
            pk=pk,
            is_active=True,
        )
        try:
            stream = get_document_storage().open(document.file_path)
        except DocumentStorageNotFound as exc:
            raise Http404("Document file not found") from exc
        except OSError as exc:
            raise Http404("Document file not found") from exc
        filename = document.file_path.rsplit("/", 1)[-1]
        return FileResponse(stream, as_attachment=True, filename=filename)


class DocumentReplace(ModelPermissionRequiredMixin, FormView):
    model = Document
    permission_action = "change"
    form_class = DocumentForm
    template_name = "compliance/document_replace.html"

    def dispatch(self, request, *args, **kwargs):
        self.document = get_object_or_404(
            scope_queryset_to_tenant(Document.objects.all(), request.user),
            pk=kwargs["pk"],
            is_active=True,
        )
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        return {
            "title": self.document.title,
            "doc_type": self.document.doc_type,
            "entity_type": self.document.content_type,
            "object_id": self.document.object_id,
            "issue_date": self.document.issue_date,
            "expiry_date": self.document.expiry_date,
        }

    def form_valid(self, form):
        with uploaded_file_cleanup() as stored:
            with transaction.atomic():
                self.document.is_current_version = False
                self.document.save(update_fields=["is_current_version", "updated_at"])
                self.document.resolve_related_alerts()
                new_document = form.save(commit=False)
                new_document.is_current_version = True
                new_document.content_type = self.document.content_type
                new_document.object_id = self.document.object_id
                new_document.file_path = ""
                new_document.save()
                stored["path"] = save_uploaded_file(
                    new_document, form.cleaned_data["file"]
                )
        set_audit_context(
            self.request,
            new_document,
            action="document_replaced",
            metadata={"replaced_document_id": str(self.document.pk)},
        )
        return redirect("document-detail", pk=new_document.pk)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(title=f"Replace {self.document.title}", document=self.document)
        return context


class DocumentDelete(
    TenantScopedQuerysetMixin, ModelPermissionRequiredMixin, DeleteView
):
    model = Document
    permission_action = "delete"
    template_name = "generic/confirm_delete.html"
    success_url = "/compliance/document/"

    def form_valid(self, form):
        self.object.is_active = False
        self.object.save(update_fields=["is_active", "updated_at"])
        set_audit_context(self.request, self.object, action="archived")
        messages.success(self.request, _("Document archived."))
        return redirect(self.success_url)


class AlertList(ComplianceList):
    model = Alert
    template_name = "compliance/alert_list.html"
    search_fields = ["message"]

    def get_queryset(self):
        queryset = super().get_queryset().select_related("alert_rule", "content_type")
        resolved = self.request.GET.get("is_resolved")
        if resolved in ("true", "false"):
            queryset = queryset.filter(is_resolved=resolved == "true")
        if self.request.GET.get("entity_type"):
            queryset = queryset.filter(
                content_type__model=self.request.GET["entity_type"]
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["entity_types"] = Alert.objects.values_list(
            "content_type__model", flat=True
        ).distinct()
        # Resolve the linked task for the page's alerts in one query so the
        # template can offer "Create task" vs "View task" without an N+1.
        alerts = list(context.get("objects") or [])
        if alerts:
            alert_ct = ContentType.objects.get_for_model(Alert)
            tasks = {
                task.source_object_id: task
                for task in KanbanTask.objects.filter(
                    source_content_type=alert_ct,
                    source_object_id__in=[alert.pk for alert in alerts],
                    is_active=True,
                ).only("id", "board_id", "source_object_id")
            }
            for alert in alerts:
                task = tasks.get(alert.pk)
                alert.linked_task_id = task.pk if task else None
                alert.linked_task_board_id = task.board_id if task else None
        return context


def _redirect_back(request, fallback="alert-list"):
    """Return to the validated referer, like AlertCreateTask already did.

    The three buttons on one alert row behaved differently: Create task came
    back to the filtered, paginated list the user was on, while Resolve and
    Undo dumped them on page one with the filters gone.
    """
    referer = request.META.get("HTTP_REFERER", "")
    if referer and url_has_allowed_host_and_scheme(
        referer,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(referer)
    return redirect(fallback)


class AlertResolve(ModelPermissionRequiredMixin, View):
    model = Alert
    permission_action = "change"

    def post(self, request, pk):
        alert = get_object_or_404(Alert, pk=pk, is_active=True)
        moved_task = alert.resolve()
        metadata = {"moved_task_id": str(moved_task.pk)} if moved_task else {}
        set_audit_context(request, alert, action="alert_resolved", metadata=metadata)
        messages.success(request, _("Alert resolved."))
        return _redirect_back(request)


class AlertReopen(ModelPermissionRequiredMixin, View):
    """Undo a resolution.

    Resolving is a single click on a crowded row, so it needs a way back. The
    audit trail keeps both events: reopening does not erase the resolution, it
    records a second, opposite one.
    """

    model = Alert
    permission_action = "change"

    def post(self, request, pk):
        alert = get_object_or_404(Alert, pk=pk, is_active=True)
        moved_task = alert.reopen()
        metadata = {"moved_task_id": str(moved_task.pk)} if moved_task else {}
        set_audit_context(request, alert, action="alert_reopened", metadata=metadata)
        messages.success(request, _("Alert reopened."))
        return _redirect_back(request)


class AlertCreateTask(ModelPermissionRequiredMixin, View):
    """Manually spawn the follow-up task for an alert (B1.4).

    Single click on purpose: reuses Alert.ensure_follow_up_task() and falls
    back to the compliance board when the rule has no explicit target, so the
    operator never has to pick a board/stage from the alert list.
    """

    model = KanbanTask
    permission_action = "add"

    def post(self, request, pk):
        alert = get_object_or_404(Alert, pk=pk, is_active=True)
        task = alert.ensure_follow_up_task(allow_default_board=True)
        if task is None:
            messages.error(
                request,
                _("No Kanban board is available to hold the follow-up task."),
            )
        else:
            messages.success(request, _("Follow-up task created."))
            set_audit_context(
                request,
                alert,
                action="alert_task_created",
                metadata={"task_id": str(task.pk)},
            )
        referer = request.META.get("HTTP_REFERER", "")
        if referer and url_has_allowed_host_and_scheme(
            referer,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(referer)
        return redirect("alert-list")


class MonthlyReviewView(ModelViewPermissionRequiredMixin, ListView):
    """LV-30: the end-of-month compliance table -- one row per (cost center,
    period) with its flights, its filed records and the reviewer's decision.

    The reviewer (group Dirección, `change_monthlycompliancereview`) marks each
    Compliant or Non-compliant with a note; everyone with view permission reads
    it. CSV export gives the informe.
    """

    model = MonthlyComplianceReview
    template_name = "compliance/monthly_review.html"
    context_object_name = "reviews"
    paginate_by = 25

    def get_queryset(self):
        from apps.core.tenancy import visible_tenant_ids

        from .monthly import month_start

        queryset = MonthlyComplianceReview.objects.filter(
            is_active=True
        ).select_related("cost_center", "reviewed_by")
        tenant_ids = visible_tenant_ids(self.request.user)
        if tenant_ids is not None:
            queryset = queryset.filter(cost_center__tenant_id__in=tenant_ids)
        status = self.request.GET.get("status")
        if status in dict(MonthlyComplianceReview.STATUS_CHOICES):
            queryset = queryset.filter(status=status)
        month = self._parse_month(self.request.GET.get("month"))
        if month:
            queryset = queryset.filter(period=month_start(month))
        return queryset

    @staticmethod
    def _parse_month(value):
        from datetime import datetime

        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y-%m").date()
        except ValueError:
            return None

    def _decorate(self, reviews):
        """Attach the flights/records counts each row shows (and the CSV needs)."""
        from .monthly import flights_in_month, records_in_month

        for review in reviews:
            review.flights = flights_in_month(review.cost_center, review.period)
            review.records = records_in_month(review.cost_center, review.period)
        return reviews

    def get(self, request, *args, **kwargs):
        if request.GET.get("export") == "csv":
            return self._csv_response()
        return super().get(request, *args, **kwargs)

    def _csv_response(self):
        import csv

        from django.http import HttpResponse

        reviews = self._decorate(list(self.get_queryset()))
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = (
            'attachment; filename="monthly-compliance.csv"'
        )
        writer = csv.writer(response)
        writer.writerow(
            ["period", "cost_center", "flights", "records", "status", "reviewed_by"]
        )
        for review in reviews:
            writer.writerow(
                [
                    review.period.strftime("%Y-%m"),
                    review.cost_center.code,
                    review.flights,
                    review.records,
                    review.get_status_display(),
                    review.reviewed_by.get_username() if review.reviewed_by else "",
                ]
            )
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = _("Monthly compliance")
        context["reviews"] = self._decorate(list(context["reviews"]))
        context["status_choices"] = MonthlyComplianceReview.STATUS_CHOICES
        context["selected_status"] = self.request.GET.get("status", "")
        context["selected_month"] = self.request.GET.get("month", "")
        context["can_review"] = self.request.user.has_perm(
            "compliance.change_monthlycompliancereview"
        )
        return context


class MonthlyReviewMark(ModelPermissionRequiredMixin, View):
    """Record a reviewer's Compliant / Non-compliant decision (LV-30)."""

    model = MonthlyComplianceReview
    permission_action = "change"

    def post(self, request, pk):
        status = request.POST.get("status")
        if status not in MonthlyComplianceReview.RESOLVED_STATUSES:
            return HttpResponseBadRequest("invalid status")
        review = get_object_or_404(
            scope_queryset_to_tenant(
                MonthlyComplianceReview.objects.all(),
                request.user,
                tenant_path="cost_center__tenant_id",
            ),
            pk=pk,
            is_active=True,
        )
        review.mark(status, request.user, notes=request.POST.get("notes", "").strip())
        set_audit_context(request, review, action=f"monthly_review_{status}")
        messages.success(
            request,
            _("%(center)s %(period)s marked.")
            % {
                "center": review.cost_center.code,
                "period": review.period.strftime("%Y-%m"),
            },
        )
        return _redirect_back(request, fallback="monthly-review")


class ComplianceUpdate(
    TenantScopedQuerysetMixin, HtmxFormMixin, ModelPermissionRequiredMixin, UpdateView
):
    """Edit view for the configuration models.

    Document types and alert rules could be created but never corrected from
    the UI: the generic list offered an Edit button whose URL did not exist,
    so a typo in a rule lived forever or went through the technical admin.
    """

    permission_action = "change"
    template_name = "generic/form.html"

    def get_success_url(self):
        return reverse(f"{self.model._meta.model_name}-list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = _("Edit %(name)s") % {"name": self.model._meta.verbose_name}
        return context

    def form_valid(self, form):
        set_audit_context(self.request, self.object)
        return super().form_valid(form)


class DocumentTypeList(ComplianceList):
    model = DocumentType


class DocumentTypeCreate(ComplianceCreate):
    model = DocumentType
    form_class = DocumentTypeForm


class DocumentTypeUpdate(ComplianceUpdate):
    model = DocumentType
    form_class = DocumentTypeForm


class AlertRuleList(ComplianceList):
    model = AlertRule


class AlertRuleCreate(ComplianceCreate):
    model = AlertRule
    form_class = AlertRuleForm


class AlertRuleUpdate(ComplianceUpdate):
    model = AlertRule
    form_class = AlertRuleForm


class AlertCreate(ComplianceCreate):
    model = Alert
    form_class = AlertForm
