"""`UX-21`: el teclado que abre cada campo en un teléfono.

Su criterio es literal — *"un campo numérico abre teclado numérico en móvil"*— y
pesa más acá que en una aplicación de escritorio: quien carga una bitácora lo
hace en faena, en el teléfono, y un teclado alfabético para escribir una altura
de vuelo o una coordenada es fricción en cada dato, varias veces por jornada.

Se resuelve en `AeroModelForm`, o sea una vez para los formularios del proyecto,
y por eso los tests miran el comportamiento del formulario base y no cada
pantalla: lo que hay que proteger es que la regla siga siendo automática.
"""

import pytest
from django import forms

from apps.core.forms import AeroModelForm
from apps.operations.models import FlightPermission
from apps.registry.models import Operator


class TestTheKeyboardFollowsTheType:
    @pytest.mark.django_db
    def test_a_decimal_field_asks_for_the_decimal_keypad(self):
        """`decimal` y no `numeric`: por acá viajan coordenadas, radios y horas
        de vuelo, y un teclado sin separador decimal los vuelve inescribibles."""

        class Form(AeroModelForm):
            class Meta:
                model = FlightPermission
                fields = ["latitude"]

        assert Form().fields["latitude"].widget.attrs["inputmode"] == "decimal"

    @pytest.mark.django_db
    def test_an_integer_field_asks_for_the_plain_numeric_keypad(self):
        class Form(AeroModelForm):
            class Meta:
                model = FlightPermission
                fields = ["max_altitude_m"]

        assert Form().fields["max_altitude_m"].widget.attrs["inputmode"] == "numeric"

    @pytest.mark.django_db
    def test_a_text_field_is_left_alone(self):
        """Sin pista es mejor que con una equivocada: un `inputmode` de más en
        un campo de texto le quita a la persona el teclado que espera."""

        class Form(AeroModelForm):
            class Meta:
                model = FlightPermission
                fields = ["location"]

        assert "inputmode" not in Form().fields["location"].widget.attrs

    @pytest.mark.django_db
    def test_a_date_field_keeps_the_keyboard_the_system_gives_it(self):
        """`AeroModelForm` ya las convierte en `<input type="date">`, y ahí el
        teclado —o el selector— lo elige el sistema operativo. Un `inputmode`
        encima sólo puede empeorarlo."""

        class Form(AeroModelForm):
            class Meta:
                model = FlightPermission
                fields = ["valid_from"]

        widget = Form().fields["valid_from"].widget
        assert widget.input_type == "date"
        assert "inputmode" not in widget.attrs

    @pytest.mark.django_db
    def test_a_phone_field_is_recognised_by_its_name(self):
        """La única excepción a deducir del tipo: "teléfono" no tiene tipo
        propio en Django, es un `CharField` como cualquier otro."""

        class Form(AeroModelForm):
            class Meta:
                model = Operator
                fields = ["phone"]

        assert Form().fields["phone"].widget.attrs["inputmode"] == "tel"

    @pytest.mark.django_db
    def test_a_select_gets_nothing(self):
        """No hay caja de texto que dirigir, y un atributo de teclado en un
        `<select>` no significa nada."""

        class Form(AeroModelForm):
            class Meta:
                model = FlightPermission
                fields = ["cost_center"]

        assert "inputmode" not in Form().fields["cost_center"].widget.attrs


class TestWhatDeliberatelyStaysOut:
    @pytest.mark.django_db
    def test_autocomplete_stays_off(self):
        """En un formulario de cumplimiento casi todo campo describe un registro
        **ajeno** —la matrícula de una aeronave, el folio de un permiso— así que
        ofrecer ahí lo que la persona escribió en otro formulario invita a
        guardar el dato de otro. El defecto `off` del proyecto se conserva."""

        class Form(AeroModelForm):
            class Meta:
                model = Operator
                fields = ["full_name", "phone"]

        form = Form()
        assert form.fields["full_name"].widget.attrs["autocomplete"] == "off"
        assert form.fields["phone"].widget.attrs["autocomplete"] == "off"

    @pytest.mark.django_db
    def test_no_enterkeyhint_is_promised(self):
        """Su valor correcto depende de si el campo es el último del formulario
        —ahí `done`, si no `next`— y eso el formulario no lo sabe: el orden final
        lo arma la plantilla, y varias reordenan u ocultan campos. Un
        `enterkeyhint="next"` en el último campo promete un salto que no ocurre,
        y una promesa falsa en el teclado es peor que ninguna pista."""

        class Form(AeroModelForm):
            class Meta:
                model = FlightPermission
                fields = ["latitude", "location", "max_altitude_m"]

        for field in Form().fields.values():
            assert "enterkeyhint" not in field.widget.attrs

    @pytest.mark.django_db
    def test_a_form_that_declares_its_own_hint_keeps_it(self):
        """La regla es un defecto, no una imposición: una pantalla que sepa algo
        que el tipo del campo no dice tiene que poder decirlo."""

        class Form(AeroModelForm):
            class Meta:
                model = FlightPermission
                fields = ["permission_number"]
                widgets = {
                    "permission_number": forms.TextInput(attrs={"inputmode": "numeric"})
                }

        assert Form().fields["permission_number"].widget.attrs["inputmode"] == "numeric"
