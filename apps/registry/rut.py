"""LV-143: el RUT como llave natural — forma canónica y dígito verificador.

El RUT es el identificador con el que una persona aparece en la credencial de la
DGAC, en el contrato y en el Capítulo 1, y hasta ahora el campo aceptaba
cualquier cosa: sin formato, sin dígito verificador y sin unicidad. Dos fichas de
la misma persona con el RUT escrito distinto (`12.345.678-9` y `12345678-9`) eran
para la app dos personas.

**No se aplica en `save()`, a propósito.** Ésa es la trampa que
`Aircraft.serial_number` documenta en LV-142: normalizar después de validar deja
la comprobación de unicidad comparando otra cosa. Acá se aplica en `clean()` y en
el formulario, donde todavía se puede avisar.
"""

import re

_KEEP = re.compile(r"[^0-9Kk]")


def normalize_rut(raw):
    """`"12.345.678-k"` -> `"12345678-K"`. `""` cuando no hay nada.

    Forma canónica sin puntos y con guión: compara, ordena y no depende de cómo
    alguien tipeó los separadores.

    Un valor que no se puede interpretar **se devuelve tal como vino** (sin
    espacios de borde) en vez de quedar en blanco: vaciar en silencio lo que
    alguien escribió es peor que rechazarlo, porque el formulario se re-dibujaría
    sin el dato y sin explicación. Lo rechaza `rut_is_valid`, que sí puede decir
    por qué.
    """
    text = (raw or "").strip()
    if not text:
        return ""
    cleaned = _KEEP.sub("", text).upper()
    if len(cleaned) < 2:
        return text
    return f"{cleaned[:-1]}-{cleaned[-1]}"


def employee_id_from_rut(value):
    """`"19.213.597-4"` -> `"RUT-192135974"`. `""` cuando no hay RUT.

    LV-169: el ID de empleado se deriva del RUT en vez de pedirse a mano. **El
    formato no se eligió acá**: es el que el import del Capítulo 1 viene
    escribiendo desde su primera corrida, y en producción hay fichas que ya lo
    llevan. Cambiarlo habría partido el padrón en dos convenciones y roto el
    "saltar los que ya están" de ese import, que compara contra este texto.

    Vive junto a `normalize_rut` y no en el comando **porque ahora lo usan los
    dos**: si el formulario y el import derivaran cada uno el suyo, bastaría con
    que alguien tocara un `f"..."` para que el import dejara de reconocer como
    existentes las fichas que la app dio de alta, y las duplicara en silencio.

    Se limpia con `_KEEP` y **no** pasando por `normalize_rut`: ante un texto sin
    un solo dígito, `normalize_rut` devuelve lo que vino —a propósito, para no
    vaciar en silencio lo que alguien escribió— y eso habría convertido un RUT
    ilegible en un ID de empleado ilegible. Acá interesa la clave, no el eco.
    """
    key = _KEEP.sub("", (value or "").strip()).upper()
    return f"RUT-{key}" if key else ""


def rut_is_valid(value):
    """Cuerpo de 6 a 8 dígitos y dígito verificador módulo 11 (0-9 o K).

    El rango del cuerpo es deliberadamente ancho por abajo: hay RUT antiguos de
    seis dígitos en circulación, y rechazar uno real por corto obligaría a
    dejarlo en blanco, que es justo el dato que esta validación existe para
    conseguir.
    """
    match = re.fullmatch(r"(\d{6,8})-([\dK])", normalize_rut(value))
    if match is None:
        return False
    body, check_digit = match.groups()
    total = 0
    for position, digit in enumerate(reversed(body)):
        total += int(digit) * (position % 6 + 2)
    remainder = 11 - total % 11
    expected = {11: "0", 10: "K"}.get(remainder, str(remainder))
    return check_digit == expected
