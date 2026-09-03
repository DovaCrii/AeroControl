"""LV-231: leer el número de la autorización DGAC desde su propio PDF.

Pedido del usuario, textual, con la captura del encabezado a la vista: *"que el
número del permiso de vuelo lo pueda sacar de la autorización DGAC; es el mismo
PDF que siempre sube la DGAC, de ahí que sea automático"*. Su captura muestra el
encabezado invariable: **"Autorización de Operación RPA DAN 151 / Número: 6551"**.

Hoy el folio se teclea a mano y `LV-156` lo exige antes de aprobar, así que es
una transcripción manual de un dato que va a la autoridad -- justo la clase de
error que `LV-171` vino a reducir, y el PDF lo trae escrito.

⚠️ **`LV-156` decidió que esto no se hacía, y su razón se revisó en vez de
ignorarla.** Decía que *"sacarlo del archivo exigiría parsear el PDF --
dependencia nueva que la política del repo no admite"*. Verificado: no había
ninguna librería de PDF en el árbol, así que la afirmación era cierta. Pero el
criterio real del repo no es "ninguna dependencia": es **ninguna que exija
paquetes de sistema**, y está escrito en `pyproject.toml` al elegir `reportlab`.
`pypdf` es puro Python y cumple ese mismo criterio.

⚠️⚠️ **Este módulo propone, nunca escribe.** Extraer de un PDF es heurística: si
la DGAC cambia el encabezado, el patrón lee otra cosa o nada. Devuelve `None` con
generosidad y el camino de teclearlo queda intacto -- el mismo criterio que
`Aerodrome` ya declara (*"la app propone, el papel manda"*). Un folio equivocado
escrito solo es peor que un folio en blanco, porque el equivocado nadie lo
revisa.
"""

import logging
import re

logger = logging.getLogger(__name__)

# "Número: 6551". Se acepta `Numero` sin tilde porque un PDF generado con una
# fuente sin acentos, o extraído por una capa OCR, los pierde -- y perder el
# folio por una tilde sería fallar por la razón más tonta posible.
#
# `\d{1,10}` y no `\d+`: acota lo que puede terminar en un campo de la base y
# evita que una cadena larguísima de dígitos (una tabla mal extraída, un número
# de cuenta) se presente como si fuera un folio.
FOLIO_PATTERN = re.compile(r"N[uú]mero\s*:?\s*(\d{1,10})", re.IGNORECASE)

# Sólo se miran las primeras páginas. El encabezado va en la primera; recorrer un
# expediente de treinta páginas es tiempo de servidor gastado para aumentar la
# probabilidad de encontrar **otro** número que también diga "Número:" -- una
# referencia a otro trámite, por ejemplo. Menos páginas es aquí más correcto, no
# sólo más rápido.
PAGES_TO_READ = 2


def folio_from_pdf(stream):
    """El folio que declara el PDF, o `None` si no se puede afirmar ninguno.

    `None` en todos los casos dudosos, y son varios a propósito:

    - el archivo no es un PDF, está cifrado o llega corrupto;
    - el encabezado no aparece en las primeras páginas;
    - **aparecen dos números distintos**, que es el caso que más importa: ahí no
      hay una respuesta, hay dos candidatas, y elegir una sería inventar cuál
      manda. Sin sugerencia, la persona teclea el que dice el papel, que es
      exactamente lo que hacía antes.

    Nunca levanta: quien llama está dibujando una ficha, y un permiso no puede
    dejar de mostrarse porque su PDF adjunto esté roto.
    """
    try:
        from pypdf import PdfReader

        reader = PdfReader(stream)
        text = "\n".join(
            page.extract_text() or "" for page in reader.pages[:PAGES_TO_READ]
        )
    except Exception:  # noqa: BLE001 - cualquier PDF ilegible es "sin sugerencia"
        logger.info("dgac_folio_unreadable", exc_info=True)
        return None

    found = {
        match.group(1).lstrip("0") or "0" for match in FOLIO_PATTERN.finditer(text)
    }
    if len(found) != 1:
        return None
    return found.pop()
