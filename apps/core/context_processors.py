"""`UX-31`: los atajos del rol, disponibles en toda página.

Es un context processor y no un `{% include %}` con lógica porque el menú vive en
`base.html`, o sea en **todas** las pantallas: calcularlo en cada vista habría
significado repetirlo en cincuenta vistas y olvidarlo en la cincuenta y una.

El costo es una consulta de grupos por petición para quien tiene rol, y se paga a
propósito: la alternativa —guardarlo en la sesión— deja a alguien con los atajos
de un rol que ya no tiene hasta que vuelva a entrar, y en una aplicación donde el
rol decide qué se ve eso es exactamente el tipo de desfase que no conviene.
"""

from django.urls import reverse

from .roles import SHORTCUT_LABELS, shortcuts_for


def role_shortcuts(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    return {
        "role_shortcuts": [
            {
                "url": reverse(name),
                "url_name": name,
                # El rótulo llega en inglés y lo traduce la plantilla, igual que
                # el resto del menú: así los dos sitios que nombran la misma
                # pantalla salen del mismo msgid y no pueden divergir.
                "label": SHORTCUT_LABELS[name],
            }
            for name in shortcuts_for(user)
        ]
    }


# LV-324: la sección de la barra lateral a la que pertenece cada pantalla (mismos valores que el
# `data-nav-group` de `base.html`). Se busca por nombre de URL y, si no está, quitando segmentos
# desde el final (`aircraft-update` -> `aircraft`), así las altas, ediciones y fichas heredan el
# módulo de su lista sin enumerarlas.
NAV_MODULE_STEMS = {
    "flight": (
        "can-i-fly",
        "permission",
        "flight-request",
        "geo-plan",
        "record",
        "calendar",
        "ops-calendar",
        "preflight",
        "weather-review",
        "notam-review",
    ),
    "compliance": (
        "document",
        "documenttype",
        "work-tray",
        "alert",
        "alertrule",
        "kanban",
        "monthly-review",
        "monthly-close",
        "operational-records",
        "nonconformity",
        "company-documents",
        "deliverable",
        "task",
        "board",
        "label",
        "stage",
        "checklist",
        "workboard",
        "history",
    ),
    "reports": ("registry-roster", "compliance-report", "monthly-report"),
    "maintenance": ("maintenance",),
    "registry": (
        "costcenter",
        "aircraft",
        "operator",
        "qualification",
        "qualificationtype",
        "assessment",
    ),
    "inventory": (
        "operatorassignment",
        "aircraftassignment",
        "battery",
        "resourcemovementlog",
    ),
}
_STEM_TO_MODULE = {
    stem: module for module, stems in NAV_MODULE_STEMS.items() for stem in stems
}


def module_for_url_name(url_name):
    parts = (url_name or "").split("-")
    while parts:
        module = _STEM_TO_MODULE.get("-".join(parts))
        if module:
            return module
        parts.pop()
    return ""


def nav_module(request):
    match = getattr(request, "resolver_match", None)
    return {"nav_module": module_for_url_name(getattr(match, "url_name", ""))}
