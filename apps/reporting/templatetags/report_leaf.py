"""R3: dibujar una hoja del payload, o la marca de que todavía no hay dato.

**La regla que manda en todo el informe se aplica acá y en un solo lugar**: el
informe nunca inventa un dato. Sin valor en la base el campo se dibuja en ámbar
punteado —la convención que el propio lienzo del diseño anotó— y nunca como
cero, porque un cero afirma ("hay cero") y la ausencia no afirma nada.

Hay **dos** clases de pendiente y conviene no confundirlas al leer una página:

1. **Hoja con `value: None`.** El colector la buscó y no estaba. Entra en
   `ReportRun.missing_fields`, que es la evidencia guardada de qué faltaba
   cuando el informe se emitió.
2. **Sección que el payload todavía no trae** (`{% pending %}`). Ningún colector
   la produce aún, así que no puede entrar en `missing_fields`: no hay ruta que
   nombrar. Se dibuja igual para que la página no mienta por omisión, y el
   rótulo dice qué fila del plan la va a llenar.
"""

from django import template

register = template.Library()


@register.inclusion_tag("reporting/_leaf.html")
def leaf(node, suffix=""):
    """El valor de una hoja `{"value", "source", "cutoff"}`, o su pendiente.

    Acepta también lo que no es una hoja —una clave que el payload de un
    informe viejo no tenía— y lo trata como pendiente. Un informe congelado hace
    meses se re-renderiza con la plantilla de hoy, así que la plantilla no puede
    dar por hecha la forma del payload que le toque.
    """
    if isinstance(node, dict) and "value" in node and "source" in node:
        return {"value": node["value"], "source": node["source"], "suffix": suffix}
    return {"value": None, "source": "", "suffix": suffix}


@register.inclusion_tag("reporting/_pending.html")
def pending(what, row=""):
    """Un bloque entero que el payload todavía no produce.

    `row` nombra la fila del plan que lo va a llenar, para que quien lea el
    borrador sepa si es un hueco de carga o trabajo pendiente de la aplicación.
    """
    return {"what": what, "row": row}
