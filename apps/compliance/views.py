from contextlib import contextmanager, suppress

from django.contrib import messages
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _, ngettext
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
from django.contrib.contenttypes.prefetch import GenericPrefetch
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.text import capfirst

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
from .forms import (
    AlertForm,
    AlertResolveForm,
    AlertRuleForm,
    DeliverableForm,
    DocumentBulkUploadForm,
    DocumentForm,
    DocumentTypeForm,
    NonConformityForm,
)
from .models import (
    Alert,
    AlertRule,
    Deliverable,
    Document,
    DocumentType,
    MonthlyComplianceReview,
    NonConformity,
    document_upload_path,
)
from .storage import DocumentStorageNotFound, get_document_storage
from .watchables import alert_subject_querysets


def document_home_url(document):
    """LV-40: the entity's own fiche (its Documents tab), not the general
    document list -- which is off the menu (LV-D8) and left the user stranded
    after uploading from a fiche.

    Module-level since LV-86: the bulk upload lands in the same place, and a
    second copy of this mapping would drift from this one.
    """
    from django.urls import NoReverseMatch

    content_type = document.content_type
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
            return f"{reverse(detail_name, args=[document.object_id])}#tab-documents"
        except NoReverseMatch:
            pass
    # Operational records live in their own repository; everything else that is
    # left falls back to the company documents view rather than the unlisted
    # general document list.
    if document.doc_type.is_operational_record:
        return reverse("operational-records")
    return reverse("company-documents")


def upload_cancel_url(request):
    """Where "Cancel" goes from an upload form: back where the person came from.

    LV-99: the single-upload form sent Cancel to the general document list --
    a screen LV-40 deliberately took off the menu, so cancelling stranded people
    on a page they could not navigate back from. Saving already lands on the
    record's own file (`document_home_url`); cancelling now agrees with it.

    Built from **our own** query parameters, never from `HTTP_REFERER`: that
    header is untrusted input, and rendering a link out of it puts somebody
    else's URL inside our page. Falls back to the company documents repository
    when the form was opened with no record in mind.
    """
    from django.contrib.contenttypes.models import ContentType

    content_type = ContentType.objects.filter(
        pk=request.GET.get("entity_type") or 0
    ).first()
    object_id = request.GET.get("object_id")
    if content_type and object_id:
        model = content_type.model_class()
        record = model._default_manager.filter(pk=object_id).first() if model else None
        if record is not None:
            document = Document(content_type=content_type, object_id=record.pk)
            with suppress(Exception):
                return document_home_url(document)
    return reverse("company-documents")


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
        context["title"] = capfirst(self.model._meta.verbose_name_plural)
        return context


class ComplianceCreate(HtmxFormMixin, ModelPermissionRequiredMixin, CreateView):
    permission_action = "add"
    template_name = "generic/form.html"

    def get_success_url(self):
        return reverse(f"{self.model._meta.model_name}-list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = _("New %(record)s") % {
            "record": self.model._meta.verbose_name
        }
        return context


class DeliverableList(ComplianceList):
    """R7.4: survey deliverables and their quality verdict (ISO 9001 8.6)."""

    model = Deliverable
    template_name = "compliance/deliverable_list.html"
    search_fields = ["title", "cost_center__code", "cost_center__name"]

    def get_queryset(self):
        queryset = super().get_queryset().select_related("cost_center")
        status = self.request.GET.get("status")
        if status in dict(Deliverable.STATUS_CHOICES):
            queryset = queryset.filter(status=status)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_choices"] = Deliverable.STATUS_CHOICES
        context["selected_status"] = self.request.GET.get("status", "")
        return context


class DeliverableDetail(ModelViewPermissionRequiredMixin, DetailView):
    model = Deliverable
    template_name = "compliance/deliverable_detail.html"
    context_object_name = "deliverable"

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(is_active=True)
            .select_related("cost_center", "validated_by")
            .prefetch_related("flight_permissions")
        )


class DeliverableCreate(ComplianceCreate):
    model = Deliverable
    form_class = DeliverableForm


class DeliverableUpdate(HtmxFormMixin, ModelPermissionRequiredMixin, UpdateView):
    model = Deliverable
    form_class = DeliverableForm
    permission_action = "change"
    template_name = "generic/form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = _("Edit deliverable")
        return context


class DeliverableValidate(ModelPermissionRequiredMixin, View):
    """The internal validation signature ISO 8.6 asks for before release.

    A signature, not a boolean: it records who and when, and freezes the
    contract thresholds in force at that moment so renegotiating the contract
    later cannot silently rewrite the verdict of work already accepted.
    """

    model = Deliverable
    permission_action = "change"

    def post(self, request, pk):
        deliverable = get_object_or_404(Deliverable, pk=pk, is_active=True)
        if deliverable.status != Deliverable.STATUS_DRAFT:
            messages.error(request, _("Only a draft deliverable can be validated."))
            return redirect(deliverable)
        deliverable.validate_quality(user=request.user)
        set_audit_context(request, deliverable, action="deliverable_validated")
        messages.success(request, _("Deliverable validated."))
        return redirect(deliverable)


class DeliverableRelease(ModelPermissionRequiredMixin, View):
    """The quality gate (R7.4), same shape as R2.4's document gate.

    Blocked only on a *measured* failure against the contract's thresholds. A
    deliverable nobody could assess -- no thresholds agreed, or metrics not in
    yet -- releases freely: enforcing an invented criterion is how a gate ends
    up switched off. Overriding a real failure needs a written waiver, so the
    exception is a decision on record rather than a silent bypass.
    """

    model = Deliverable
    permission_action = "change"

    def post(self, request, pk):
        deliverable = get_object_or_404(Deliverable, pk=pk, is_active=True)
        if deliverable.status != Deliverable.STATUS_VALIDATED:
            messages.error(request, _("Only a validated deliverable can be released."))
            return redirect(deliverable)

        waiver = (request.POST.get("waiver_reason") or "").strip()
        if waiver:
            deliverable.release_waiver_reason = waiver
        if not deliverable.can_release:
            set_audit_context(
                request, deliverable, action="deliverable_release_blocked"
            )
            messages.error(
                request,
                _(
                    "This deliverable is below the contract's acceptance "
                    "criteria. Releasing it anyway requires a documented reason."
                ),
            )
            return redirect(deliverable)

        deliverable.status = Deliverable.STATUS_RELEASED
        deliverable.save(
            update_fields=["status", "release_waiver_reason", "updated_at"]
        )
        set_audit_context(
            request,
            deliverable,
            action="deliverable_released",
            metadata={"waived": bool(deliverable.release_waiver_reason)},
        )
        messages.success(request, _("Deliverable released."))
        return redirect(deliverable)


class DeliverableReject(ModelPermissionRequiredMixin, View):
    """Reject a deliverable -- the reflight / rework path of ISO 10.2.

    Rejecting **opens a non-conformity automatically**. This is the clause's
    most important trigger: a rejected survey is exactly the kind of finding
    10.2 wants a root cause for, and leaving it to someone to remember to file
    one is how the record ends up incomplete.

    The finding is created open and empty of analysis on purpose -- prompting
    for a root cause at the moment of rejection would get "pending" typed into
    it, which looks answered and is worse than blank.
    """

    model = Deliverable
    permission_action = "change"

    @transaction.atomic
    def post(self, request, pk):
        deliverable = get_object_or_404(Deliverable, pk=pk, is_active=True)
        if deliverable.status == Deliverable.STATUS_RELEASED:
            messages.error(request, _("A released deliverable cannot be rejected."))
            return redirect(deliverable)
        deliverable.status = Deliverable.STATUS_REJECTED
        deliverable.save(update_fields=["status", "updated_at"])

        finding = NonConformity.objects.create(
            title=_("Rejected deliverable: %(title)s") % {"title": deliverable.title},
            source=NonConformity.SOURCE_REJECTED_DELIVERABLE,
            cost_center=deliverable.cost_center,
            content_type=ContentType.objects.get_for_model(Deliverable),
            object_id=deliverable.pk,
            description=_(
                "Opened automatically when the deliverable was rejected. "
                "Record the root cause and the corrective action before "
                "closing it."
            ),
        )
        set_audit_context(
            request,
            deliverable,
            action="deliverable_rejected",
            metadata={"non_conformity_id": str(finding.pk)},
        )
        messages.success(
            request, _("Deliverable rejected and a non-conformity opened.")
        )
        return redirect(deliverable)


class NonConformityList(ComplianceList):
    """R7.6: reflights, rejected surveys, incidents and audit findings."""

    model = NonConformity
    template_name = "compliance/nonconformity_list.html"
    search_fields = ["title", "description", "root_cause"]

    def get_queryset(self):
        queryset = super().get_queryset().select_related("cost_center")
        status = self.request.GET.get("status")
        if status in dict(NonConformity.STATUS_CHOICES):
            queryset = queryset.filter(status=status)
        source = self.request.GET.get("source")
        if source in dict(NonConformity.SOURCE_CHOICES):
            queryset = queryset.filter(source=source)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_choices"] = NonConformity.STATUS_CHOICES
        context["source_choices"] = NonConformity.SOURCE_CHOICES
        context["selected_status"] = self.request.GET.get("status", "")
        context["selected_source"] = self.request.GET.get("source", "")
        return context


class NonConformityDetail(ModelViewPermissionRequiredMixin, DetailView):
    model = NonConformity
    template_name = "compliance/nonconformity_detail.html"
    context_object_name = "finding"

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(is_active=True)
            .select_related("cost_center", "closed_by", "effectiveness_verified_by")
        )


class NonConformityCreate(ComplianceCreate):
    model = NonConformity
    form_class = NonConformityForm


class NonConformityUpdate(HtmxFormMixin, ModelPermissionRequiredMixin, UpdateView):
    model = NonConformity
    form_class = NonConformityForm
    permission_action = "change"
    template_name = "generic/form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = _("Edit non-conformity")
        return context


class NonConformityClose(ModelPermissionRequiredMixin, View):
    """Close a finding, which requires the analysis ISO 10.2 asks for."""

    model = NonConformity
    permission_action = "change"

    def post(self, request, pk):
        finding = get_object_or_404(NonConformity, pk=pk, is_active=True)
        if not finding.close(user=request.user):
            messages.error(
                request,
                _(
                    "Record the root cause and the corrective action before "
                    "closing this finding."
                ),
            )
            return redirect(finding)
        set_audit_context(request, finding, action="non_conformity_closed")
        messages.success(request, _("Non-conformity closed."))
        return redirect(finding)


class NonConformityReopen(ModelPermissionRequiredMixin, View):
    model = NonConformity
    permission_action = "change"

    def post(self, request, pk):
        finding = get_object_or_404(NonConformity, pk=pk, is_active=True)
        finding.reopen()
        set_audit_context(request, finding, action="non_conformity_reopened")
        messages.success(request, _("Non-conformity reopened."))
        return redirect(finding)


class NonConformityVerifyEffectiveness(ModelPermissionRequiredMixin, View):
    """Same second statement as on an alert: "and it worked"."""

    model = NonConformity
    permission_action = "change"

    def post(self, request, pk):
        finding = get_object_or_404(NonConformity, pk=pk, is_active=True)
        note = (request.POST.get("note") or "").strip()
        if not finding.verify_effectiveness(user=request.user, note=note):
            messages.error(
                request, _("Only a closed finding can have its action verified.")
            )
            return redirect(finding)
        set_audit_context(
            request, finding, action="non_conformity_effectiveness_verified"
        )
        messages.success(request, _("Corrective action verified."))
        return redirect(finding)


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


class CompanyDocumentsView(CsvExportMixin, ModelViewPermissionRequiredMixin, ListView):
    """A visible, downloadable home for company-wide documents -- the AOC,
    procedures and forms that belong to the operator as a whole rather than to
    a specific aircraft or permit. They attach to the tenant and flow through
    the same upload/replace/download pipeline as any other Document.

    R4.6: was a plain, unfiltered dump -- no search, no way to narrow by
    category. Reuses DocumentType as the "category" axis (the same one every
    other Document list in the app already groups by) rather than inventing a
    second taxonomy just for this page.
    """

    model = Document
    template_name = "compliance/company_documents.html"
    htmx_template_name = "compliance/_company_document_rows.html"
    context_object_name = "documents"
    paginate_by = 25
    csv_filename = "company_documents.csv"
    csv_fields = [
        Document._meta.get_field(name)
        for name in ("title", "doc_type", "issue_date", "expiry_date")
    ]

    def get_template_names(self):
        if self.request.headers.get("HX-Request") == "true":
            return [self.htmx_template_name]
        return super().get_template_names()

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
        query_text = self.request.GET.get("q", "").strip()
        if query_text:
            queryset = queryset.filter(title__icontains=query_text)
        if self.request.GET.get("doc_type"):
            queryset = queryset.filter(doc_type_id=self.request.GET["doc_type"])
        return queryset

    def get_context_data(self, **kwargs):
        from apps.core.models import OperationalTenant
        from apps.core.tenancy import get_default_tenant, visible_tenant_ids

        context = super().get_context_data(**kwargs)
        context["title"] = _("Company documents")
        context["document_content_type_id"] = ContentType.objects.get_for_model(
            OperationalTenant
        ).pk
        context["document_types"] = DocumentType.objects.filter(is_active=True)
        context["is_htmx"] = self.request.headers.get("HX-Request") == "true"
        # get_default_tenant() returns the pk; resolve the instance so the
        # template can build the upload link from tenant.pk.
        tenant_ids = visible_tenant_ids(self.request.user)
        if tenant_ids is None:
            tenant_ids = [get_default_tenant()]
        context["tenant"] = OperationalTenant.objects.filter(
            pk__in=tenant_ids, is_active=True
        ).first()
        return context


class OperationalRecordsView(
    CsvExportMixin, ModelViewPermissionRequiredMixin, ListView
):
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
        self._prefill_dates_from_record(initial)
        return initial

    def _prefill_dates_from_record(self, initial):
        """LV-79: propose the dates the linked record already holds.

        Uploading the DGAC authorization for a permit meant retyping the very
        dates the permit was created with -- the same information looked up
        twice. The record already knows them, so it offers them.

        Derived from the record rather than passed in the URL: the link is not
        the only way to reach this form, and a URL parameter would silently
        stop working the moment someone arrives another way.

        **Only where the mapping is unambiguous.** A permit's validity window
        *is* the window its authorization covers, and a qualification's dates
        are the same dates. An aircraft or an operator carries several dates
        (insurance, credential, airworthiness) and which one applies depends on
        the document type -- guessing wrong there is worse than not guessing,
        so those are left blank.

        Every value is a suggestion in an editable field, never a decision: the
        DGAC can issue a resolution on a date of its own.
        """
        from django.contrib.contenttypes.models import ContentType

        # (app_label, model) -> (source field for issue_date, for expiry_date)
        date_sources = {
            ("operations", "flightpermission"): ("valid_from", "valid_until"),
            ("registry", "qualification"): ("issue_date", "expiry_date"),
        }

        entity_type, object_id = initial.get("entity_type"), initial.get("object_id")
        if not entity_type or not object_id:
            return
        content_type = ContentType.objects.filter(pk=entity_type).first()
        if content_type is None:
            return
        source = date_sources.get((content_type.app_label, content_type.model))
        if source is None:
            return
        model = content_type.model_class()
        if model is None:
            return
        record = model._default_manager.filter(pk=object_id, is_active=True).first()
        if record is None:
            return

        issue_field, expiry_field = source
        for target, field_name in (
            ("issue_date", issue_field),
            ("expiry_date", expiry_field),
        ):
            # Anything already in the URL wins: an explicit request beats a
            # derived suggestion.
            if not initial.get(target):
                value = getattr(record, field_name, None)
                if value:
                    initial[target] = value

    def get_success_url(self):
        return document_home_url(self.object)

    def get_context_data(self, **kwargs):
        # LV-99: Cancel goes where Save goes, not to the unlisted document list.
        context = super().get_context_data(**kwargs)
        context["cancel_url"] = upload_cancel_url(self.request)
        return context

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
        # LV-85: "pdf", "image" or None -- which viewer the page embeds, decided
        # from the same allowlist the preview view enforces so the page cannot
        # offer a viewer for something that will come back as a download.
        extension = self.object.file_path.rsplit(".", 1)[-1].lower()
        content_type = INLINE_PREVIEW_TYPES.get(extension)
        context["preview_kind"] = (
            None
            if content_type is None
            else ("pdf" if content_type == "application/pdf" else "image")
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


# LV-85: the only kinds served **inline**. Everything else keeps coming back as
# a download. This is not about what the browser can render -- it is that an
# uploaded file displayed inline is executed in this app's origin if the browser
# can be talked into treating it as HTML. PDFs and raster images have no such
# reading; KML is XML and DOCX/XLSX are ZIPs, so they stay attachments.
INLINE_PREVIEW_TYPES = {
    "pdf": "application/pdf",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
}


class DocumentPreview(ModelPermissionRequiredMixin, View):
    """LV-85: serve the file for viewing inside the page, not as a download.

    Same authorization as `DocumentDownload` -- `view_document` plus the tenant
    scope -- because it is the same bytes: a "preview" that skipped the checks
    would be a way around them (the F-05 finding, in a new wrapper).

    Anything outside the inline allowlist redirects to the download instead of
    being refused: the user asked to see a document, and handing them the file
    is closer to that than an error page.
    """

    model = Document
    permission_action = "view"

    def get(self, request, pk):
        document = get_object_or_404(
            scope_queryset_to_tenant(Document.objects.all(), request.user),
            pk=pk,
            is_active=True,
        )
        filename = document.file_path.rsplit("/", 1)[-1]
        extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        content_type = INLINE_PREVIEW_TYPES.get(extension)
        if content_type is None:
            return redirect("document-download", pk=pk)
        try:
            stream = get_document_storage().open(document.file_path)
        except (DocumentStorageNotFound, OSError) as exc:
            raise Http404("Document file not found") from exc
        response = FileResponse(
            stream, as_attachment=False, filename=filename, content_type=content_type
        )
        # Belt and braces next to SECURE_CONTENT_TYPE_NOSNIFF: this response is
        # the one that hands a user-supplied file to the browser with
        # `Content-Disposition: inline`, so the type it is served as must be the
        # type it is treated as.
        response["X-Content-Type-Options"] = "nosniff"
        # The app refuses to be framed anywhere (X_FRAME_OPTIONS=DENY plus
        # `frame-ancestors 'none'`), which is the clickjacking protection and
        # stays. **This one response** relaxes it to same-origin, because the
        # fiche embeds it in an <iframe> of its own -- being framed by yourself
        # is not that attack. Both headers, because either alone still blocks:
        # the CSP directive is honoured by modern browsers and X-Frame-Options
        # by everything else.
        response["X-Frame-Options"] = "SAMEORIGIN"
        response.frame_ancestors_self = True
        return response


class DocumentBulkUpload(ModelPermissionRequiredMixin, FormView):
    """LV-86: several documents onto one record in a single action.

    Requires `add_document`, like the single upload it batches.

    Files are written **inside one transaction with the same cleanup guard** the
    single upload uses: storage is not transactional, so a failure halfway
    through a batch of twelve would otherwise leave stored files with no rows
    pointing at them.
    """

    model = Document
    permission_action = "add"
    form_class = DocumentBulkUploadForm
    template_name = "compliance/document_bulk_form.html"

    def get_initial(self):
        initial = super().get_initial()
        for field in ("entity_type", "object_id", "doc_type"):
            value = self.request.GET.get(field)
            if value:
                initial[field] = value
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # LV-99 moved this to `upload_cancel_url`, shared with the single
        # upload: both screens answer the same question, and a second copy is
        # how one of them drifts back to the unlisted document list.
        context["cancel_url"] = upload_cancel_url(self.request)
        return context

    def form_valid(self, form):
        record = form.cleaned_data["record"]
        uploads = form.cleaned_data["files"]
        titles = form.titles_for(record)
        content_type = form.cleaned_data["entity_type"]
        created = []
        with uploaded_file_cleanup() as stored:
            with transaction.atomic():
                for uploaded, title in zip(uploads, titles):
                    document = Document(
                        title=title,
                        doc_type=form.cleaned_data["doc_type"],
                        content_type=content_type,
                        object_id=record.pk,
                        issue_date=form.cleaned_data["issue_date"],
                        expiry_date=form.cleaned_data.get("expiry_date"),
                    )
                    set_audit_context(self.request, document)
                    document.save()
                    stored["path"] = save_uploaded_file(document, uploaded)
                    created.append(document)
        messages.success(
            self.request,
            ngettext(
                "%(count)s document uploaded.",
                "%(count)s documents uploaded.",
                len(created),
            )
            % {"count": len(created)},
        )
        self.created = created
        return super().form_valid(form)

    def get_success_url(self):
        # Back to the record the batch was filed against, same reasoning as
        # LV-40 for the single upload: the general document list is off the menu.
        return document_home_url(self.created[0])


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
        # LV-100: `replacing` is what tells the shared field layout to show the
        # record as a fact instead of as two pickers this view ignores.
        context.update(
            title=f"Replace {self.document.title}",
            document=self.document,
            replacing=self.document,
        )
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


# LV-75: `_group_alerts` lived here and folded same-rule, same-date alerts into
# one row (R6.3). It is gone: one alert, one row.
#
# R6.3's premise was "same rule + same date => same cause" (a fleet policy
# covering several aircraft). LV-68 already found that false against production
# data -- dates coincide without a shared cause -- and removed the bulk resolve,
# but kept the visual grouping. That left the row itself making the claim the
# data does not support, plus a second, quieter cost: a grouped row had no
# button in its Actions column (just "2 alertas") and offered its members a
# text link instead, so the same action lived in two different places depending
# on whether a neighbouring record happened to share a date.
class AlertList(ComplianceList):
    model = Alert
    template_name = "compliance/alert_list.html"
    search_fields = ["message"]

    def get_queryset(self):
        # LV-106: `content_object` is a GenericForeignKey, which no
        # `select_related` can reach -- and every row reads it three times (the
        # record's name, `watched_date`, `is_overdue`), so the list cost one
        # query per alert. Measured on the demo: 62 queries for 21 alerts, while
        # every other list in the app sits between 6 and 16. It is the third
        # appearance of the shape V.18/V.19 already cost this project twice, and
        # it lands on the screen the user says they live in.
        # `GenericPrefetch` rather than a plain `prefetch_related`: the bare
        # prefetch resolves the generic relation but hands back instances whose
        # own `__str__` crosses a relation (a qualification names its operator
        # and its type), so the row still cost two queries. The per-model
        # querysets carry those joins -- see `alert_subject_querysets`.
        queryset = (
            super()
            .get_queryset()
            .select_related("alert_rule", "content_type")
            .prefetch_related(
                GenericPrefetch("content_object", alert_subject_querysets())
            )
        )
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
        # LV-76: get_queryset() has filtered on ?entity_type since this view was
        # written and this list has always been in the context, but no template
        # ever rendered it -- a working filter with no way to reach it. Paired
        # with the raw model slug ("flightpermission") the select would have been
        # unreadable anyway, so the labels come from the same verbose_name the
        # rows already show in the "Entity type" column.
        content_types = ContentType.objects.filter(
            pk__in=Alert.objects.values("content_type_id")
        )
        entity_types = []
        for content_type in content_types:
            model = content_type.model_class()
            label = model._meta.verbose_name if model else content_type.model
            entity_types.append((content_type.model, str(label).capitalize()))
        context["entity_types"] = sorted(entity_types, key=lambda pair: pair[1])
        context["selected_entity_type"] = self.request.GET.get("entity_type", "")
        # LV-69b: this used to resolve each alert's linked KanbanTask in one
        # query, so the row could offer "Create task" vs "View task". Those
        # actions were removed when the workboard left the menu (LV-69) --
        # they pushed work into a place nobody navigates to any more -- so the
        # query went with them rather than costing one lookup per page load for
        # a value no template reads. Restoring the buttons means restoring this.
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
    """R6.2: ISO 10.2 asks for the root cause on record -- "Resolve" used to
    take nothing at all. AlertResolveForm makes `reason` required for this
    one manual click; the automatic callers of Alert.resolve() (generate_alerts
    -> resolve_open_alerts_for, Document.resolve_related_alerts, R6.1's
    task-completion signal) have no human to ask and stay reason-less.

    A crowded list row has no room for a required textarea, so this is a
    small modal (the same generic/_form_content.html every other
    create/edit modal in the app uses) instead of the one-click button the
    other row actions still are.
    """

    model = Alert
    permission_action = "change"

    def get(self, request, pk):
        get_object_or_404(Alert, pk=pk, is_active=True)
        return render(
            request,
            "generic/_form_content.html",
            {"form": AlertResolveForm(), "title": _("Resolve alert")},
        )

    def post(self, request, pk):
        alert = get_object_or_404(Alert, pk=pk, is_active=True)
        form = AlertResolveForm(request.POST)
        if not form.is_valid():
            return render(
                request,
                "generic/_form_content.html",
                {"form": form, "title": _("Resolve alert")},
                status=422,
            )
        moved_task = alert.resolve(reason=form.cleaned_data["reason"])
        metadata = {"reason": form.cleaned_data["reason"]}
        if moved_task:
            metadata["moved_task_id"] = str(moved_task.pk)
        set_audit_context(request, alert, action="alert_resolved", metadata=metadata)
        if request.headers.get("HX-Request") == "true":
            return HttpResponse(
                status=204, headers={"HX-Trigger": "modal-form-success"}
            )
        messages.success(request, _("Alert resolved."))
        return _redirect_back(request)


# LV-68 (2026-08-11): AlertResolveGroup lived here -- one modal that resolved a
# whole (rule, date) group with a single shared reason. Removed after seeing it
# against real production data: two aircraft can share an insurance expiry date
# without sharing a cause, and writing one root cause across independent
# findings is false evidence, the opposite of what ISO 10.2 wants. The visual
# grouping stays (R6.3, it does cut noise); every action is per alert again.
# Deleted rather than left unrouted: an endpoint that performs the action we
# just judged wrong is a liability, not a spare part.


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


class AlertVerifyEffectiveness(ModelPermissionRequiredMixin, View):
    """R7.6: confirm a corrective action actually held (ISO 10.2).

    Not the inverse of reopening: this leaves the alert resolved and its reason
    untouched, and adds a second, later statement -- "and it worked". The way
    to say the opposite is to reopen, which is already there.

    An optional note travels with it. Unlike the resolution reason (required by
    R6.2), "it held" often needs no elaboration, and demanding prose to confirm
    a non-event is how a control turns into a formality people click through.
    """

    model = Alert
    permission_action = "change"

    def post(self, request, pk):
        alert = get_object_or_404(Alert, pk=pk, is_active=True)
        note = (request.POST.get("note") or "").strip()
        if not alert.verify_effectiveness(user=request.user, note=note):
            messages.error(
                request, _("Only a resolved alert can have its action verified.")
            )
            return _redirect_back(request)
        set_audit_context(request, alert, action="alert_effectiveness_verified")
        messages.success(request, _("Corrective action verified."))
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
