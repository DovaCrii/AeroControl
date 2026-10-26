"""Gráficos SVG de servidor para «Cumplimiento» (LV-359, fase 2): `ring`, `hbar` y `sparkline`.

Reglas, todas vigiladas por `test_lv359_compliance_charts.py`:

- **Geometría calculada acá, en Python, y escrita como atributos** (`stroke-dasharray`, `width`, `points`…).
  Ningún `style=""`: la CSP de la app lo bloquea y los colores viven en `identity.css` por clase.
- **Nunca sólo un dibujo**: cada `<svg>` es `role="img"` con `<title>` y `<desc>` que dicen las cifras, y
  la plantilla imprime la misma cifra al lado (un lector de pantalla no recorre el interior de una imagen).
- Sin JavaScript, sin librerías y sin animación.
- Todo texto que llega de fuera se escapa; el HTML devuelto se arma sólo con números formateados acá.
"""

from math import pi

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()


def _n(value):
    """Un número para un atributo SVG: dos decimales como máximo y sin ceros de relleno."""
    text = f"{float(value):.2f}".rstrip("0").rstrip(".")
    return text or "0"


def _head(uid, title, desc, width, height, css):
    """Apertura del `<svg>` con su `<title>` y `<desc>` enlazados (`aria-labelledby`)."""
    uid = escape(uid)
    return (
        f'<svg class="id-cx-svg {css}" width="{_n(width)}" height="{_n(height)}" '
        f'viewBox="0 0 {_n(width)} {_n(height)}" role="img" '
        f'aria-labelledby="{uid}-t {uid}-d" focusable="false">'
        f'<title id="{uid}-t">{escape(title)}</title>'
        f'<desc id="{uid}-d">{escape(desc)}</desc>'
    )


def render_ring(segments, uid, title, desc, center="", size=96, stroke=12, gap=1.5):
    """Anillo de segmentos. `segments`: [(clase_css, valor)]. El valor 0 no se dibuja.

    Cada segmento es un círculo con `stroke-dasharray` (largo visible, resto) y `stroke-dashoffset`
    (acumulado), girado -90° para que el primero arranque arriba. Con varios segmentos se deja un
    hueco de `gap` entre ellos, que es lo que separa los tramos que comparten color (≤7 y ≤15 días).
    """
    segments = [(css, int(value)) for css, value in segments if int(value) > 0]
    total = sum(value for _css, value in segments)
    mid = size / 2
    radius = (size - stroke) / 2
    circumference = 2 * pi * radius
    parts = [
        _head(uid, title, desc, size, size, "id-cx-ring-svg"),
        f'<circle class="id-cx-track" cx="{_n(mid)}" cy="{_n(mid)}" r="{_n(radius)}" '
        f'fill="none" stroke-width="{_n(stroke)}"/>',
    ]
    drawn = 0.0
    many = len(segments) > 1
    for css, value in segments:
        length = circumference * value / total
        visible = max(length - gap, 0.5) if many else length
        parts.append(
            f'<circle class="id-cx-seg {escape(css)}" cx="{_n(mid)}" cy="{_n(mid)}" '
            f'r="{_n(radius)}" fill="none" stroke-width="{_n(stroke)}" '
            f'stroke-dasharray="{_n(visible)} {_n(circumference - visible)}" '
            f'stroke-dashoffset="{_n(-drawn)}" transform="rotate(-90 {_n(mid)} {_n(mid)})"/>'
        )
        drawn += length
    if center != "":
        parts.append(
            f'<text class="id-cx-ring-n" x="{_n(mid)}" y="{_n(mid)}" text-anchor="middle" '
            f'dominant-baseline="central">{escape(center)}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def render_hbar(bars, uid, title, desc, width=300, row=26, label_width=96):
    """Barras horizontales. `bars`: [(rótulo, valor, clase_css)]; la cifra va impresa al final de cada barra."""
    bars = [(label, int(value), css) for label, value, css in bars]
    top = max([value for _l, value, _c in bars] + [1])
    value_width = 34
    room = max(width - label_width - value_width, 10)
    height = row * len(bars)
    parts = [_head(uid, title, desc, width, height, "id-cx-hbar-svg")]
    for index, (label, value, css) in enumerate(bars):
        y = index * row
        text_y = y + row / 2
        size = 0 if value <= 0 else max(room * value / top, 2)
        parts.append(
            f'<text class="id-cx-svg-text" x="0" y="{_n(text_y)}" '
            f'dominant-baseline="central">{escape(label)}</text>'
        )
        if size:
            parts.append(
                f'<rect class="id-cx-bar {escape(css)}" x="{_n(label_width)}" '
                f'y="{_n(y + 4)}" width="{_n(size)}" height="{_n(row - 8)}" rx="3"/>'
            )
        parts.append(
            f'<text class="id-cx-svg-text id-cx-svg-value" x="{_n(label_width + size + 6)}" '
            f'y="{_n(text_y)}" dominant-baseline="central">{value}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def render_sparkline(values, uid, title, desc, width=120, height=28, pad=3):
    """Línea mínima de una serie. Con un solo punto se dibuja sólo el punto; sin puntos, nada de línea."""
    values = [float(v) for v in values]
    parts = [_head(uid, title, desc, width, height, "id-cx-spark-svg")]
    if values:
        low, high = min(values), max(values)
        span = (high - low) or 1.0
        step = (width - 2 * pad) / (len(values) - 1) if len(values) > 1 else 0
        points = [
            (
                pad + index * step,
                height - pad - (value - low) / span * (height - 2 * pad),
            )
            for index, value in enumerate(values)
        ]
        if len(points) > 1:
            joined = " ".join(f"{_n(x)},{_n(y)}" for x, y in points)
            parts.append(
                f'<polyline class="id-cx-spark" fill="none" stroke-width="2" points="{joined}"/>'
            )
        x, y = points[-1]
        parts.append(
            f'<circle class="id-cx-spark-end" cx="{_n(x)}" cy="{_n(y)}" r="2.5"/>'
        )
    parts.append("</svg>")
    return "".join(parts)


def render_daybar(days, width=128, height=14, horizon=90, marks=(30, 60)):
    """Barra de días 0 a `horizon` con marcas en 30 y 60 (LV-376, fase 1b). Decorativa: `aria-hidden`.

    La fecha y «en N días» van impresas al lado, así que el dibujo no lleva `<title>` ni `role`. El
    color sale de la clase (`id-cx-day--soon|mid|far`), nunca de un `style`; la geometría, de atributos.
    Escala de PERMISOS: hasta 30 días ámbar, hasta 60 cian, más allá verde.
    """
    days = int(days)
    clamped = min(max(days, 0), horizon)
    fill = max(width * clamped / horizon, 3)
    css = "soon" if days <= marks[0] else ("mid" if days <= marks[1] else "far")
    top, bar = 3, height - 6
    parts = [
        f'<svg class="id-cx-svg id-cx-daybar" width="{_n(width)}" height="{_n(height)}" '
        f'viewBox="0 0 {_n(width)} {_n(height)}" aria-hidden="true" focusable="false">',
        f'<rect class="id-cx-day-track" x="0" y="{top}" width="{_n(width)}" '
        f'height="{bar}" rx="3"/>',
        f'<rect class="id-cx-day-fill id-cx-day--{css}" x="0" y="{top}" '
        f'width="{_n(fill)}" height="{bar}" rx="3"/>',
    ]
    for mark in marks:
        x = width * mark / horizon
        parts.append(
            f'<line class="id-cx-day-mark" x1="{_n(x)}" y1="0" x2="{_n(x)}" y2="{_n(height)}"/>'
        )
    parts.append("</svg>")
    return "".join(parts)


@register.simple_tag
def daybar(days, width=128):
    return mark_safe(render_daybar(days, width))  # nosec B308 B703


# Retirada de PANTALLA (LV-367, fase 4), no de código: «Cumplimiento» ya no dibuja anillos, pero la etiqueta
# sigue registrada y probada. Condición de cierre (paso 2): borrar `ring`, `render_ring` y las reglas
# `.id-cx-seg*`/`.id-cx-track`/`.id-cx-ring-*` de `identity.css` cuando NINGUNA plantilla la use durante un
# despliegue completo (`grep "{% ring"` en `templates/` sin resultados en `main` y en `p340`).
@register.simple_tag
def ring(segments, uid, title, desc, center="", size=96):
    return mark_safe(render_ring(segments, uid, title, desc, center, size))  # nosec B308 B703


@register.simple_tag
def hbar(bars, uid, title, desc, width=300):
    return mark_safe(render_hbar(bars, uid, title, desc, width))  # nosec B308 B703


@register.simple_tag
def sparkline(values, uid, title, desc, width=120):
    return mark_safe(render_sparkline(values, uid, title, desc, width))  # nosec B308 B703
