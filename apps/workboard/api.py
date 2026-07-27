from rest_framework import serializers
from django.http import JsonResponse
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.viewsets import ViewSet
from rest_framework.exceptions import NotAuthenticated, PermissionDenied
import json
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_datetime

from apps.core.api import ViewModelPermissions

from .models import KanbanTask
from .selectors import user_can_edit_board, visible_tasks_for_user
from .models import KanbanStage


class ThrottledObtainAuthToken(ObtainAuthToken):
    """Token endpoint with the anon throttle it silently opted out of.

    DRF's ObtainAuthToken sets ``throttle_classes = ()`` on the class, so the
    project-wide DEFAULT_THROTTLE_CLASSES never applied to the one endpoint
    that accepts unauthenticated credential guesses.
    """

    throttle_classes = (AnonRateThrottle,)


class KanbanTaskSerializer(serializers.ModelSerializer):
    state = serializers.CharField(source="stage.status_type", read_only=True)
    stage_name = serializers.CharField(source="stage.name", read_only=True)
    board_name = serializers.CharField(source="board.name", read_only=True)
    progress = serializers.IntegerField(source="checklist_progress", read_only=True)
    source_type = serializers.CharField(
        source="source_content_type.model", read_only=True, allow_null=True
    )
    source_id = serializers.UUIDField(
        source="source_object_id", read_only=True, allow_null=True
    )

    class Meta:
        model = KanbanTask
        fields = [
            "id",
            "title",
            "board",
            "board_name",
            "stage",
            "stage_name",
            "state",
            "priority",
            "due_date",
            "progress",
            "source_type",
            "source_id",
            "updated_at",
        ]


class KanbanTaskViewSet(ViewSet):
    """Canonical task API used by both the stable and DRF-compatible URLs."""

    permission_classes = [IsAuthenticated, ViewModelPermissions]
    queryset = KanbanTask.objects.all()

    def get_queryset(self):
        return (
            visible_tasks_for_user(self.request.user)
            .select_related("board", "stage", "assigned_to")
            .prefetch_related("labels", "checklist_items")
        )

    def permission_denied(self, request, message=None, code=None):
        if not request.user or not request.user.is_authenticated:
            raise NotAuthenticated("Authentication required.")
        raise PermissionDenied("Permission denied.")

    @staticmethod
    def _legacy_item(task):
        return {
            "id": str(task.pk),
            "title": task.title,
            "board": {"id": str(task.board_id), "name": task.board.name},
            "state": task.stage.status_type,
            "stage": task.stage.name,
            "priority": task.priority,
            "assignee": task.assigned_to.full_name if task.assigned_to else None,
            "due_date": task.due_date.isoformat() if task.due_date else None,
            "labels": [
                {"id": str(label.pk), "name": label.name, "color": label.color}
                for label in task.labels.all()
            ],
            "checklist": {
                "total": task.checklist_total,
                "completed": task.checklist_completed,
                "progress": task.checklist_progress,
            },
            "updated_at": task.updated_at.isoformat(),
            "source": {
                "type": task.source_content_type.model,
                "id": str(task.source_object_id),
            }
            if task.source_content_type_id and task.source_object_id
            else None,
        }

    def list(self, request):
        queryset = self.get_queryset()
        priority = request.query_params.get("priority")
        if priority in dict(KanbanTask.PRIORITIES):
            queryset = queryset.filter(priority=priority)
        if request.path.startswith("/api/drf/"):
            return Response(KanbanTaskSerializer(queryset[:100], many=True).data)
        try:
            page = max(int(request.GET.get("page", "1")), 1)
            page_size = min(max(int(request.GET.get("page_size", "25")), 1), 100)
        except ValueError:
            return JsonResponse({"detail": "Invalid pagination."}, status=400)
        total = queryset.count()
        start = (page - 1) * page_size
        items = [
            self._legacy_item(task) for task in queryset[start : start + page_size]
        ]
        return JsonResponse(
            {
                "version": "v1",
                "page": page,
                "page_size": page_size,
                "total": total,
                "results": items,
            }
        )

    def partial_update(self, request, pk=None):
        task = get_object_or_404(self.get_queryset(), pk=pk)
        if not user_can_edit_board(request.user, task.board):
            return JsonResponse({"detail": "Object permission denied."}, status=403)
        expected_updated = request.headers.get("If-Unmodified-Since")
        if expected_updated:
            expected = parse_datetime(expected_updated)
            if expected is None or task.updated_at > expected:
                return JsonResponse(
                    {"detail": "Task changed since it was read.", "code": "conflict"},
                    status=409,
                )
        try:
            payload = (
                request.data
                if hasattr(request, "data")
                else json.loads(request.body or "{}")
            )
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"detail": "Invalid JSON."}, status=400)
        allowed = {"title", "description", "priority", "stage_id", "due_date"}
        unknown = sorted(set(payload) - allowed)
        if unknown:
            return JsonResponse(
                {"detail": "Unsupported fields.", "fields": unknown}, status=400
            )
        if "priority" in payload and payload["priority"] not in dict(
            KanbanTask.PRIORITIES
        ):
            return JsonResponse({"detail": "Invalid priority."}, status=400)
        if "stage_id" in payload:
            stage = KanbanStage.objects.filter(
                pk=payload["stage_id"], board=task.board, is_active=True
            ).first()
            if not stage:
                return JsonResponse(
                    {"detail": "Stage does not belong to this board."}, status=400
                )
            task.stage = stage
        changed = ["stage"] if "stage_id" in payload else []
        for field in ("title", "description", "priority", "due_date"):
            if field in payload:
                setattr(task, field, payload[field])
                changed.append(field)
        # full_clean before save: without it {"due_date": "mañana"} raised an
        # unhandled 500, and a 10,000-character title persisted fine on SQLite
        # (which ignores varchar lengths) only to blow up on PostgreSQL later.
        try:
            task.full_clean()
        except DjangoValidationError as exc:
            return JsonResponse(
                {"detail": "Validation failed.", "errors": exc.message_dict},
                status=400,
            )
        # update_fields keeps the write to what the request touched, so the
        # optimistic-concurrency check is not undone by rewriting the row.
        task.save(update_fields=[*changed, "updated_at"])
        from apps.core.audit import set_audit_context

        set_audit_context(request, task)
        return JsonResponse(
            {
                "version": "v1",
                "id": str(task.pk),
                "updated": sorted(payload),
                "updated_at": task.updated_at.isoformat(),
            }
        )


KanbanTaskApiView = KanbanTaskViewSet


def api_openapi_schema(_request):
    """Return the stable, public OpenAPI contract for the v1 API.

    The schema is deliberately kept as a small hand-maintained contract until
    the API surface grows enough to justify a schema-generation dependency.
    """
    schema = {
        "openapi": "3.0.3",
        "info": {
            "title": "AeroControl API",
            "version": "1.0.0",
            "description": "Read and update operational Kanban tasks.",
        },
        "servers": [{"url": "/"}],
        "components": {
            "securitySchemes": {
                "tokenAuth": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "Authorization",
                    "description": "Use Authorization: Token <key>, with the token returned by /api-token/.",
                }
            },
            "schemas": {
                "KanbanTask": {
                    "type": "object",
                    "required": ["id", "title", "board", "stage", "priority"],
                    "properties": {
                        "id": {"type": "string", "format": "uuid"},
                        "title": {"type": "string"},
                        "board": {"type": "string", "format": "uuid"},
                        "board_name": {"type": "string"},
                        "stage": {"type": "string", "format": "uuid"},
                        "stage_name": {"type": "string"},
                        "state": {"type": "string"},
                        "priority": {
                            "type": "string",
                            "enum": ["low", "medium", "high"],
                        },
                        "due_date": {
                            "type": "string",
                            "format": "date",
                            "nullable": True,
                        },
                        "progress": {"type": "integer", "minimum": 0, "maximum": 100},
                        "updated_at": {"type": "string", "format": "date-time"},
                    },
                },
                "GeoPlanVersionRef": {
                    "type": "object",
                    "required": ["version_number", "checksum"],
                    "properties": {
                        "version_number": {"type": "integer", "minimum": 1},
                        "checksum": {"type": "string"},
                        "source": {
                            "type": "string",
                            "enum": ["import", "editor", "restore"],
                        },
                        "summary": {"type": "string"},
                        "feature_count": {"type": "integer", "minimum": 0},
                        "size_bytes": {"type": "integer", "minimum": 0},
                        "bbox": {
                            "type": "array",
                            "nullable": True,
                            "items": {"type": "number"},
                            "minItems": 4,
                            "maxItems": 4,
                        },
                        "created_at": {"type": "string", "format": "date-time"},
                    },
                },
                "GeoPlan": {
                    "type": "object",
                    "required": ["id", "title", "status"],
                    "properties": {
                        "id": {"type": "string", "format": "uuid"},
                        "title": {"type": "string"},
                        "status": {
                            "type": "string",
                            "enum": [
                                "draft",
                                "editing",
                                "in_review",
                                "approved",
                                "rejected",
                            ],
                        },
                        "cost_center": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string", "format": "uuid"},
                                "name": {"type": "string"},
                            },
                        },
                        "flight_permission": {
                            "type": "string",
                            "format": "uuid",
                            "nullable": True,
                        },
                        "current_version": {
                            "allOf": [
                                {"$ref": "#/components/schemas/GeoPlanVersionRef"}
                            ],
                            "nullable": True,
                        },
                        "created_at": {"type": "string", "format": "date-time"},
                        "updated_at": {"type": "string", "format": "date-time"},
                    },
                },
            },
        },
        "paths": {
            "/api/drf/v1/workboard/tasks/": {
                "get": {
                    "operationId": "listKanbanTasks",
                    "summary": "List active Kanban tasks",
                    "security": [{"tokenAuth": []}],
                    "parameters": [
                        {
                            "name": "priority",
                            "in": "query",
                            "schema": {
                                "type": "string",
                                "enum": ["low", "medium", "high"],
                            },
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Active tasks",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "array",
                                        "items": {
                                            "$ref": "#/components/schemas/KanbanTask"
                                        },
                                    }
                                }
                            },
                        },
                        "401": {"description": "Authentication required"},
                        "403": {"description": "Missing view permission"},
                    },
                }
            },
            "/api/v1/workboard/tasks/{id}/": {
                "patch": {
                    "operationId": "updateKanbanTask",
                    "summary": "Update a Kanban task",
                    "security": [{"tokenAuth": []}],
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string", "format": "uuid"},
                        },
                        {
                            "name": "If-Unmodified-Since",
                            "in": "header",
                            "schema": {"type": "string", "format": "date-time"},
                        },
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/KanbanTask"}
                            }
                        },
                    },
                    "responses": {
                        "200": {"description": "Updated task"},
                        "400": {"description": "Validation error"},
                        "401": {"description": "Authentication required"},
                        "403": {"description": "Missing change permission"},
                        "409": {"description": "Optimistic concurrency conflict"},
                    },
                }
            },
            "/api/v1/geo/plans/{id}/": {
                "get": {
                    "operationId": "getGeoPlan",
                    "summary": "Read geo plan metadata",
                    "security": [{"tokenAuth": []}],
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string", "format": "uuid"},
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Plan metadata",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/GeoPlan"}
                                }
                            },
                        },
                        "401": {"description": "Authentication required"},
                        "403": {"description": "Missing view permission"},
                        "404": {"description": "No such active plan"},
                    },
                }
            },
            "/api/v1/geo/plans/{id}/versions/": {
                "get": {
                    "operationId": "listGeoPlanVersions",
                    "summary": "List a plan's versions (without content)",
                    "security": [{"tokenAuth": []}],
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string", "format": "uuid"},
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Versions, newest first",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "array",
                                        "items": {
                                            "$ref": "#/components/schemas/GeoPlanVersionRef"
                                        },
                                    }
                                }
                            },
                        },
                        "401": {"description": "Authentication required"},
                        "403": {"description": "Missing view permission"},
                        "404": {"description": "No such active plan"},
                    },
                },
                "post": {
                    "operationId": "commitGeoPlanVersion",
                    "summary": "Commit a new canonical version",
                    "description": (
                        "Appends a version. The server re-validates and "
                        "recomputes every derived field; client-supplied "
                        "checksums/counts are ignored."
                    ),
                    "security": [{"tokenAuth": []}],
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string", "format": "uuid"},
                        },
                        {
                            "name": "If-Unmodified-Since",
                            "in": "header",
                            "schema": {"type": "string", "format": "date-time"},
                        },
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["base_version", "content"],
                                    "properties": {
                                        "base_version": {
                                            "type": "integer",
                                            "minimum": 0,
                                        },
                                        "summary": {"type": "string"},
                                        "content": {"type": "object"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "201": {"description": "New version committed"},
                        "200": {
                            "description": "No change (content matched the latest)"
                        },
                        "400": {"description": "Invalid document"},
                        "401": {"description": "Authentication required"},
                        "403": {"description": "Missing change permission"},
                        "409": {
                            "description": "conflict (stale base_version) or plan_locked"
                        },
                        "429": {"description": "Throttled (geo-commit)"},
                    },
                },
            },
            "/api/v1/geo/plans/{id}/versions/{number}/restore/": {
                "post": {
                    "operationId": "restoreGeoPlanVersion",
                    "summary": "Restore a version as a new version",
                    "security": [{"tokenAuth": []}],
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string", "format": "uuid"},
                        },
                        {
                            "name": "number",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "integer", "minimum": 1},
                        },
                    ],
                    "responses": {
                        "201": {"description": "Restored as a new version"},
                        "200": {
                            "description": "No change (already the current version)"
                        },
                        "401": {"description": "Authentication required"},
                        "403": {"description": "Missing change permission"},
                        "404": {"description": "No such plan or version"},
                        "409": {"description": "plan_locked"},
                        "429": {"description": "Throttled (geo-commit)"},
                    },
                }
            },
            "/api/v1/geo/plans/{id}/versions/{number}/content/": {
                "get": {
                    "operationId": "getGeoPlanVersionContent",
                    "summary": "Read the full canonical document of a version",
                    "description": (
                        "Returns the canonical AeroKML JSON. The response carries "
                        "an ETag equal to the content checksum; send it back as "
                        "If-None-Match to get a 304 when unchanged."
                    ),
                    "security": [{"tokenAuth": []}],
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string", "format": "uuid"},
                        },
                        {
                            "name": "number",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "integer", "minimum": 1},
                        },
                        {
                            "name": "If-None-Match",
                            "in": "header",
                            "schema": {"type": "string"},
                        },
                    ],
                    "responses": {
                        "200": {
                            "description": "Canonical document",
                            "content": {
                                "application/json": {"schema": {"type": "object"}}
                            },
                        },
                        "304": {"description": "Content unchanged (ETag matched)"},
                        "401": {"description": "Authentication required"},
                        "403": {"description": "Missing view permission"},
                        "404": {"description": "No such plan or version"},
                    },
                }
            },
        },
    }
    return JsonResponse(schema)
