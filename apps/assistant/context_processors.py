"""`LV-332`: lo que necesita el panel flotante del asistente en cualquier pantalla.

Devuelve `assistant_panel` (¿se dibuja el botón y el panel?) y las sugerencias de la pantalla.
Apagado, o sin `view_flightpermission`, el panel no existe: ni botón ni HTML. El candado es el
mismo `assistant_available()` de la pantalla; este módulo no lo duplica.
"""

from django.utils.translation import gettext_lazy as _

from apps.core.context_processors import module_for_url_name

SUGGESTIONS_BY_MODULE = {
    "flight": (
        _("Which permits expire in the next 30 days?"),
        _("Which sites have no current permit?"),
    ),
}
DEFAULT_SUGGESTIONS = (_("Which sites have no current permit?"),)


def assistant_panel(request):
    from .views import assistant_available

    user = getattr(request, "user", None)
    if (
        user is None
        or not user.is_authenticated
        or not assistant_available()
        or not user.has_perm("operations.view_flightpermission")
    ):
        return {"assistant_panel": False}
    match = getattr(request, "resolver_match", None)
    module = module_for_url_name(getattr(match, "url_name", ""))
    return {
        "assistant_panel": True,
        "assistant_suggestions": SUGGESTIONS_BY_MODULE.get(module, DEFAULT_SUGGESTIONS),
    }
