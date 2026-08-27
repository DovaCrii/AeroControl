"""LV-165: el contraste de la paleta cumple WCAG AA, en los dos temas.

Reportado por el usuario el 2026-08-27: *"en oscuro todas las letras grises o
símbolos grises deben ser legibles"*. **Se midió antes de tocar nada, y la
paleta ya cumplía**: en oscuro el peor par es `--ac-text-muted` sobre
`--ac-surface-raised` con 5.35:1, contra un mínimo de 4.5. El oscuro está de
hecho mejor que el claro, donde ese mismo par roza el mínimo con 5.08:1 y
`--ac-primary` sobre `--ac-bg` da 4.53:1.

También se midieron las pantallas reales en el navegador, en oscuro: cero fallos
de texto sobre el panel, el listado de operadores y la prueba de conocimientos
(781 elementos), y cero de las 63 formas SVG por debajo del 3:1 que corresponde
a un objeto gráfico. Lo que el usuario percibe como "apagado y plano" es falta
de **jerarquía y color**, no de contraste -- y aclarar un gris que ya cumple
reduciría los niveles distinguibles y lo dejaría más plano todavía. Eso se
atiende en las filas de diseño (`LV-163` y las del tablero SIGO y la
navegación), no acá.

Lo que este archivo aporta es lo que faltaba: que la conformidad **no se pueda
perder en silencio**. Antes existía una sola medición a mano, escrita en un
comentario junto a `.sidebar-label`, y nada comprobaba el resto.
"""

import re
from pathlib import Path

import pytest
from django.conf import settings

CSS = Path(settings.BASE_DIR) / "static" / "css" / "app.css"

# WCAG 2.1: 4.5:1 para texto normal. No se usa el 3:1 de texto grande porque
# estos tokens se aplican a texto de cuerpo en casi todos sus usos, y un umbral
# elegido por el caso más favorable no protege el caso real.
AA_TEXT = 4.5

SURFACES = ("--ac-bg", "--ac-surface", "--ac-surface-raised")
# Los tokens que terminan pintando texto. `--ac-border` queda fuera a propósito:
# es una línea divisoria, no un objeto gráfico portador de información, y
# exigirle 3:1 obligaría a un borde que compite con el contenido.
FOREGROUNDS = ("--ac-text", "--ac-text-secondary", "--ac-text-muted", "--ac-primary")


def _block(pattern):
    match = re.search(
        pattern + r"[^{]*\{(.*?)\n\}", CSS.read_text(encoding="utf-8"), re.DOTALL
    )
    assert match, f"no se encontró el bloque {pattern!r} en app.css"
    return dict(re.findall(r"(--ac-[a-z-]+):\s*(#[0-9a-fA-F]{3,8})", match.group(1)))


def _rgb(value):
    raw = value.lstrip("#")
    if len(raw) == 3:
        raw = "".join(c * 2 for c in raw)
    return tuple(int(raw[i : i + 2], 16) for i in (0, 2, 4))


def _relative_luminance(value):
    def channel(component):
        component /= 255
        return (
            component / 12.92
            if component <= 0.03928
            else ((component + 0.055) / 1.055) ** 2.4
        )

    red, green, blue = (channel(c) for c in _rgb(value))
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast(foreground, background):
    """El ratio de WCAG 2.1, tal como lo define la norma."""
    first, second = (
        _relative_luminance(foreground),
        _relative_luminance(background),
    )
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


THEMES = {
    "claro": r"(?m)^:root",
    "oscuro": r'\[data-theme="dark"\], \[data-bs-theme="dark"\]',
}


def test_the_formula_matches_the_published_examples():
    """El guardián del guardián. Sin esto, un error en la fórmula haría pasar
    toda la matriz de abajo en verde midiendo cualquier cosa. Los tres valores
    salen de la definición de WCAG: negro sobre blanco es exactamente 21."""
    assert round(contrast("#000000", "#ffffff"), 2) == 21.0
    assert round(contrast("#ffffff", "#ffffff"), 2) == 1.0
    # Simétrico: el orden de los argumentos no puede cambiar el resultado.
    assert contrast("#767676", "#ffffff") == contrast("#ffffff", "#767676")


@pytest.mark.parametrize("theme", sorted(THEMES))
def test_the_palette_is_actually_being_read(theme):
    tokens = _block(THEMES[theme])

    faltan = [name for name in SURFACES + FOREGROUNDS if name not in tokens]
    assert not faltan, f"{theme}: sin declarar {faltan}"


@pytest.mark.parametrize("theme", sorted(THEMES))
def test_every_text_token_clears_aa_on_every_surface(theme):
    """La matriz completa, y no una muestra: cada token de texto se usa sobre las
    tres superficies según la pantalla, así que basta un par por debajo para que
    haya una pantalla ilegible."""
    tokens = _block(THEMES[theme])
    bajos = []
    for foreground in FOREGROUNDS:
        for surface in SURFACES:
            ratio = contrast(tokens[foreground], tokens[surface])
            if ratio < AA_TEXT:
                bajos.append(f"{foreground} sobre {surface}: {ratio:.2f}:1")

    assert not bajos, f"{theme}, por debajo de {AA_TEXT}:1:\n  " + "\n  ".join(bajos)


def test_the_three_text_levels_stay_distinguishable():
    """Que cumplan no alcanza: si los tres grises convergen, la pantalla queda
    plana aunque cada uno sea legible -- que es exactamente lo que el usuario
    reportó. Se exige separación entre niveles, en los dos temas, para que
    "subir el contraste" no se convierta en aplanar la jerarquía.
    """
    for theme, pattern in THEMES.items():
        tokens = _block(pattern)
        surface = tokens["--ac-surface"]
        fuerte = contrast(tokens["--ac-text"], surface)
        medio = contrast(tokens["--ac-text-secondary"], surface)
        debil = contrast(tokens["--ac-text-muted"], surface)

        assert fuerte > medio > debil, (
            f"{theme}: los niveles no van de más a menos "
            f"({fuerte:.2f} / {medio:.2f} / {debil:.2f})"
        )
        # Un salto mínimo entre niveles contiguos: por debajo de esto el ojo no
        # los separa y el nivel deja de comunicar.
        assert medio / debil >= 1.15, f"{theme}: secundario y débil casi iguales"
