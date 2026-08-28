"""LV-174: la tipografía dice lo mismo en toda la app.

Observación del usuario, mirando varios módulos: *"a veces la fuente o el
engrosado es diferente; normalizar y que sea claro en toda la app"*. Tenía
razón, y la medición explica **por qué** se percibía arbitrario.

**Los pesos declarados no eran los pesos dibujados.** La app pedía siete
(400, 500, 600, 650, 700, 750, 800) y el navegador dibujaba **cuatro**. Medido
con la pila real (`system-ui`, sin webfont), comparando el ancho del mismo texto
a 16 px:

| declarado | ancho | |
|---|---|---|
| 400 | 193.20 px | |
| 500 y 600 | 197.75 px | **idénticos** |
| 650, 700 y 750 | 203.72 px | **idénticos** |
| 800 | 212.50 px | |

O sea que `650` y `750` eran ficción: se dibujan exactamente como `700`. Un
archivo pedía 650 y el de al lado 700 creyendo distinguirse, y en pantalla eran
lo mismo — de ahí la sensación de que el engrosado está puesto al azar. Estaba
puesto al azar.

**La normalización es invisible a propósito**: cada peso se reemplazó por el que
ya se estaba dibujando (500→600, 650→700, 750→700), así que ni un píxel se movió
y lo que cambió es que el código dejó de afirmar diferencias que no existen.

**Y los tamaños eran veintiséis.** En la banda del texto chico había pares
separados por 0,32 px —`0.72` y `0.73`, `0.9` y `0.92`— que nadie puede ver pero
que obligan a elegir entre dos valores igualmente arbitrarios cada vez que se
escribe una regla. Se juntaron en cuatro escalones con una deriva máxima de
0,04 rem (0,64 px). Los títulos **no** se tocaron: ahí la diferencia sí se ve y
es jerarquía deliberada.

Verificado después del cambio: la barra lateral sigue pidiendo exactamente los
mismos 248 px para su fila más larga.
"""

import re
from pathlib import Path

from django.conf import settings

CSS = Path(settings.BASE_DIR) / "static" / "css" / "app.css"

# Los cuatro que el navegador dibuja distinto. Pedir otro no es un matiz: es
# escribir una diferencia que la pantalla no puede mostrar.
RENDERED_WEIGHTS = {"400", "600", "700", "800"}

# La banda del texto chico, en escalones que sí se distinguen. `0.95` es el
# `body` —la raíz de la escala—, y los tres restantes son deliberados y están
# documentados donde se usan: la bajada de la marca, la insignia del menú
# plegado y el rótulo de la hoja SIGO.
SMALL_TEXT_STEPS = {"0.72rem", "0.78rem", "0.85rem", "0.92rem"}
DELIBERATE_SMALL = {"0.58rem", "0.62rem", "0.66rem", "0.95rem"}


def _declarations(pattern):
    return re.findall(pattern, CSS.read_text(encoding="utf-8"))


def test_only_the_weights_the_browser_can_draw():
    used = set(_declarations(r"font-weight:\s*(\d+)"))

    assert used <= RENDERED_WEIGHTS, (
        f"pesos que no se dibujan distinto: {sorted(used - RENDERED_WEIGHTS)}. "
        "Medido: 500 se dibuja como 600, y 650 y 750 como 700 — ver LV-174"
    )


def test_the_small_text_band_uses_the_scale():
    """Dos tamaños separados por 0,32 px no son un matiz, son una moneda al aire."""
    used = {
        size
        for size in _declarations(r"font-size:\s*([0-9.]+rem)")
        if float(size.replace("rem", "")) < 1
    }

    assert used <= SMALL_TEXT_STEPS | DELIBERATE_SMALL, (
        f"tamaños fuera de la escala: {sorted(used - SMALL_TEXT_STEPS - DELIBERATE_SMALL)}"
    )


def test_the_scale_did_not_grow_a_second_generation():
    """El proyecto ya arrastró generaciones de tokens conviviendo.

    Por eso esto normaliza **los valores** en vez de agregar una capa de tokens
    tipográficos encima de la existente: una segunda generación resuelve la
    inconsistencia de hoy y crea la de mañana, con las dos vivas a la vez.
    """
    css = CSS.read_text(encoding="utf-8")

    assert "--ac-font-size" not in css
    assert "--ac-text-xs" not in css
