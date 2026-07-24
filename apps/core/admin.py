from django.contrib import admin
from .models import (
    AuditEvent,
    BackupConfig,
    JobRun,
    OperationalTenant,
    TenantMembership,
)

admin.site.register(BackupConfig)
admin.site.register([OperationalTenant, TenantMembership])


@admin.register(JobRun)
class JobRunAdmin(admin.ModelAdmin):
    """Read-only: job history is written by the jobs themselves."""

    list_display = ("command", "started_at", "finished_at", "result", "summary")
    list_filter = ("command", "result")
    search_fields = ("command", "summary")
    readonly_fields = [field.name for field in JobRun._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor", "action", "method", "path", "status_code")
    list_filter = ("action", "method", "status_code")
    search_fields = (
        "path",
        "request_id",
        "object_id",
        "model_label",
        "actor__username",
    )
    readonly_fields = [field.name for field in AuditEvent._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
