from rest_framework import serializers
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
