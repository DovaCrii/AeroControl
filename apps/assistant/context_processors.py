"""`LV-332`: lo que necesita el panel flotante del asistente en cualquier pantalla.

Devuelve `assistant_panel` (¿se dibuja el botón y el panel?) y las sugerencias de la pantalla.
Apagado, o sin el permiso de NINGUNA herramienta (`LV-340`), el panel no existe: ni botón ni HTML. El candado es el
mismo `assistant_available()` de la pantalla; este módulo no lo duplica.
"""

from django.conf import settings
from django.utils.translation import gettext_lazy as _

from apps.core.context_processors import module_for_url_name

from .tools import user_has_any_tool_permission

# `LV-346`: (texto, módulo de la pantalla donde se ofrece primero, permiso de la herramienta que la
# contesta). ÚNICO lugar donde se decide qué se sugiere: una sugerencia sólo aparece si la persona
# tiene el permiso de la herramienta que la contesta, para que nunca se ofrezca una pregunta que
# acabaría en error de permiso. Al sumar una herramienta, sumar su sugerencia aquí.
SUGGESTIONS = (
    (
        _("Which permits expire in the next 30 days?"),
        "flight",
        "operations.view_flightpermission",
    ),
    (
        _("Which sites have no current permit?"),
        "flight",
        "operations.view_flightpermission",
    ),
    (
        _("Which aircraft have insurance expiring soon?"),
        "registry",
        "registry.view_aircraft",
    ),
    (_("What is the fleet availability?"), "registry", "registry.view_aircraft"),
    (
        _("Which maintenance is coming up or still to be defined?"),
        "maintenance",
        "maintenance.view_maintenancerecord",
    ),
    (
        _("Which company documents expire in 30 days?"),
        "compliance",
        "compliance.view_document",
    ),
    (_("Open alerts by urgency"), "compliance", "compliance.view_alert"),
)
MAX_SUGGESTIONS = 3


def suggestions_for(user, module):
    """Sugerencias de la pantalla `module` que `user` puede ver; si ninguna de esa pantalla le
    sirve, las primeras que sí puede ver de todo el catálogo."""
    allowed = [(t, m) for t, m, perm in SUGGESTIONS if user.has_perm(perm)]
    here = [t for t, m in allowed if m == module]
    return (here or [t for t, _m in allowed])[:MAX_SUGGESTIONS]


def assistant_panel(request):
    from .views import assistant_available

    user = getattr(request, "user", None)
    if (
        user is None
        or not user.is_authenticated
        or not assistant_available()
        or not user_has_any_tool_permission(user)
    ):
        return {"assistant_panel": False}
    match = getattr(request, "resolver_match", None)
    module = module_for_url_name(getattr(match, "url_name", ""))
    return {
        "assistant_panel": True,
        "assistant_suggestions": suggestions_for(user, module),
        "assistant_allow_copy": bool(settings.AI_ASSISTANT_ALLOW_COPY),
    }
