from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.shortcuts import redirect
from django.utils import timezone
from django.views.generic import DetailView, FormView, ListView

from apps.compliance.models import Document, DocumentType
from apps.compliance.views import save_uploaded_file, uploaded_file_cleanup
from apps.core.audit import set_audit_context
from apps.core.views import ModelPermissionRequiredMixin, ModelViewPermissionRequiredMixin

from .forms import GeoPlanImportForm
from .kml import canonical
from .models import GeoPlan, GeoPlanVersion

GEO_SOURCE_DOC_TYPE_CODE = "GEO_SOURCE"


class GeoPlanListView(ModelViewPermissionRequiredMixin, ListView):
    model = GeoPlan
    template_name = "geo/plan_list.html"
    context_object_name = "plans"
    paginate_by = 25

    def get_queryset(self):
        return (
            GeoPlan.objects.filter(is_active=True)
            .select_related("cost_center", "current_version")
            .order_by("-created_at")
        )


class GeoPlanDetailView(ModelViewPermissionRequiredMixin, DetailView):
    model = GeoPlan
    template_name = "geo/plan_detail.html"
    context_object_name = "plan"

    def get_queryset(self):
        return GeoPlan.objects.select_related(
            "cost_center", "flight_permission", "current_version", "source_document"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["versions"] = self.object.versions.order_by("-version_number")
        return context


class GeoPlanImportView(ModelPermissionRequiredMixin, FormView):
    model = GeoPlan
    permission_action = "add"
    template_name = "geo/plan_import.html"
    form_class = GeoPlanImportForm

    def form_valid(self, form):
        uploaded = form.cleaned_data["file"]
        document_content = form.canonical
        bbox = canonical.compute_bbox(document_content) or (None, None, None, None)

        with uploaded_file_cleanup() as state, transaction.atomic():
            plan = GeoPlan.objects.create(
                title=form.cleaned_data["title"],
                cost_center=form.cleaned_data["cost_center"],
                flight_permission=form.cleaned_data.get("flight_permission"),
                created_by=self.request.user,
                status="draft",
            )
            doc_type, _created = DocumentType.objects.get_or_create(
                code=GEO_SOURCE_DOC_TYPE_CODE,
                defaults={"name": "Geo source", "requires_expiry": False},
            )
            document = Document(
                doc_type=doc_type,
                content_type=ContentType.objects.get_for_model(GeoPlan),
                object_id=plan.pk,
                title=uploaded.name,
                issue_date=timezone.localdate(),
                file_path="",
            )
            document.save()
            # Set only after the storage write so a later failure in this block
            # removes the orphaned file (uploaded_file_cleanup).
            state["path"] = save_uploaded_file(document, uploaded)

            version = GeoPlanVersion.objects.create(
                plan=plan,
                version_number=1,
                content=document_content,
                content_checksum=canonical.canonical_checksum(document_content),
                source="import",
                feature_count=canonical.count_features(document_content),
                size_bytes=canonical.size_bytes(document_content),
                bbox_west=bbox[0],
                bbox_south=bbox[1],
                bbox_east=bbox[2],
                bbox_north=bbox[3],
                created_by=self.request.user,
            )
            plan.source_document = document
            plan.current_version = version
            plan.save(
                update_fields=["source_document", "current_version", "updated_at"]
            )
            set_audit_context(
                self.request,
                plan,
                action="geo_plan_imported",
                metadata={"version": 1, "features": version.feature_count},
            )
        self._plan = plan
        return redirect("geo-plan-detail", pk=plan.pk)
