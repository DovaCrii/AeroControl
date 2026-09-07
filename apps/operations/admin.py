from django.contrib import admin

from .models import (
    FlightPermission,
    FlightRecord,
    PreflightChecklist,
    PreflightChecklistItem,
)

admin.site.register([FlightPermission, FlightRecord])


class PreflightChecklistItemInline(admin.TabularInline):
    model = PreflightChecklistItem
    extra = 1


@admin.register(PreflightChecklist)
class PreflightChecklistAdmin(admin.ModelAdmin):
    """`UX-29`: las listas se configuran acá y no en una pantalla propia.

    Es una decisión de alcance y conviene que esté escrita. Configurar la lista
    es un acto **raro** —se hace una vez y se toca cuando cambia el
    procedimiento— y de una sola persona; darle pantalla propia habría sumado
    una entrada de menú que casi nadie usa a un menú que `LV-170` ya tuvo que
    plegar por tener veinte. Lo que se usa todos los días —contestarla y
    firmarla— sí tiene pantalla, colgada del vuelo.

    ⚠️ **`PreflightCheck` y `PreflightAnswer` no se registran, y eso es el
    punto.** Un chequeo firmado es evidencia; dejarlo editable desde el
    administrador sería dejar una puerta trasera a lo que la propia clase
    prohíbe. El administrador de Django no es "modo experto": es la misma base,
    sin los guardias.
    """

    list_display = ("name", "model_keywords", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "model_keywords")
    inlines = [PreflightChecklistItemInline]
