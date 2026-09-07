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
