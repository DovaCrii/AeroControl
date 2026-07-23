from rest_framework import serializers
from django.http import JsonResponse
from rest_framework.permissions import DjangoModelPermissions, IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet
from rest_framework.exceptions import NotAuthenticated, PermissionDenied
import json
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_datetime

from .models import KanbanTask
from .selectors import user_can_edit_board, visible_tasks_for_user
from .models import KanbanStage


class KanbanTaskSerializer(serializers.ModelSerializer):
    state = serializers.CharField(source="stage.status_type", read_only=True)
    stage_name = serializers.CharField(source="stage.name", read_only=True)
    board_name = serializers.CharField(source="board.name", read_only=True)
    progress = serializers.IntegerField(source="checklist_progress", read_only=True)

    class Meta:
        model = KanbanTask
        fields = ["id", "title", "board", "board_name", "stage", "stage_name", "state", "priority", "due_date", "progress", "updated_at"]


class KanbanTaskViewSet(ViewSet):
    """Canonical task API used by both the stable and DRF-compatible URLs."""

    permission_classes = [IsAuthenticated, DjangoModelPermissions]
    queryset = KanbanTask.objects.all()

    def get_queryset(self):
        return visible_tasks_for_user(self.request.user).select_related("board", "stage", "assigned_to").prefetch_related("labels", "checklist_items")

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
            "labels": [{"id": str(label.pk), "name": label.name, "color": label.color} for label in task.labels.all()],
            "checklist": {"total": task.checklist_total, "completed": task.checklist_completed, "progress": task.checklist_progress},
            "updated_at": task.updated_at.isoformat(),
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
        items = [self._legacy_item(task) for task in queryset[start:start + page_size]]
        return JsonResponse({"version": "v1", "page": page, "page_size": page_size, "total": total, "results": items})

    def partial_update(self, request, pk=None):
        task = get_object_or_404(self.get_queryset(), pk=pk)
        if not user_can_edit_board(request.user, task.board):
            return JsonResponse({"detail": "Object permission denied."}, status=403)
        expected_updated = request.headers.get("If-Unmodified-Since")
        if expected_updated:
            expected = parse_datetime(expected_updated)
            if expected is None or task.updated_at > expected:
                return JsonResponse({"detail": "Task changed since it was read.", "code": "conflict"}, status=409)
        try:
            payload = request.data if hasattr(request, "data") else json.loads(request.body or "{}")
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"detail": "Invalid JSON."}, status=400)
        allowed = {"title", "description", "priority", "stage_id", "due_date"}
        unknown = sorted(set(payload) - allowed)
        if unknown:
            return JsonResponse({"detail": "Unsupported fields.", "fields": unknown}, status=400)
        if "priority" in payload and payload["priority"] not in dict(KanbanTask.PRIORITIES):
            return JsonResponse({"detail": "Invalid priority."}, status=400)
        if "stage_id" in payload:
            stage = KanbanStage.objects.filter(pk=payload["stage_id"], board=task.board, is_active=True).first()
            if not stage:
                return JsonResponse({"detail": "Stage does not belong to this board."}, status=400)
            task.stage = stage
        for field in ("title", "description", "priority", "due_date"):
            if field in payload:
                setattr(task, field, payload[field])
        task.save()
        from apps.core.audit import set_audit_context
        set_audit_context(request, task)
        return JsonResponse({"version": "v1", "id": str(task.pk), "updated": sorted(payload), "updated_at": task.updated_at.isoformat()})


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
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "Token",
                    "description": "Use the token returned by /api-token/.",
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
                        "priority": {"type": "string", "enum": ["low", "medium", "high"]},
                        "due_date": {"type": "string", "format": "date", "nullable": True},
                        "progress": {"type": "integer", "minimum": 0, "maximum": 100},
                        "updated_at": {"type": "string", "format": "date-time"},
                    },
                }
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
                            "schema": {"type": "string", "enum": ["low", "medium", "high"]},
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Active tasks",
                            "content": {"application/json": {"schema": {"type": "array", "items": {"$ref": "#/components/schemas/KanbanTask"}}}},
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
                        {"name": "id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}},
                        {"name": "If-Unmodified-Since", "in": "header", "schema": {"type": "string", "format": "date-time"}},
                    ],
                    "requestBody": {"required": True, "content": {"application/json": {"schema": {"$ref": "#/components/schemas/KanbanTask"}}}},
                    "responses": {
                        "200": {"description": "Updated task"},
                        "400": {"description": "Validation error"},
                        "401": {"description": "Authentication required"},
                        "403": {"description": "Missing change permission"},
                        "409": {"description": "Optimistic concurrency conflict"},
                    },
                }
            },
        },
    }
    return JsonResponse(schema)
