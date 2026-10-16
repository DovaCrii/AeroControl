from django.contrib import admin

from .models import AssistantUsage


@admin.register(AssistantUsage)
class AssistantUsageAdmin(admin.ModelAdmin):
    """Solo lectura: lo escribe el servicio, no una persona. No hay texto de preguntas."""

    list_display = ("created_at", "user", "outcome", "rounds", "total_tokens", "ms")
    list_filter = ("outcome",)
    readonly_fields = [field.name for field in AssistantUsage._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
