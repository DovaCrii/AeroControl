"""SVG de servidor del centelleo GNSS (LV-367, fases 2 y 3): la banda compacta de la franja del panel.

Mismas reglas que `compliance_charts` (las vigila `test_lv367_gnss_day.py`):

- **Geometría calculada en Python y escrita como atributos.** Ningún `style=""` (la CSP lo bloquea): los
  colores viven en `identity.css` por clase (`id-gx-*`).
- **Nunca sólo un dibujo:** cada `<svg>` es `role="img"` con `<title>` y `<desc>` que dicen la ventana y la
  hora, y la plantilla imprime la misma cifra al lado.
- **Sin escala de intensidad.** La fuente no publica ningún índice (S4, ROTI, TEC, Kp): el dibujo muestra
  CUÁNDO es la ventana típica, jamás cuánto. La ventana va con trama, no sólo con color.
- Sin JavaScript ni animación. Todo texto se escapa; el HTML sólo se arma con números formateados acá.
"""

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _

register = template.Library()

WIDTH = 288
BAR_Y = 8
BAR_H = 16
HEIGHT = 44


def _n(value):
    """Un número para un atributo SVG: dos decimales como máximo y sin ceros de relleno."""
    text = f"{float(value):.2f}".rstrip("0").rstrip(".")
    return text or "0"


def _x(fraction):
    return fraction * WIDTH


def describe(day):
    """`(título, descripción)` del dibujo, en el idioma activo; dicen lo mismo que el texto impreso al lado."""
    title = _("Typical scintillation window over the next 24 hours")
    if day["window_label"]:
        desc = _(
            "Typical window: %(window)s. The marker is the current time, %(now)s. "
            "Statistical reference, not a measurement."
        ) % {"window": day["window_label"], "now": day["now_label"]}
    else:
        desc = _(
            "No typical window in these 24 hours. The marker is the current time, %(now)s. "
            "Statistical reference, not a measurement."
        ) % {"now": day["now_label"]}
    return title, desc


def render_day_band(day, uid):
    """La banda compacta de 24 horas (12:00 a 12:00): pista, ventana con trama, «ahora» y el eje cada 6 horas."""
    uid = escape(uid)
    title, desc = describe(day)
    parts = [
        f'<svg class="id-gx-svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" '
        f'role="img" aria-labelledby="{uid}-t {uid}-d" focusable="false">'
        f'<title id="{uid}-t">{escape(title)}</title>'
        f'<desc id="{uid}-d">{escape(desc)}</desc>',
        f'<defs><pattern id="{uid}-h" width="6" height="6" patternUnits="userSpaceOnUse" '
        f'patternTransform="rotate(45)"><line class="id-gx-hatch" x1="0" y1="0" x2="0" y2="6" '
        f'stroke-width="2.5"/></pattern></defs>',
        f'<rect class="id-gx-track" x="0.5" y="{BAR_Y}" width="{WIDTH - 1}" height="{BAR_H}" rx="4"/>',
    ]
    for x0, x1 in day["window"]:
        parts.append(
            f'<rect class="id-gx-win" x="{_n(_x(x0))}" y="{BAR_Y}" width="{_n(_x(x1 - x0))}" '
            f'height="{BAR_H}" fill="url(#{uid}-h)"/>'
        )
    now_x = _x(day["now"])
    parts.append(
        f'<line class="id-gx-now" x1="{_n(now_x)}" y1="{BAR_Y - 4}" x2="{_n(now_x)}" '
        f'y2="{BAR_Y + BAR_H + 2}" stroke-width="2"/>'
        f'<circle class="id-gx-now-dot" cx="{_n(now_x)}" cy="{BAR_Y - 4}" r="3"/>'
    )
    last = len(day["ticks"]) - 1
    for index, (fraction, label) in enumerate(day["ticks"]):
        anchor = "start" if index == 0 else "end" if index == last else "middle"
        parts.append(
            f'<text class="id-gx-tick" x="{_n(_x(fraction))}" y="{HEIGHT - 4}" '
            f'text-anchor="{anchor}">{escape(label)}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


@register.simple_tag
def gnss_day_band(day, uid):
    return mark_safe(render_day_band(day, uid))  # nosec B308 B703
