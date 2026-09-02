"""La respuesta cuando `django-axes` retiene una cuenta.

Hasta ahora el bloqueo devolvía el **403 pelado** que trae `axes` por omisión:
un párrafo en inglés, sin la chapa de la aplicación, sin decir cuánto dura ni
qué hacer. Y el formulario de acceso, del otro lado, decía *"probá de nuevo"* —
que es justo lo que no funciona mientras el bloqueo está puesto.

Se usa `AXES_LOCKOUT_CALLABLE` y no `AXES_LOCKOUT_TEMPLATE` porque la plantilla
necesita **la duración real de la espera**, y ese número vive en
`AXES_COOLOFF_TIME`: escrito a mano en el HTML se desincroniza en silencio el
día que alguien cambie el ajuste, y una pantalla que promete quince minutos
cuando son sesenta es peor que una que no promete nada.

⚠️ **Se renderiza sin `request`**, que es la lección de `LV-215`: `render` corre
los context processors, y el de `compliance` consulta la base y pide
`request.user.has_perm(...)`. Una pantalla de error que se apoya en el orden de
los middleware no es autónoma — y ésta la ve precisamente alguien que **no**
tiene sesión.
"""

from django.conf import settings
from django.http import HttpResponseForbidden
from django.template.loader import render_to_string

# Cuando `AXES_COOLOFF_TIME` no está configurado el bloqueo no expira solo, y la
# pantalla no puede prometer una espera. Se muestra igual, sin el plazo: decir
# "esperá 0 minutos" sería mentir en la dirección peligrosa.
DEFAULT_COOLOFF_MINUTES = None


def cooloff_minutes():
    """Los minutos de espera configurados, o `None` si no expira sola."""
    cooloff = getattr(settings, "AXES_COOLOFF_TIME", None)
    if cooloff is None:
        return DEFAULT_COOLOFF_MINUTES
    if isinstance(cooloff, (int, float)):
        # `axes` acepta horas como número suelto.
        return int(cooloff * 60)
    seconds = getattr(cooloff, "total_seconds", None)
    if seconds is None:
        return DEFAULT_COOLOFF_MINUTES
    return max(1, int(seconds() // 60))


def lockout_response(request, credentials=None, *args, **kwargs):
    """La pantalla de cuenta retenida, con la chapa de la aplicación.

    Devuelve 403 y no 200: para un cliente automático —y para el registro del
    proxy— esto **es** un acceso denegado, y responder 200 lo haría indistinguible
    de un formulario de acceso servido con normalidad.
    """
    body = render_to_string(
        "registration/lockout.html",
        {
            "cooloff_minutes": cooloff_minutes(),
            "support_contact": getattr(settings, "SUPPORT_CONTACT", ""),
        },
    )
    return HttpResponseForbidden(body)
