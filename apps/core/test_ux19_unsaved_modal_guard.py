"""`UX-19`: cerrar el modal genérico habiendo escrito algo pregunta antes.

*Criterio de la fila:* cerrar con `Esc` o con "Cancelar" habiendo tocado un campo
pide confirmación.

Importa porque el modal es donde se cargan los formularios largos del proyecto —
un permiso de vuelo, un documento— y hasta acá se cerraba callado: un `Esc` de
más y no quedaba nada de lo escrito.

Se afirma sobre los archivos porque ahí vive la conducta: `app.js` es estático y
el aviso viaja en un `data-*` de `base.html`, que es el camino que este proyecto
usa para todo texto que el JS tiene que decir en español (`data-confirm`, los
rótulos del tirador de la barra). Un test que abriera un navegador mediría el
navegador.
"""

import re
from pathlib import Path

from django.conf import settings
from django.utils.translation import activate, gettext

APP_JS = (Path(settings.BASE_DIR) / "static" / "js" / "app.js").read_text(
    encoding="utf-8"
)
BASE = (Path(settings.BASE_DIR) / "templates" / "base.html").read_text(encoding="utf-8")

MESSAGE = "This form has changes that have not been saved. Close it and lose them?"


class TestTheGuardCoversEveryWayOut:
    def test_it_hangs_off_the_cancellable_event(self):
        """⚠️ `hide.bs.modal` y no cada botón: ese evento es **cancelable** y
        cubre las cuatro salidas de una vez — `Esc`, la cruz, cualquier
        `data-bs-dismiss` y el clic fuera del cuadro. Botón por botón habría
        dejado `Esc` sin cubrir, que es justo el accidente más común."""
        assert "'hide.bs.modal'" in APP_JS
        guard = APP_JS.split("'hide.bs.modal'", 1)[1]
        assert "event.preventDefault()" in guard.split("});", 1)[0]

    def test_typing_in_the_modal_is_what_arms_it(self):
        """Y `change` además de `input`: un `<select>` o una casilla no emiten
        `input` en todos los navegadores, y elegir una faena distinta es
        exactamente "tocar un campo"."""
        assert re.search(
            r"addEventListener\('input'[^)]*\)?[\s\S]{0,200}#modal-content", APP_JS
        )
        assert re.search(
            r"addEventListener\('change'[^)]*\)?[\s\S]{0,200}#modal-content", APP_JS
        )


class TestItDoesNotAskWhenThereIsNothingToLose:
    def test_a_saved_form_closes_without_a_question(self):
        """El camino feliz cierra el modal por `modal-form-success`. Si la marca
        siguiera puesta, guardar terminaría preguntando "¿perder los cambios?"
        justo después de guardarlos — y una guardia que miente enseña a
        contestar que sí sin leer, que es peor que no tenerla."""
        success = APP_JS.split("'modal-form-success'", 1)[1].split("});", 1)[0]

        assert "modalDirty = false" in success

    def test_a_fresh_form_starts_clean(self):
        """Contenido nuevo en el modal es formulario nuevo: lo tecleado en el
        anterior ya no está en pantalla."""
        swap = APP_JS.split("'htmx:afterSwap'", 1)[1]

        assert "modalDirty = false" in swap


class TestTheFailedSaveKeepsTheGuard:
    def test_a_422_does_not_reset_the_flag(self):
        """⚠️ El caso que importa, y el que un reinicio ciego habría roto. El
        swap de un 422 no trae un formulario en blanco: trae el mismo, con los
        errores marcados y **con todo lo que la persona escribió**. Reiniciar ahí
        dejaría sin guardia el momento con más escrito y más ganas de cerrar."""
        swap = APP_JS.split("'htmx:afterSwap'", 1)[1]

        assert "422" in swap
        assert re.search(r"if\s*\(!failed\)\s*modalDirty = false", swap)


class TestTheQuestionIsAskedInSpanish:
    def test_the_message_rides_on_the_modal(self):
        """`app.js` es estático y no pasa por gettext: el texto tiene que llegar
        desde la plantilla o saldría siempre en inglés."""
        assert "data-unsaved-message=" in BASE
        assert MESSAGE in BASE
        assert "this.dataset.unsavedMessage" in APP_JS

    def test_and_the_catalogue_has_it(self):
        """En una pregunta de «¿perdés lo escrito?» es exactamente donde no se
        puede dudar del idioma."""
        activate("es")
        try:
            assert gettext(MESSAGE) != MESSAGE
        finally:
            activate("es")
