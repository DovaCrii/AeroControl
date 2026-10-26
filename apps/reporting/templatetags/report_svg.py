"""LV-378 (PR 2): la tira de vencimientos del informe v2, SVG de servidor.

Reglas, las mismas de `compliance_charts.py` y vigiladas por
`test_lv378_permits_v2.py`:

- **Geometría calculada acá, en Python, y escrita como atributos** (`x`, `y`, `width`,
  `points`…). Ningún `style=""`: los colores viven en `report-a4-v2.css` por clase.
- **Nunca sólo un dibujo**: `role="img"`, `<title>` y `<desc>` con ids únicos por hoja
  (`uid`), y el `<desc>` lleva el texto completo. Las cifras van impresas como
  `<text>`, no sólo dibujadas.
- **La banda se dice con forma y no sólo con color**: ✕ crítico, ▲ por vencer, ●
  vigente, los mismos símbolos del panel (`apps/dashboard/compliance_permits.py`).
  Es lo que sobrevive a una fotocopia en blanco y negro.
- Sin JavaScript, sin librerías y sin animación. Todo texto de fuera se escapa.
"""

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

from apps.reporting.groups import STRIP_DAYS, strip_marks

register = template.Library()

#: Geometría en unidades de SVG = píxeles CSS (el `viewBox` coincide con el ancho).
WIDTH = 690
PLOT_LEFT = 14
PLOT_RIGHT = 614
BAND_TOP = 20
BAND_HEIGHT = 22
LABEL_ROW = 16
LABEL_FIRST = BAND_TOP + BAND_HEIGHT + 14
#: Ancho aproximado de un carácter a 11,5 px en Arial: sólo para que dos rótulos no
#: se pisen. Equivocarse por poco desplaza un rótulo a la fila de abajo, no lo tapa.
CHAR_PX = 6.6
GAP_PX = 8

SYMBOLS = {"critical": "✕", "warning": "▲", "nominal": "●"}
WORDS = {"critical": "Crítico", "warning": "Por vencer", "nominal": "Vigente"}
BAND_NAMES = {
    "critical": "crítico",
    "warning": "por vencer",
    "nominal": "vigente",
}


@register.filter
def band_symbol(band):
    return SYMBOLS.get(band, "")


@register.filter
def band_word(band):
    return WORDS.get(band, "")


def _n(value):
    text = f"{float(value):.2f}".rstrip("0").rstrip(".")
    return text or "0"


def _x(days):
    return PLOT_LEFT + (PLOT_RIGHT - PLOT_LEFT) * min(days, STRIP_DAYS) / STRIP_DAYS


def _mark(band, x, y):
    """La marca de la banda como forma: ✕ (dos trazos), ▲ (triángulo) o ● (círculo)."""
    if band == "critical":
        d = f"M{_n(x - 4)} {_n(y - 4)} L{_n(x + 4)} {_n(y + 4)} M{_n(x - 4)} {_n(y + 4)} L{_n(x + 4)} {_n(y - 4)}"
        return f'<path class="rpt2-mark rpt2-mark-critical" d="{d}" fill="none"/>'
    if band == "warning":
        points = f"{_n(x)},{_n(y - 5)} {_n(x + 5)},{_n(y + 4)} {_n(x - 5)},{_n(y + 4)}"
        return f'<polygon class="rpt2-mark rpt2-mark-warning" points="{points}"/>'
    return f'<circle class="rpt2-mark rpt2-mark-nominal" cx="{_n(x)}" cy="{_n(y)}" r="4.5"/>'


def _place(marks):
    """La fila de rótulo de cada marca: `[(fila, x, ancla, texto, banda, días)]`.

    Cada rótulo va en la primera fila donde no pisa a otro; si no cabe a la derecha
    de su marca, se ancla a su final.
    """
    rows, placed = [], []
    for days, count, code, band in marks:
        text = f"×{count} {code}"
        width = len(text) * CHAR_PX
        x = _x(days)
        anchor = "start"
        left, right = x - 2, x + width
        if right > PLOT_RIGHT + 4:
            anchor, left, right = "end", x - width, x + 2
        row = 0
        while any(
            r == row
            and not (right + GAP_PX < other_left or left - GAP_PX > other_right)
            for r, other_left, other_right in placed
        ):
            row += 1
        placed.append((row, left, right))
        rows.append((row, x, anchor, text, band, days))
    return rows


def _height(rows):
    label_rows = max((row for row, *_rest in rows), default=-1) + 1
    return LABEL_FIRST + max(label_rows, 1) * LABEL_ROW


def strip_height(groups):
    """El alto de la tira para estas faenas: el reparto en hojas lo necesita antes de
    dibujarla, porque crece con las filas de rótulos que hagan falta."""
    marks, _beyond = strip_marks(groups)
    return _height(_place(marks))


def render_expiry_strip(groups, uid):
    """La tira 0–90 días: tres franjas, marcas por faena y fecha, y «›90» aparte."""
    marks, beyond = strip_marks(groups)
    rows = _place(marks)
    height = _height(rows)

    title = "Vencimientos de los permisos vigentes en los próximos 90 días"
    pieces = [
        f"{code} ×{count}: {days} días ({BAND_NAMES.get(band, '')})"
        for days, count, code, band in marks
    ] or ["ningún permiso vigente de faenas con operación"]
    desc = (
        "De 0 a 90 días desde el corte, por faena con operación: "
        + "; ".join(pieces)
        + f". Más de 90 días: {beyond}."
    )
    uid = escape(uid)
    out = [
        f'<svg class="rpt2-strip" width="{WIDTH}" height="{_n(height)}" '
        f'viewBox="0 0 {WIDTH} {_n(height)}" role="img" '
        f'aria-labelledby="{uid}-t {uid}-d" focusable="false">',
        f'<title id="{uid}-t">{escape(title)}</title>',
        f'<desc id="{uid}-d">{escape(desc)}</desc>',
    ]
    zones = (
        (0, 30, "rpt2-zone rpt2-zone-critical"),
        (30, 60, "rpt2-zone rpt2-zone-warning"),
        (60, 90, "rpt2-zone rpt2-zone-nominal"),
    )
    for start, end, css in zones:
        out.append(
            f'<rect class="{css}" x="{_n(_x(start))}" y="{BAND_TOP}" '
            f'width="{_n(_x(end) - _x(start))}" height="{BAND_HEIGHT}"/>'
        )
    for days in (0, 30, 60, 90):
        x = _x(days)
        if days:
            out.append(
                f'<line class="rpt2-tick" x1="{_n(x)}" y1="{BAND_TOP}" '
                f'x2="{_n(x)}" y2="{BAND_TOP + BAND_HEIGHT}"/>'
            )
        anchor = "end" if days == 90 else ("start" if days == 0 else "middle")
        out.append(
            f'<text class="rpt2-axis" x="{_n(x)}" y="{BAND_TOP - 6}" '
            f'text-anchor="{anchor}">{days}{" días" if days == 90 else ""}</text>'
        )
    centre_y = BAND_TOP + BAND_HEIGHT / 2
    # Primero las marcas y sus guías, después todos los rótulos: así una guía que
    # pasa por detrás de un rótulo ajeno queda tapada por su halo blanco y no lo
    # atraviesa.
    for row, x, _anchor, _text, band, _days in rows:
        out.append(_mark(band, x, centre_y))
        if row:
            label_y = LABEL_FIRST + row * LABEL_ROW
            out.append(
                f'<line class="rpt2-lead" x1="{_n(x)}" y1="{BAND_TOP + BAND_HEIGHT}" '
                f'x2="{_n(x)}" y2="{_n(label_y - 12)}"/>'
            )
    for row, x, anchor, text, _band, _days in rows:
        out.append(
            f'<text class="rpt2-label-svg" x="{_n(x)}" '
            f'y="{_n(LABEL_FIRST + row * LABEL_ROW)}" '
            f'text-anchor="{anchor}">{escape(text)}</text>'
        )
    out.append(
        f'<text class="rpt2-beyond" x="{WIDTH}" y="{_n(BAND_TOP + 15)}" '
        f'text-anchor="end">›90: {beyond}</text>'
    )
    out.append("</svg>")
    return "".join(out)


@register.simple_tag
def expiry_strip(groups, uid):
    return mark_safe(render_expiry_strip(groups, uid))  # nosec B308 B703


# -- cobertura por faena (PR 3) ------------------------------------------------


@register.filter
def coverage_state(row):
    """El estado de una faena en la cobertura: `nominal`, `warning`, `renew` (permiso
    a ≤30 días) o `none` (sin permiso vigente). El peor permiso manda, nunca el promedio."""
    if not row.get("permits_in_force"):
        return "none"
    band = row.get("band")
    return "renew" if band == "critical" else (band or "nominal")


COVERAGE_WORDS = {
    "nominal": "Vigente",
    "warning": "Por vencer",
    "renew": "Renovar ahora",
    "none": "Sin habilitación",
}
COVERAGE_BANDS = {
    "nominal": "nominal",
    "warning": "warning",
    "renew": "critical",
    "none": "critical",
}


@register.filter
def coverage_word(state):
    return COVERAGE_WORDS.get(state, "")


@register.filter
def coverage_band(state):
    return COVERAGE_BANDS.get(state, "")


def render_coverage_bar(rows, uid):
    """Barra apilada de la cobertura: `● N vigente | ▲ N por vencer | ✕ N críticos`.

    Un segmento por banda, proporcional a las faenas, con la cifra impresa dentro
    (`<text>`) y la leyenda debajo con forma + palabra + cifra. Los críticos se
    parten en su leyenda: sin permiso (la faena no puede volar) y con permiso a ≤30
    días (hay que renovar ya). Sin faenas no se dibuja barra: se dice.
    """
    rows = list(rows)
    states = [coverage_state(row) for row in rows]
    count = {key: states.count(key) for key in COVERAGE_WORDS}
    critical = count["renew"] + count["none"]
    total = len(rows)
    height = 44
    desc = (
        f"Cobertura de {total} Centros de Costo con operación: {count['nominal']} "
        f"vigentes, {count['warning']} por vencer, {critical} críticos "
        f"({count['none']} sin habilitación y {count['renew']} con permiso a 30 "
        "días o menos)."
    )
    uid = escape(uid)
    out = [
        f'<svg class="rpt2-covbar" width="{WIDTH}" height="{height}" '
        f'viewBox="0 0 {WIDTH} {height}" role="img" '
        f'aria-labelledby="{uid}-t {uid}-d" focusable="false">',
        f'<title id="{uid}-t">Cobertura por Centro de Costo</title>',
        f'<desc id="{uid}-d">{escape(desc)}</desc>',
    ]
    segments = (
        ("nominal", count["nominal"], "rpt2-seg rpt2-seg-nominal"),
        ("warning", count["warning"], "rpt2-seg rpt2-seg-warning"),
        ("critical", critical, "rpt2-seg rpt2-seg-critical"),
    )
    x = 0.0
    for _key, n, css in segments:
        if not n or not total:
            continue
        width = WIDTH * n / total
        out.append(
            f'<rect class="{css}" x="{_n(x)}" y="0" width="{_n(max(width - 2, 1))}" '
            f'height="22"/>'
        )
        if width >= 26:
            out.append(
                f'<text class="rpt2-seg-n" x="{_n(x + (width - 2) / 2)}" y="16" '
                f'text-anchor="middle">{n}</text>'
            )
        x += width
    legend = (
        (
            "nominal",
            f"{count['nominal']} vigente{'s' if count['nominal'] != 1 else ''}",
        ),
        ("warning", f"{count['warning']} por vencer (31–60 d)"),
        (
            "critical",
            f"{critical} crítico{'s' if critical != 1 else ''}: "
            f"{count['none']} sin habilitación, {count['renew']} con permiso a ≤30 d",
        ),
    )
    cursor = 0.0
    for band, text in legend:
        out.append(_mark(band, cursor + 5, 35))
        out.append(
            f'<text class="rpt2-covbar-label" x="{_n(cursor + 15)}" y="39">'
            f"{escape(text)}</text>"
        )
        cursor += 15 + len(text) * CHAR_PX + 22
    out.append("</svg>")
    return "".join(out)


@register.simple_tag
def coverage_bar(rows, uid):
    return mark_safe(render_coverage_bar(rows, uid))  # nosec B308 B703
