"""`UX-20`, `UX-22` y `UX-23`: lo que cierra la fase D del plan.

Las tres son de entrada de datos y las tres se resolvieron en un sitio y no en
cada pantalla, que es lo que las hace sostenibles:

- **`UX-20`** — un formulario largo no se abre en el cuadro, se navega. Decidido
  en `HtmxFormMixin`, porque el disparador del cuadro está escrito en decenas de
  listados y una regla que cada uno tiene que recordar estaría mal la primera vez
  que alguien la olvide, y en silencio.
- **`UX-22`** — "Guardar y crear otro" en las altas repetitivas, por vista y a
  mano: no toda alta es repetitiva.
- **`UX-23`** — el borrador, más allá del formulario de permiso. El JS ya era
  genérico; lo que faltaba era la plantilla.
"""

import re
from pathlib import Path

import pytest
from django import forms
from django.conf import settings
from django.contrib.auth.models import Permission, User
from django.urls import reverse

from apps.core.testing import without_template_comments
from apps.core.views import (
    SAVE_AND_ADD_ANOTHER,
    UX20_FIELD_THRESHOLD,
    HtmxFormMixin,
    SaveAndAddAnotherMixin,
)

TEMPLATES = Path(settings.BASE_DIR) / "templates"


def _form_with(**fields):
    return type("Probe", (forms.Form,), fields)()


def _add_another_view(path, post):
    """Una vista mínima con el mixin: lo que se mide es a dónde manda, y montar
    un alta real de bitácora traería veinte campos que no tienen nada que ver."""
    from django.test import RequestFactory

    class Base:
        def get_success_url(self):
            return "/vuelos/"

    view = type("Probe", (SaveAndAddAnotherMixin, Base), {})()
    view.request = RequestFactory().post(path, post)
    return view


class TestWhichFormsAreTooLongForABox:
    """`UX-20`. El umbral sale del plan: más de ocho campos o cualquier campo de
    selección múltiple."""

    def test_a_short_form_stays_in_the_box(self):
        form = _form_with(**{f"f{n}": forms.CharField() for n in range(3)})

        assert not HtmxFormMixin().form_is_long(form)

    def test_nine_visible_fields_is_too_many(self):
        form = _form_with(
            **{f"f{n}": forms.CharField() for n in range(UX20_FIELD_THRESHOLD + 1)}
        )

        assert HtmxFormMixin().form_is_long(form)

    def test_hidden_fields_do_not_count(self):
        """No ocupan pantalla, y contarlos mandaría a página completa
        formularios que se ven de tres renglones."""
        fields = {f"f{n}": forms.CharField() for n in range(3)}
        fields.update(
            {
                f"h{n}": forms.CharField(widget=forms.HiddenInput())
                for n in range(UX20_FIELD_THRESHOLD)
            }
        )
        form = _form_with(**fields)

        assert not HtmxFormMixin().form_is_long(form)

    def test_one_multiple_select_is_enough_on_its_own(self):
        """⚠️ Sin importar el total. Un `<select multiple>` trae su propia barra
        de desplazamiento, y una barra dentro del cuadro dentro de la página es
        exactamente lo que la fila nombra: *"dejan de anidar tres barras"*."""
        form = _form_with(
            one=forms.CharField(),
            many=forms.MultipleChoiceField(choices=[("a", "A"), ("b", "B")]),
        )

        assert HtmxFormMixin().form_is_long(form)

    def test_and_a_checkbox_group_counts_as_one_too(self):
        """`CheckboxSelectMultiple` no es un `<select>`, pero es la misma
        cantidad de pantalla. Por eso se pregunta por `allow_multiple_selected`
        y no por la clase del widget."""
        form = _form_with(
            many=forms.MultipleChoiceField(
                choices=[("a", "A")], widget=forms.CheckboxSelectMultiple
            )
        )

        assert HtmxFormMixin().form_is_long(form)


@pytest.fixture
def editor(db):
    user = User.objects.create_user("editor", password="x")
    user.user_permissions.add(
        *Permission.objects.filter(
            codename__in=["add_costcenter", "view_costcenter"],
            content_type__app_label="registry",
        )
    )
    return user


class TestTheLongFormLeavesTheBox:
    @pytest.mark.django_db
    def test_asking_for_it_as_a_fragment_sends_the_browser_to_its_own_page(
        self, client, editor
    ):
        """`HX-Redirect` es como htmx entiende "esto no va a ser un fragmento":
        el navegador va a la misma URL sin la cabecera y la vista sirve su página
        completa."""
        client.force_login(editor)

        response = client.get(reverse("costcenter-create"), HTTP_HX_REQUEST="true")

        assert response.status_code == 204
        assert response["HX-Redirect"] == reverse("costcenter-create")

    @pytest.mark.django_db
    def test_the_full_page_still_answers_normally(self, client, editor):
        client.force_login(editor)

        response = client.get(reverse("costcenter-create"))

        assert response.status_code == 200

    @pytest.mark.django_db
    def test_the_redirect_keeps_the_query(self, client, editor):
        """De la query salen los valores iniciales de varias altas: perderla al
        redirigir dejaría el formulario en blanco justo cuando venía apuntado."""
        client.force_login(editor)

        response = client.get(
            reverse("costcenter-create"), {"code": "CC738"}, HTTP_HX_REQUEST="true"
        )

        assert response["HX-Redirect"].endswith("?code=CC738")


class TestSaveAndAddAnother:
    """`UX-22`. Una jornada de faena son seis u ocho vuelos del mismo permiso, y
    hasta acá cada uno costaba volver al listado y buscar "Nuevo" otra vez."""

    def test_it_comes_back_to_the_same_form_with_its_query(self):
        """De la query salen los valores iniciales (`?permission=`, `?aircraft=`):
        quien está cargando diez vuelos del mismo permiso quiere el siguiente ya
        apuntando al mismo permiso."""
        view = _add_another_view(
            "/vuelos/new/?permission=7", {SAVE_AND_ADD_ANOTHER: "1"}
        )

        assert view.get_success_url() == "/vuelos/new/?permission=7"

    def test_plain_save_goes_wherever_it_always_went(self):
        view = _add_another_view("/vuelos/new/", {})

        assert view.get_success_url() == "/vuelos/"

    @pytest.mark.django_db
    def test_only_the_views_that_declare_it_offer_the_button(self):
        """No toda alta es repetitiva: un centro de costo se crea una vez al año
        y ofrecerle el botón sólo agrega ruido."""
        from apps.compliance.views import DocumentCreate
        from apps.operations.views import FlightRecordCreate
        from apps.registry.views import AssignmentCreate, CostCenterCreate

        assert FlightRecordCreate.save_and_add_another
        assert DocumentCreate.save_and_add_another
        assert AssignmentCreate.save_and_add_another
        assert not getattr(CostCenterCreate, "save_and_add_another", False)

    def test_the_button_never_shows_on_an_edit(self):
        """⚠️ En una edición, el formulario que quedaría abierto vendría cargado
        con los datos del registro recién modificado — la forma más limpia de
        duplicarlo sin querer."""
        for name in ("generic/form.html", "compliance/document_form.html"):
            source = (TEMPLATES / name).read_text(encoding="utf-8")
            assert re.search(
                r"view\.save_and_add_another and not view\.object", source
            ), name

    def test_the_saved_message_says_what_the_blank_form_is(self):
        """El aviso por defecto es cierto, pero deja la duda de si el formulario
        en blanco que apareció es el mismo que no se guardó."""
        from apps.core.views import SaveAndAddAnotherMixin

        assert "get_success_message" in vars(SaveAndAddAnotherMixin)
        # Un gancho y no un segundo `messages.success`: apilar dos avisos
        # diciendo casi lo mismo es peor que uno preciso.
        assert "get_success_message" in vars(HtmxFormMixin)


class TestTheDraftIsNoLongerOnlyForPermits:
    """`UX-23`. `form-draft.js` ya era genérico —se engancha en
    `[data-form-draft]` y no sabe nada del permiso— así que lo que faltaba no era
    código sino la plantilla."""

    def test_the_generic_form_offers_it(self):
        source = (TEMPLATES / "generic" / "form.html").read_text(encoding="utf-8")

        assert 'include "generic/_form_draft.html"' in source
        assert "form-draft.js" in source

    def test_the_long_forms_with_their_own_template_have_it_too(self):
        """⚠️ Y ésta es la mitad que casi queda inerte. `generic/form.html` no lo
        sirve a los formularios largos que importan, porque **los largos tienen
        plantilla propia**: la ficha de faena y la carga de documentos no pasan
        por él. Se descubrió mirando el navegador, no el test: el panel no
        aparecía en ninguna pantalla real."""
        for name in (
            "registry/costcenter_form.html",
            "compliance/document_form.html",
        ):
            source = (TEMPLATES / name).read_text(encoding="utf-8")
            assert 'include "generic/_form_draft.html"' in source, name
            assert 'include "generic/_form_draft_button.html"' in source, name
            assert "form-draft.js" in source, name

    def test_the_partial_does_not_pin_a_shared_key(self):
        """⚠️ Sin `data-form-draft-key` a propósito: el JS cae entonces en
        `window.location.pathname`, que separa el alta de cada edición. Una clave
        fija compartida —como `permission-form`— ofrece en la ficha del registro
        3 el borrador que quedó del 5."""
        # Sin los comentarios: el propio archivo **explica** por qué no lleva la
        # clave, y buscarla en el texto crudo encontraría esa explicación. Es el
        # mismo tropiezo que ya obligó a extraer este ayudante (`UX-07`).
        source = without_template_comments(
            (TEMPLATES / "generic" / "_form_draft.html").read_text(encoding="utf-8")
        )

        assert "data-form-draft" in source
        assert "data-form-draft-key" not in source

    def test_only_long_forms_get_the_panel(self):
        """Uno de tres campos se vuelve a escribir en veinte segundos, y
        ofrecerle un panel de borrador es ruido en toda pantalla de alta."""
        source = (TEMPLATES / "generic" / "form.html").read_text(encoding="utf-8")

        assert f"form.visible_fields|length > {UX20_FIELD_THRESHOLD}" in source

    def test_the_template_threshold_matches_the_python_one(self):
        """Son la misma pregunta hecha dos veces —un formulario largo es el que
        no cabe en un cuadro y el que duele perder a medio llenar— y si los dos
        números se separan, una pantalla ofrecerá borrador sin ser larga o al
        revés, sin que nadie se entere."""
        source = (TEMPLATES / "generic" / "form.html").read_text(encoding="utf-8")

        found = {int(n) for n in re.findall(r"visible_fields\|length > (\d+)", source)}

        assert found == {UX20_FIELD_THRESHOLD}
