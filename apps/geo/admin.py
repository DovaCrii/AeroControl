from django.contrib import admin

from .models import GeoPlan, GeoPlanHistory, GeoPlanVersion


@admin.register(GeoPlan)
class GeoPlanAdmin(admin.ModelAdmin):
    list_display = ("title", "cost_center", "status", "current_version", "is_active")
    list_filter = ("status", "is_active")
    search_fields = ("title",)
    autocomplete_fields = ()


class _ReadOnlyAdmin(admin.ModelAdmin):
    """Append-only / audit rows: visible but never editable from the admin."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(GeoPlanVersion)
class GeoPlanVersionAdmin(_ReadOnlyAdmin):
    list_display = ("plan", "version_number", "source", "feature_count", "created_at")
    list_filter = ("source",)


@admin.register(GeoPlanHistory)
class GeoPlanHistoryAdmin(_ReadOnlyAdmin):
    list_display = ("plan", "previous_status", "new_status", "changed_by", "created_at")
