"""LV-209: el botón "Descartarlo" parecía no hacer nada.

Reportado por el usuario con captura: *"al momento de descartarlo no hace nada el
botón"*.

**Y sí hacía la mitad**: el borrador se borraba de `localStorage`; lo que no se
iba era el aviso, así que en pantalla no pasaba nada y el efecto era
indistinguible de un botón muerto.

La causa no está en el JS sino en el CSS, y se puede medir en el bundle
vendorizado de Bootstrap:

- `[hidden]{display:none!important}` en la posición ~10.129
- `.d-flex{display:flex!important}` en la ~163.993
- `.d-none{display:none!important}` en la ~164.069

Un selector de atributo y una clase tienen **la misma especificidad**, y los tres
son `!important`, así que decide el orden: **`d-flex` vence a `[hidden]`**. El
aviso del borrador es un `alert d-flex`, de modo que `element.hidden = true` se
aplicaba y no ocultaba nada. `d-none` está después de `d-flex`, así que es la
única de las tres que puede ocultarlo.

**El mismo defecto lo tenía el aviso que `LV-198` acababa de agregar** —también un
`alert d-flex` que arranca oculto—, así que se habría visto siempre, con o sin
borradores. No llegó a producción.

Lo que estos tests fijan es **el orden en el bundle**, porque de eso depende el
arreglo: si una actualización de Bootstrap pusiera `.d-none` antes que `.d-flex`,
`setHidden` dejaría de funcionar **en silencio**. El comportamiento del clic se
verificó ejecutando `form-draft.js` con node contra un DOM de mentira.
"""

import re

import pytest
from django.conf import settings

BOOTSTRAP = settings.BASE_DIR / "static" / "vendor" / "bootstrap" / "bootstrap.min.css"
SCRIPT = settings.BASE_DIR / "static" / "js" / "form-draft.js"


def _positions():
    css = BOOTSTRAP.read_text(encoding="utf-8")
    return {
        name: css.find(needle)
        for name, needle in (
            ("hidden", "[hidden]{display:none!important}"),
            ("d-flex", ".d-flex{display:flex!important}"),
            ("d-none", ".d-none{display:none!important}"),
        )
    }


class TestWhyHiddenAloneDoesNotWork:
    def test_the_three_rules_are_all_there(self):
        """Si alguna dejara de existir, lo de abajo mediría el vacío."""
        assert all(position > 0 for position in _positions().values())

    def test_d_flex_beats_the_hidden_attribute(self):
        """**La causa del defecto.** Misma especificidad, los dos `!important`:
        gana el que viene después, y `d-flex` viene después."""
        positions = _positions()

        assert positions["d-flex"] > positions["hidden"]

    def test_d_none_beats_d_flex(self):
        """**De esto depende el arreglo.** Si una actualización de Bootstrap
        invirtiera este orden, `setHidden` dejaría de ocultar y el botón volvería a
        "no hacer nada" sin que ningún otro test lo note."""
        positions = _positions()

        assert positions["d-none"] > positions["d-flex"]


class TestTheScriptUsesTheOneThatWins:
    def test_there_is_a_single_place_that_hides(self):
        """Un helper y no seis asignaciones repartidas: con el atributo puesto a
        mano en cada sitio, arreglar cinco y olvidar uno es exactamente cómo vuelve
        el defecto por la puerta de al lado."""
        script = SCRIPT.read_text(encoding="utf-8")

        assert "function setHidden(element, value)" in script
        assert "classList.toggle('d-none', value)" in script

    def test_nothing_sets_the_attribute_on_its_own_any_more(self):
        """Fuera del helper no queda ninguna asignación directa de `.hidden`, que
        es la que no oculta."""
        script = SCRIPT.read_text(encoding="utf-8")
        # La única permitida es la de dentro del helper.
        assignments = re.findall(r"^\s*\w+\.hidden = ", script, re.MULTILINE)

        assert len(assignments) == 1, assignments

    def test_the_attribute_is_kept_alongside_the_class(self):
        """`hidden` se conserva porque es lo que leen los lectores de pantalla: la
        clase arregla el dibujo, el atributo dice el significado."""
        script = SCRIPT.read_text(encoding="utf-8")

        assert "element.hidden = value;" in script


@pytest.mark.django_db
class TestTheNoticesOnScreen:
    def test_the_draft_notice_is_a_flex_box(self):
        """La premisa del defecto, fijada: si mañana deja de ser `d-flex`, este test
        recuerda que el arreglo era para eso."""
        from django.urls import reverse

        from apps.core.testing import login_as

        content = (
            login_as("add_flightpermission", "view_flightpermission")
            .get(reverse("permission-create"))
            .content.decode()
        )
        notice = content[content.find("data-form-draft-notice") - 200 :][:260]

        assert "d-flex" in notice

    def test_the_draft_index_notice_is_one_too(self):
        """El que `LV-198` agregó: mismo `alert d-flex`, mismo defecto, y por eso
        pasa por el mismo helper."""
        from django.urls import reverse

        from apps.core.testing import login_as

        content = (
            login_as("view_flightpermission")
            .get(reverse("permission-list"))
            .content.decode()
        )
        box = content[content.find("data-draft-index") - 200 :][:260]

        assert "d-flex" in box
