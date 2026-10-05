"""LV-264: `<form data-confirm>` preguntaba dos veces.

`app.js` lo enganchaba en dos lugares —en `document.body` y en `document`—, y como
el envío sube de uno al otro, `window.confirm` salía dos veces. Medido el
2026-10-05 en el navegador con `confirm` sustituido por un contador: **2 llamadas**
al aceptar y **2 al cancelar**, o sea que la segunda pregunta llegaba aun después
de contestar «Cancelar». «Aprobar» del informe mensual y los «Archivar» pasan por
acá.
"""

import re
from pathlib import Path

from django.conf import settings

APP_JS = Path(settings.BASE_DIR) / "static" / "js" / "app.js"


def _code():
    """`app.js` sin comentarios: los comentarios nombran el atributo a propósito."""
    js = APP_JS.read_text(encoding="utf-8")
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    return re.sub(r"^\s*//.*$", "", js, flags=re.M)


def test_only_one_handler_asks():
    code = _code()
    readers = re.findall(r"dataset\.confirm\b|\[data-confirm\]", code)
    calls = re.findall(r"window\.confirm\(\s*form\.dataset\.confirm", code)
    assert len(calls) == 1, "data-confirm se pregunta en más de un manejador"
    assert readers, "la premisa cambió: ya no hay manejador de data-confirm"


def test_a_cancelled_submit_is_not_asked_again():
    code = _code()
    handler = code[: code.index("window.confirm(form.dataset.confirm")]
    handler = handler[handler.rindex("addEventListener('submit'") :]
    assert "event.defaultPrevented" in handler
