"""LV-211: un campo del formulario que la plantilla no dibuja se borra al guardar.

Encontrado en producción a los minutos de desplegar `LV-206`. El usuario reportó
que no veía la casilla "En esta faena se vuela", y al mirarlo apareció lo otro:
**`CC410` había desaparecido de la tabla del panel sin que él la desmarcara.**

`_costcenter_form_fields.html` dibuja **campo por campo** —está agrupada en
secciones desde `LV-36`— así que un campo que entra a `Meta.fields` y no a esa
plantilla no queda invisible: queda **sin enviar**. Y un checkbox que el navegador
no envía no es "sin cambios", es `False`. Así que cada edición de una faena la
sacaba de la tabla, en silencio y sin que nadie lo pidiera.

Lo que estos tests fijan no es el campo sino **la clase de defecto**: que editar
una ficha no puede borrar lo que la pantalla no muestra. El test que importa
recorre `Meta.fields` y comprueba que la plantilla los dibuje todos — así el
próximo campo que alguien agregue al formulario y olvide en el HTML falla acá en
vez de borrar datos en producción.
"""

import re

import pytest
from django.conf import settings
from django.urls import reverse

from apps.core.testing import login_as
from apps.registry.forms import CostCenterForm
from apps.registry.models import CostCenter

TEMPLATE = settings.BASE_DIR / "templates" / "registry" / "_costcenter_form_fields.html"


@pytest.mark.django_db
def test_every_form_field_is_drawn_by_the_template():
    """**El test que sostiene la fila.** Un campo en el formulario y no en el
    HTML no es invisible: es un dato que se borra al guardar.

    Se lee la plantilla y no el HTML renderizado a propósito: lo que hay que
    afirmar es que **el autor la escribió completa**, y eso se ve en el archivo.
    """
    drawn = set(
        re.findall(r"form\.(\w+)\|as_crispy_field", TEMPLATE.read_text("utf-8"))
    )
    declared = set(CostCenterForm().fields)

    missing = declared - drawn
    assert not missing, f"en el formulario y no en la plantilla: {sorted(missing)}"


@pytest.mark.django_db
class TestEditingKeepsWhatItDoesNotShow:
    def _edit(self, center, **overrides):
        """Guardar la ficha como lo hace el navegador: **sólo** lo que la
        plantilla dibuja. Un campo ausente del POST es un campo ausente."""
        drawn = set(
            re.findall(r"form\.(\w+)\|as_crispy_field", TEMPLATE.read_text("utf-8"))
        )
        data = {
            "code": center.code,
            "name": center.name,
            "contract_status": center.contract_status,
            "responsible": center.responsible or "Alguien",
            "responsible_type": "administrator",
            "notes": "",
        }
        # Los checkbox marcados viajan; los desmarcados no viajan en absoluto.
        if "operates_flights" in drawn and center.operates_flights:
            data["operates_flights"] = "on"
        data.update(overrides)
        return login_as("change_costcenter", "view_costcenter").post(
            reverse("costcenter-update", args=[center.pk]), data
        )

    def test_editing_keeps_operates_flights(self):
        """El caso exacto de producción: se edita el nombre y la faena sigue
        volando."""
        center = CostCenter.objects.create(
            code="CC410", name="Levantamientos digital", responsible="Cristóbal Muñoz"
        )

        self._edit(center, name="Levantamientos Digital")

        center.refresh_from_db()
        assert center.operates_flights is True

    def test_unchecking_it_still_works(self):
        """El contrapeso: la casilla tiene que poder desmarcarse de verdad, o el
        arreglo habría vuelto el campo inmutable."""
        center = CostCenter.objects.create(
            code="CC110", name="Casa Matriz", responsible="Gerencia General"
        )

        # Sin la clave en el POST: es cómo el navegador manda un checkbox apagado.
        response = login_as("change_costcenter", "view_costcenter").post(
            reverse("costcenter-update", args=[center.pk]),
            {
                "code": center.code,
                "name": center.name,
                "contract_status": "active",
                "responsible": "Gerencia General",
                "responsible_type": "administrator",
                "notes": "",
            },
        )

        assert response.status_code in (200, 302)
        center.refresh_from_db()
        assert center.operates_flights is False

    def test_the_field_reaches_the_page(self):
        center = CostCenter.objects.create(code="CC738", name="MLP")

        content = (
            login_as("change_costcenter", "view_costcenter")
            .get(reverse("costcenter-update", args=[center.pk]))
            .content.decode()
        )

        assert "operates_flights" in content
        assert "En esta faena se vuela" in content
