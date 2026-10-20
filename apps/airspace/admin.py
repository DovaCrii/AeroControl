from django.contrib import admin

from .models import AirspaceFeature, AirspaceSnapshot


class _ReadOnlyAdmin(admin.ModelAdmin):
    """The catalog is written only by `import_airspace_zones`, never by hand."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AirspaceSnapshot)
class AirspaceSnapshotAdmin(_ReadOnlyAdmin):
    list_display = (
        "fetched_at",
        "source_name",
        "feature_count",
        "added",
        "changed",
        "archived",
        "is_current",
    )
    list_filter = ("is_current",)


@admin.register(AirspaceFeature)
class AirspaceFeatureAdmin(_ReadOnlyAdmin):
    list_display = ("code", "name", "kind", "folder", "region", "is_active")
    list_filter = ("kind", "is_active", "folder")
    search_fields = ("code", "name", "raw_name")
    exclude = ("geometry",)
