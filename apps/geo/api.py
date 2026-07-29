"""JSON API for geo plans and their versions.

Hand-wired routes (no router), mirroring apps/workboard/api.py.

Reads (GEO-5) are gated on ``geo.view_geoplan``; writes (GEO-6: commit, restore)
on ``geo.change_geoplan``. A version is always reached through its plan, so the
plan is the single permission anchor. The export surface (GEO-10) is not here
yet. See docs/dev/geo-editor-plan.md §5-6.
"""

import io
import zipfile

from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.utils.dateparse import parse_datetime
from django.utils.text import slugify
from rest_framework.exceptions import NotAuthenticated, ParseError, PermissionDenied
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import ScopedRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from apps.core.api import ViewModelPermissions
from apps.core.audit import set_audit_context

from .kml import canonical
from .kml.build import build_kml_bytes
from .kml.errors import KmlImportError
from .kml.kmz import MAX_ENTRY_BYTES
from .models import GeoPlan, GeoPlanVersion

CHANGE_PERM = "geo.change_geoplan"
VIEW_PERM = "geo.view_geoplan"


def _get_active_plan(pk):
    """Fetch an active plan by pk or raise 404. Shared by read and write views."""
    return get_object_or_404(
        GeoPlan.objects.filter(is_active=True).select_related(
            "cost_center", "flight_permission", "current_version"
        ),
        pk=pk,
    )


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


class _GeoApiView(APIView):
    """Shared 401/403 split for every geo endpoint (matches the workboard API)."""

    def permission_denied(self, request, message=None, code=None):
        if not request.user or not request.user.is_authenticated:
            raise NotAuthenticated("Authentication required.")
        raise PermissionDenied("Permission denied.")


class _GeoReadView(_GeoApiView):
    """Base for the read endpoints: ``view_geoplan`` + plan lookup.

    ``queryset`` is what ``ViewModelPermissions`` inspects to resolve the
    required permission; it is not used to fetch rows.
    """

    permission_classes = [IsAuthenticated, ViewModelPermissions]
    queryset = GeoPlan.objects.all()

    def get_plan(self, pk):
        return _get_active_plan(pk)


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


# Icons/images that a map can safely render as <img>; anything else is served
# opaque so a crafted entry (e.g. an SVG carrying script) is never interpreted.
_RESOURCE_CONTENT_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "bmp": "image/bmp",
}


class GeoPlanResourceView(_GeoReadView):
    """GET /.../resource/?name=<name> — one embedded KMZ resource (GEO-13).

    Serves an icon/image byte-for-byte from the plan's source KMZ so the map can
    show the real symbols. `name` must be in the current version's
    ``kmz_resources`` whitelist (the canonical validated at import), so this can
    never be turned into an arbitrary zip reader. Best-effort: 404 when the
    source is missing, not a KMZ, or the entry is absent.
    """

    def get(self, request, pk):
        from apps.compliance.storage import get_document_storage

        from .kml.kmz import read_kmz_resource

        plan = self.get_plan(pk)
        name = request.GET.get("name", "")
        resources = (
            plan.current_version.content.get("kmz_resources") or []
            if plan.current_version_id
            else []
        )
        if not name or name not in resources or not plan.source_document_id:
            return HttpResponse(status=404)
        try:
            stored = get_document_storage().open(plan.source_document.file_path)
            data = stored.read()
            payload = read_kmz_resource(data, name)
        except (KmlImportError, FileNotFoundError, OSError):
            return HttpResponse(status=404)
        if payload is None:
            return HttpResponse(status=404)
        extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        content_type = _RESOURCE_CONTENT_TYPES.get(
            extension, "application/octet-stream"
        )
        response = HttpResponse(payload, content_type=content_type)
        response["Cache-Control"] = "private, max-age=3600"
        response["X-Content-Type-Options"] = "nosniff"
        return response


class _GeoCommitMixin(_GeoApiView):
    """Shared write helpers for commit and restore.

    The domain permission is checked explicitly (not via DjangoModelPermissions)
    because that maps POST to ``add_*``, the wrong verb: committing a version is
    a *change* to an existing plan, not creating a plan.
    """

    @staticmethod
    def _latest(plan):
        return plan.versions.order_by("-version_number").first()

    @staticmethod
    def _audit(request, plan, action, metadata):
        # DRF wraps the Django request; the audit middleware reads
        # _audit_context off the underlying request, so set it there and not on
        # the wrapper (where it would be invisible to the middleware).
        set_audit_context(
            getattr(request, "_request", request),
            plan,
            action=action,
            metadata=metadata,
        )

    def _commit_version(self, request, plan, latest, **fields):
        """Insert a new version and advance the plan pointer, atomically.

        full_clean() runs inside the transaction as layer 2 of the approved-plan
        lock; the endpoint's own status check is layer 1.
        """
        with transaction.atomic():
            version = GeoPlanVersion(
                plan=plan,
                version_number=(latest.version_number if latest else 0) + 1,
                parent_version=latest,
                created_by=request.user,
                **fields,
            )
            version.full_clean()
            version.save()
            plan.current_version = version
            plan.save(update_fields=["current_version", "updated_at"])
        return version

    @staticmethod
    def _locked_response():
        return JsonResponse(
            {"detail": "This plan is locked.", "code": "plan_locked"}, status=409
        )


class GeoPlanVersionsView(_GeoCommitMixin):
    """GET: list versions (``view_geoplan``). POST: commit (``change_geoplan``).

    Both live on the same path, so permissions and throttles branch on method:
    reads keep the project-default user throttle; the commit adds the scoped
    ``geo-commit`` ceiling (declaring throttle_classes replaces the defaults, so
    UserRateThrottle is kept explicitly).
    """

    queryset = GeoPlan.objects.all()
    throttle_scope = "geo-commit"

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated()]
        return [IsAuthenticated(), ViewModelPermissions()]

    def get_throttles(self):
        if self.request.method == "POST":
            return [UserRateThrottle(), ScopedRateThrottle()]
        return super().get_throttles()

    def get(self, request, pk):
        plan = _get_active_plan(pk)
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

    def post(self, request, pk):
        if not request.user.has_perm(CHANGE_PERM):
            return JsonResponse({"detail": "Permission denied."}, status=403)
        plan = _get_active_plan(pk)

        try:
            payload = request.data
        except ParseError:
            return JsonResponse({"detail": "Invalid JSON."}, status=400)
        if not isinstance(payload, dict):
            return JsonResponse({"detail": "Invalid payload."}, status=400)

        # Layer 1 of the lock, and the authoritative one: every content change
        # goes through this endpoint.
        if plan.status not in GeoPlan.EDITABLE_STATUSES:
            return self._locked_response()

        # Optimistic concurrency, two independent checks (same as workboard): a
        # timestamp precondition and the authoritative base_version.
        expected_updated = request.headers.get("If-Unmodified-Since")
        if expected_updated:
            expected = parse_datetime(expected_updated)
            if expected is None or plan.updated_at > expected:
                return JsonResponse(
                    {"detail": "Plan changed since it was read.", "code": "conflict"},
                    status=409,
                )

        latest = self._latest(plan)
        latest_number = latest.version_number if latest else 0
        if payload.get("base_version") != latest_number:
            return JsonResponse(
                {
                    "detail": "base_version is not the latest version.",
                    "code": "conflict",
                    "latest": latest_number,
                },
                status=409,
            )

        content = payload.get("content")
        # The client is not trusted: re-validate schema, caps, coordinate ranges
        # and re-parse every raw_xml fragment with the hardened parser.
        try:
            canonical.validate_document(content, reparse_raw=True)
        except KmlImportError as exc:
            return JsonResponse({"detail": str(exc)}, status=400)

        checksum = canonical.canonical_checksum(content)
        if latest and latest.content_checksum == checksum:
            return JsonResponse(
                {
                    "version": "v1",
                    "code": "no_change",
                    "version_number": latest.version_number,
                },
                status=200,
            )

        bbox = canonical.compute_bbox(content) or (None, None, None, None)
        version = self._commit_version(
            request,
            plan,
            latest,
            content=content,
            content_checksum=checksum,
            source="editor",
            summary=(payload.get("summary") or "")[:200],
            feature_count=canonical.count_features(content),
            size_bytes=canonical.size_bytes(content),
            bbox_west=bbox[0],
            bbox_south=bbox[1],
            bbox_east=bbox[2],
            bbox_north=bbox[3],
        )
        self._audit(
            request,
            plan,
            "geo_plan_committed",
            {
                "version": version.version_number,
                "checksum": checksum,
                "feature_count": version.feature_count,
            },
        )
        return JsonResponse(
            {
                "version": "v1",
                "version_number": version.version_number,
                "checksum": checksum,
                "feature_count": version.feature_count,
            },
            status=201,
        )


class GeoPlanRestoreView(_GeoCommitMixin):
    """POST /.../versions/<n>/restore/ — copy version n forward as a new version."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle, ScopedRateThrottle]
    throttle_scope = "geo-commit"

    def post(self, request, pk, number):
        if not request.user.has_perm(CHANGE_PERM):
            return JsonResponse({"detail": "Permission denied."}, status=403)
        plan = _get_active_plan(pk)

        if plan.status not in GeoPlan.EDITABLE_STATUSES:
            return self._locked_response()

        source = get_object_or_404(plan.versions.all(), version_number=number)
        latest = self._latest(plan)
        # Restoring the version that is already current is a no-op.
        if latest and latest.content_checksum == source.content_checksum:
            return JsonResponse(
                {
                    "version": "v1",
                    "code": "no_change",
                    "version_number": latest.version_number,
                },
                status=200,
            )

        version = self._commit_version(
            request,
            plan,
            latest,
            restored_from=source,
            content=source.content,
            content_checksum=source.content_checksum,
            source="restore",
            summary=f"Restore of v{number}"[:200],
            feature_count=source.feature_count,
            size_bytes=source.size_bytes,
            bbox_west=source.bbox_west,
            bbox_south=source.bbox_south,
            bbox_east=source.bbox_east,
            bbox_north=source.bbox_north,
        )
        self._audit(
            request,
            plan,
            "geo_plan_restored",
            {
                "version": version.version_number,
                "restored_from": number,
            },
        )
        return JsonResponse(
            {
                "version": "v1",
                "version_number": version.version_number,
                "restored_from": number,
            },
            status=201,
        )


def _build_kmz(plan, version, kml_bytes):
    """Zip doc.kml with the original's embedded resources copied byte-for-byte.

    Resource *names* live in the canonical (validated at import); the bytes are
    never stored, they are copied from the source KMZ at export. Best-effort: if
    the source is missing or unreadable the KML still exports, just without its
    icons/imagery.
    """
    buffer = io.BytesIO()
    # getvalue() must run AFTER the ZipFile closes, or the central directory is
    # never written and the archive is unreadable.
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as out:
        out.writestr("doc.kml", kml_bytes)
        resources = version.content.get("kmz_resources") or []
        if resources and plan.source_document_id:
            _copy_kmz_resources(out, plan.source_document, resources)
    return buffer.getvalue()


def _copy_kmz_resources(out, source_document, resources):
    """Copy named resources from the original KMZ into the export, best-effort."""
    from apps.compliance.storage import get_document_storage

    try:
        original = get_document_storage().open(source_document.file_path)
        source = zipfile.ZipFile(io.BytesIO(original.read()))
    except Exception:
        return  # source missing/unreadable: the KML still exports without icons
    present = {info.filename: info for info in source.infolist()}
    for name in resources:
        info = present.get(name)
        # Guard the copy the way the importer does: a stored file could have been
        # tampered with between import and export.
        if info is None or name == "doc.kml" or info.file_size > MAX_ENTRY_BYTES:
            continue
        with source.open(info) as handle:
            out.writestr(name, handle.read(MAX_ENTRY_BYTES + 1)[:MAX_ENTRY_BYTES])


class GeoPlanExportView(_GeoCommitMixin):
    """POST /.../export/ — download a version as KML or KMZ.

    POST (not GET) so the audit middleware records it. Gated on ``view_geoplan``:
    exporting is a read. Scoped to the geo-export throttle.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle, ScopedRateThrottle]
    throttle_scope = "geo-export"

    def post(self, request, pk):
        if not request.user.has_perm(VIEW_PERM):
            return JsonResponse({"detail": "Permission denied."}, status=403)
        plan = _get_active_plan(pk)

        try:
            payload = request.data
        except ParseError:
            return JsonResponse({"detail": "Invalid request."}, status=400)

        fmt = payload.get("format", "kml")
        if fmt not in ("kml", "kmz"):
            return JsonResponse({"detail": "Unsupported format."}, status=400)

        number = payload.get("version") or (
            plan.current_version.version_number if plan.current_version_id else None
        )
        try:
            number = int(number)
        except (TypeError, ValueError):
            return JsonResponse({"detail": "A version is required."}, status=400)
        version = get_object_or_404(plan.versions.all(), version_number=number)

        kml_bytes = build_kml_bytes(version.content)
        base = slugify(plan.title) or "plan"
        self._audit(
            request,
            plan,
            "geo_plan_exported",
            {"version": number, "format": fmt},
        )
        if fmt == "kml":
            response = HttpResponse(
                kml_bytes, content_type="application/vnd.google-earth.kml+xml"
            )
            response["Content-Disposition"] = (
                f'attachment; filename="{base}_v{number}.kml"'
            )
            return response

        response = HttpResponse(
            _build_kmz(plan, version, kml_bytes),
            content_type="application/vnd.google-earth.kmz",
        )
        response["Content-Disposition"] = f'attachment; filename="{base}_v{number}.kmz"'
        return response
