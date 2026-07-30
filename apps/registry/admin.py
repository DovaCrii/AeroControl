from django.contrib import admin

from .models import (
    Aircraft,
    AircraftAssignment,
    Assignment,
    CostCenter,
    Operator,
    OperatorAssignment,
    Qualification,
    QualificationType,
    ResourceMovementLog,
)

admin.site.register(
    [
        CostCenter,
        Aircraft,
        Operator,
        Assignment,
        OperatorAssignment,
        AircraftAssignment,
        Qualification,
        QualificationType,
    ]
)


@admin.register(ResourceMovementLog)
class ResourceMovementLogAdmin(admin.ModelAdmin):
    """Read-only: the movement log is append-only (writes come from the signal)."""

    list_display = ("resource_kind", "resource_id", "movement", "created_at")
    list_filter = ("resource_kind", "movement")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
