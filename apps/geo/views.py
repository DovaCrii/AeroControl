from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.shortcuts import redirect
from django.utils import timezone
from django.views.generic import DetailView, FormView, ListView

from apps.compliance.models import Document, DocumentType
from apps.compliance.views import save_uploaded_file, uploaded_file_cleanup
from apps.core.audit import set_audit_context
from apps.core.views import (
    ModelPermissionRequiredMixin,
    ModelViewPermissionRequiredMixin,
)

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
        from django.conf import settings
        from django.middleware.csrf import get_token
        from django.urls import reverse
        from django.utils.translation import gettext as _

        context = super().get_context_data(**kwargs)
        plan = self.object
        context["versions"] = plan.versions.order_by("-version_number")
        current = plan.current_version
        # Editing (GEO-8) is offered only when the user may change the plan AND
        # the plan is in an editable state; the commit API re-checks both, this
        # only decides whether to render the editor UI. Read-only otherwise.
        editable = self.request.user.has_perm("geo.change_geoplan") and plan.is_editable
        context["editable"] = editable
        # Config for the map island. It fetches the canonical document from the
        # read API and (when editable) commits through the write API; business
        # rules live on the server.
        context["map_config"] = {
            "planId": str(plan.pk),
            "currentVersion": current.version_number if current else None,
            "baseVersion": current.version_number if current else 0,
            "contentUrl": (
                reverse(
                    "api-v1-geo-plan-version-content",
                    args=[plan.pk, current.version_number],
                )
                if current
                else None
            ),
            "commitUrl": reverse("api-v1-geo-plan-versions", args=[plan.pk]),
            "csrfToken": get_token(self.request) if editable else "",
            "tileProviders": settings.GEO_TILE_PROVIDERS,
            "editable": editable,
            "iconBase": settings.STATIC_URL + "vendor/leaflet/images/",
            # The island is client-side JS (outside gettext's reach), so its
            # user-visible strings are localized here and passed through.
            "labels": {
                "untitled": _("Untitled"),
                "length": _("Length"),
                "area": _("Area"),
                "layers": _("Layers"),
                "features": _("Features"),
                "loading": _("Loading map…"),
                "error": _("The map could not be loaded."),
                "empty": _("This version has no geometry to show."),
                "name": _("Name"),
                "description": _("Description"),
                "apply": _("Apply"),
                "unsaved": _("Unsaved changes"),
                "saving": _("Saving…"),
                "conflict": _(
                    "The plan changed on the server. Reload to get the latest "
                    "version, then reapply your changes."
                ),
                "locked": _("This plan can no longer be edited."),
                "invalid": _("The change was rejected:"),
                "throttled": _("Too many saves in a row. Wait a moment."),
                "rescue": _("Download your local copy"),
            },
        }
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
