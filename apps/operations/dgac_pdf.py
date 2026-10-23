"""Shim de importación: el lector de PDF vive ahora en `apps.core.pdf_text` (LV-368).

Se conserva porque las vistas, `compliance.forms` y las pruebas de LV-231/LV-295/
LV-299 importan (y una prueba parchea) `apps.operations.dgac_pdf.<nombre>`.

Plan de retiro. Condición de cierre: cuando ningún módulo ni prueba importe ni parchee
`apps.operations.dgac_pdf` (`grep -r dgac_pdf apps` sin resultados fuera de este
archivo), se borra y los consumidores importan de `apps.core.pdf_text`.
"""

from apps.core.pdf_text import (  # noqa: F401
    FOLIO_PATTERN,
    PAGES_TO_READ,
    WINDOW_PATTERN,
    folio_from_pdf,
    text_from_pdf,
    window_from_pdf,
    window_from_text,
)
