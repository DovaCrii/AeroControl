from rest_framework import serializers
from django.http import JsonResponse
from rest_framework.permissions import DjangoModelPermissions, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import KanbanTask


class KanbanTaskSerializer(serializers.ModelSerializer):
    state = serializers.CharField(source="stage.status_type", read_only=True)
    stage_name = serializers.CharField(source="stage.name", read_only=True)
    board_name = serializers.CharField(source="board.name", read_only=True)
    progress = serializers.IntegerField(source="checklist_progress", read_only=True)

    class Meta:
        model = KanbanTask
        fields = ["id", "title", "board", "board_name", "stage", "stage_name", "state", "priority", "due_date", "progress", "updated_at"]


class KanbanTaskApiView(APIView):
    permission_classes = [IsAuthenticated, DjangoModelPermissions]

    def get_queryset(self):
        return KanbanTask.objects.filter(is_active=True, board__is_active=True).select_related("board", "stage")

    def get(self, request):
        queryset = self.get_queryset()
        if request.query_params.get("priority") in dict(KanbanTask.PRIORITIES):
            queryset = queryset.filter(priority=request.query_params["priority"])
        return Response(KanbanTaskSerializer(queryset[:100], many=True).data)


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
