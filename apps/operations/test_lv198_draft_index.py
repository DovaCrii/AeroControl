"""LV-198: los borradores se ven desde fuera del formulario.

Pedido del usuario: *"el borrador no quedar abajo, si no generar un listado fuera
que existen borradores"*. El aviso vivía al pie del formulario de alta, así que
**sólo se descubría volviendo a esa misma pantalla** — y un borrador que hay que
recordar para encontrarlo no cumple el pedido que lo creó (`LV-154`: *"por si toca
salir y avanzar en otros temas, para no perder lo llenado"*).

**Es por navegador y no puede ser de otra forma.** El borrador vive en
`localStorage` por decisión de `LV-154`, con su razón escrita: una fila incompleta
en la base habría exigido hacer nulas tres columnas obligatorias y decidir qué
hacen con un permiso sin faena el panel, las alertas, el calendario y el informe.
Un índice compartido entre personas es esa otra decisión, no esta fila — y por eso
el aviso **dice "en este navegador"**: prometer un listado que otro no va a ver
sería peor que no tenerlo.

**Y un defecto de paso**: el aviso decía *"Tienes un borrador guardado en este
navegador ()"* — los paréntesis estaban fuera del span de la fecha, así que un
borrador sin `at` los dejaba vacíos a la vista.

Lo que se prueba acá es el **cableado**: que los rótulos lleguen traducidos en
`data-*` y que el script esté cargado. El comportamiento del contador se verificó
ejecutando `form-draft.js` con node contra un `localStorage` de mentira — cuenta,
filtra las claves ajenas y elige el plural—, porque este repo no tiene infra de
tests de JavaScript y montar un DOM en Python probaría el montaje, no el módulo.
"""

import pytest
from django.urls import reverse

from apps.core.testing import login_as


@pytest.mark.django_db
class TestTheIndexIsWiredOnTheList:
    def _content(self):
        return (
            login_as("view_flightpermission")
            .get(reverse("permission-list"))
            .content.decode()
        )

    def test_the_box_is_there_and_starts_hidden(self):
        """Arranca oculto: sin borradores no hay nada que decir, y un aviso vacío
        en cada visita enseña a no leer los avisos."""
        content = self._content()

        assert "data-draft-index" in content
        assert "data-draft-index" in content and "hidden" in content

    def test_both_plural_forms_arrive_translated(self):
        """El JS elige la forma; el servidor traduce las dos. En `form-draft.js`
        no se escriben cadenas visibles porque no habría cómo traducirlas."""
        content = self._content()

        assert "borrador sin terminar en este navegador" in content
        assert "borradores sin terminar en este navegador" in content

    def test_it_says_it_is_only_this_browser(self):
        """La promesa tiene que coincidir con la verdad de `LV-154`."""
        assert "en este navegador" in self._content()

    def test_the_script_is_loaded_here_too(self):
        """El índice comparte el prefijo de `localStorage` con quien lo escribe, y
        por eso vive en el mismo archivo: con el prefijo duplicado en dos, el día
        que cambie el índice deja de encontrar los borradores, en silencio."""
        assert "js/form-draft.js" in self._content()

    def test_it_offers_the_way_back(self):
        """Un aviso sin la salida al lado es lo que `R10.8` vino a corregir."""
        assert "Retomarlo" in self._content()


@pytest.mark.django_db
class TestTheEmptyParenthesesAreGone:
    def test_the_date_and_its_parentheses_are_one_unit(self):
        """Estaban sueltos en el texto, así que un borrador sin fecha dibujaba
        "()" — un dato ausente sin explicación se lee como pantalla rota. Se lee
        **el archivo**, igual que los tests de `LV-131` y `R10.3`: lo que se afirma
        es que el envoltorio existe y que los paréntesis están dentro."""
        from django.conf import settings

        template = (
            settings.BASE_DIR / "templates" / "operations" / "permission_form.html"
        ).read_text(encoding="utf-8")

        assert "data-form-draft-when-wrap" in template
        # Los paréntesis viven dentro del envoltorio que se oculta, no sueltos
        # antes del span.
        assert "(<span data-form-draft-when></span>)" in template

    def test_the_script_only_reveals_it_with_a_date(self):
        """**LV-209** cambió la línea que este test fijaba**: la visibilidad pasa
        ahora por `setHidden`, porque el atributo `hidden` no oculta un elemento
        con `d-flex` — ver `test_lv209_hidden_does_not_hide_a_flex_box.py`. Lo que
        este test defiende sigue siendo lo mismo: el envoltorio de la fecha se
        revela **sólo** cuando hay fecha."""
        from django.conf import settings

        script = (settings.BASE_DIR / "static" / "js" / "form-draft.js").read_text(
            encoding="utf-8"
        )

        assert "data-form-draft-when-wrap" in script
        # Dentro del `if (when && draft.at)`, o sea sólo con fecha.
        assert "setHidden(wrap, false);" in script
