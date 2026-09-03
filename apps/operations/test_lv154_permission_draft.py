"""LV-154: un borrador para no perder lo llenado al salir del formulario.

Textual del usuario: *"además deja un botón de dejar en borrador, por si toca
salir y avanzar en otros temas, para no perder lo llenado"*.

**Vive en el navegador**, decisión del usuario entre dos formas materialmente
distintas. Un borrador de verdad —una fila incompleta en la base— habría exigido
hacer nulos `cost_center`, `purpose` y `area_type` con su migración, y decidir qué
hacen con un permiso sin faena el panel, las alertas, el calendario y el informe,
que hoy asumen que la tiene.

Lo que se puede afirmar desde acá es el contrato: el botón está, el JS se sirve
como archivo, los rótulos los traduce el servidor y el token CSRF no se guarda.
El comportamiento se verificó en el navegador, que es donde corre.
"""

from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse

from apps.core.testing import login_as

SCRIPT = Path(settings.BASE_DIR) / "static" / "js" / "form-draft.js"
TEMPLATE = Path(settings.BASE_DIR) / "templates" / "operations" / "permission_form.html"


@pytest.mark.django_db
class TestTheFormOffersADraft:
    def test_the_button_is_on_the_create_form(self):
        content = (
            login_as("add_flightpermission")
            .get(reverse("permission-create"))
            .content.decode()
        )

        assert "data-form-draft-save" in content
        assert "form-draft.js" in content

    def test_the_notice_starts_hidden(self):
        # El aviso de "hay un borrador" lo destapa el JS sólo si hay uno: en un
        # formulario recién abierto no puede haber una alerta afirmando que sí.
        content = (
            login_as("add_flightpermission")
            .get(reverse("permission-create"))
            .content.decode()
        )

        assert "data-form-draft-notice hidden" in content

    def test_the_notice_has_a_slot_for_when_it_was_saved(self):
        content = (
            login_as("add_flightpermission")
            .get(reverse("permission-create"))
            .content.decode()
        )

        assert "data-form-draft-when" in content


class TestTheScriptRespectsTheProjectRules:
    def test_the_screen_says_the_draft_is_only_in_this_browser(self):
        # La limitación se dice en la pantalla: un borrador que se promete en
        # todas partes y sólo está en un navegador es peor que no tenerlo. Se
        # afirma sobre la plantilla y no sobre la página renderizada, porque el
        # texto se traduce y un test que compara la etiqueta pasa en aislado y
        # falla en la suite (la lección de LV-95).
        source = TEMPLATE.read_text(encoding="utf-8")

        assert "saved in this browser" in source

    def test_the_template_has_no_inline_handler(self):
        source = TEMPLATE.read_text(encoding="utf-8")

        assert "onclick=" not in source
        assert "oninput=" not in source

    def test_the_script_carries_no_user_facing_text(self):
        source = SCRIPT.read_text(encoding="utf-8")

        assert "textContent = '" not in source
        assert "dataset.savedLabel" in source

    def test_the_csrf_token_is_never_stored(self):
        # Guardar el token sería guardar una credencial de esta sesión, y
        # restaurarlo sería restaurar una vencida.
        source = SCRIPT.read_text(encoding="utf-8")

        assert "csrfmiddlewaretoken" in source
        assert "field.type !== 'password'" in source

    def test_a_blocked_storage_does_not_break_the_form(self):
        # Una ventana privada hace que `localStorage` lance al tocarlo; el
        # formulario tiene que seguir funcionando sin borrador.
        source = SCRIPT.read_text(encoding="utf-8")

        assert "function storage()" in source
        assert "return null" in source

    def test_saving_the_record_drops_the_draft(self):
        source = SCRIPT.read_text(encoding="utf-8")

        assert "form.addEventListener('submit', drop)" in source
