"""GEO-5: read-only JSON API for geo plans and their versions.

Hand-wired routes (no router), mirroring apps/workboard/api.py. Everything is
gated on ``geo.view_geoplan``: a version is always reached through its plan, so
the plan is the single permission anchor. See docs/dev/geo-editor-plan.md §6.

The commit/restore/export surface (GEO-6/GEO-10) is deliberately absent here;
this module is reads only.
"""

from django.http import HttpResponse, JsonResponse
from rest_framework.exceptions import NotAuthenticated, PermissionDenied
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.api import ViewModelPermissions

from .models import GeoPlan


def _version_ref(version):
    """Version metadata without the (potentially multi-MB) canonical blob."""
    bbox = [
        version.bbox_west,
        version.bbox_south,
        version.bbox_east,
        version.bbox_north,
    ]
    return {
        "version_number": version.version_number,
        "checksum": version.content_checksum,
        "source": version.source,
        "summary": version.summary,
        "feature_count": version.feature_count,
        "size_bytes": version.size_bytes,
        "bbox": bbox if version.bbox_west is not None else None,
        "created_at": version.created_at.isoformat(),
    }


class _GeoReadView(APIView):
    """Base for the read endpoints: view permission on GeoPlan + plan lookup.

    ``queryset`` is what ``ViewModelPermissions`` inspects to resolve the
    required permission (``geo.view_geoplan``); it is not used to fetch rows.
    """

    permission_classes = [IsAuthenticated, ViewModelPermissions]
    queryset = GeoPlan.objects.all()

    def permission_denied(self, request, message=None, code=None):
        # Match the workboard API: an anonymous caller gets 401, an
        # authenticated one lacking the permission gets 403.
        if not request.user or not request.user.is_authenticated:
            raise NotAuthenticated("Authentication required.")
        raise PermissionDenied("Permission denied.")

    def get_plan(self, pk):
        return get_object_or_404(
            GeoPlan.objects.filter(is_active=True).select_related(
                "cost_center", "flight_permission", "current_version"
            ),
            pk=pk,
        )


class GeoPlanMetaView(_GeoReadView):
    """GET /api/v1/geo/plans/<uuid>/ — status, current version, timestamps."""

    def get(self, request, pk):
        plan = self.get_plan(pk)
        return JsonResponse(
            {
                "version": "v1",
                "id": str(plan.pk),
                "title": plan.title,
                "status": plan.status,
                "cost_center": {
                    "id": str(plan.cost_center_id),
                    "name": str(plan.cost_center),
                },
                "flight_permission": (
                    str(plan.flight_permission_id)
                    if plan.flight_permission_id
                    else None
                ),
                "current_version": (
                    _version_ref(plan.current_version)
                    if plan.current_version_id
                    else None
                ),
                "created_at": plan.created_at.isoformat(),
                "updated_at": plan.updated_at.isoformat(),
            }
        )


class GeoPlanVersionListView(_GeoReadView):
    """GET /api/v1/geo/plans/<uuid>/versions/ — the version chain, no content."""

    def get(self, request, pk):
        plan = self.get_plan(pk)
        # defer(content): the blob is never sent here, so don't load it.
        versions = plan.versions.defer("content").order_by("-version_number")
        return JsonResponse(
            {
                "version": "v1",
                "plan": str(plan.pk),
                "current_version": (
                    plan.current_version.version_number
                    if plan.current_version_id
                    else None
                ),
                "results": [_version_ref(v) for v in versions],
            }
        )


class GeoPlanVersionContentView(_GeoReadView):
    """GET /.../versions/<n>/content/ — full canonical doc, ETag = checksum."""

    def get(self, request, pk, number):
        plan = self.get_plan(pk)
        version = get_object_or_404(plan.versions.all(), version_number=number)
        etag = f'"{version.content_checksum}"'
        # Cheap revalidation: the checksum is the version's identity, so a
        # matching If-None-Match means the client already has this document.
        if request.headers.get("If-None-Match") == etag:
            not_modified = HttpResponse(status=304)
            not_modified["ETag"] = etag
            return not_modified
        response = JsonResponse(version.content)
        response["ETag"] = etag
        return response
