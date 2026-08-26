"""LV-143: el RUT del operador, validado y comparado.

Es la llave natural chilena —con la que la persona aparece en la credencial de la
DGAC y en el Capítulo 1— y el campo aceptaba cualquier cosa: sin formato, sin
dígito verificador y sin unicidad, así que dos fichas de la misma persona con el
RUT escrito distinto eran dos personas para la app.

**Sin restricción de base de datos**, y eso es lo que estos tests fijan: en
producción hay duplicados que vinieron del import, y la regla se aplica sólo
cuando el valor cambia para no congelar esas fichas. El último test es el
contrapeso: si alguien mueve la regla a `save()`, el importador se cae, y este
archivo lo dice antes que producción.
"""

import pytest
from django.core.exceptions import ValidationError

from apps.core.models import OperationalTenant
from apps.registry.forms import OperatorForm
from apps.registry.models import Operator
from apps.registry.rut import normalize_rut, rut_is_valid


def _data(**overrides):
    data = {"employee_id": "E-200", "full_name": "Ana Rivas", "rut": "12.345.678-5"}
    data.update(overrides)
    return data


class TestTheCanonicalForm:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("12.345.678-5", "12345678-5"),
            ("12345678-5", "12345678-5"),
            ("123456785", "12345678-5"),
            ("  12.345.678-k  ", "12345678-K"),
            ("", ""),
            (None, ""),
        ],
    )
    def test_the_separators_do_not_change_the_value(self, raw, expected):
        assert normalize_rut(raw) == expected

    def test_something_that_is_not_a_rut_is_kept_so_it_can_be_rejected(self):
        # Vaciarlo en silencio sería peor: el formulario se re-dibujaría sin el
        # dato y sin explicación. Lo rechaza `rut_is_valid`, que sí dice por qué.
        assert normalize_rut("sin rut") == "sin rut"

    @pytest.mark.parametrize(
        "value",
        [
            "12.345.678-5",
            "11.111.111-1",
            "6.376.291-1",  # cuerpo de siete dígitos: los RUT antiguos existen
            "874.321-5",  # y de seis
            "6.000.000-K",  # dígito verificador K, el caso que se olvida
            "6.000.005-0",  # y el 0, que es el otro resto especial del módulo 11
        ],
    )
    def test_a_real_rut_passes_the_check_digit(self, value):
        assert rut_is_valid(value)

    @pytest.mark.parametrize("value", ["12.345.678-9", "12345678-K", "sin rut", "1-9"])
    def test_a_wrong_check_digit_or_shape_does_not(self, value):
        assert not rut_is_valid(value)


@pytest.mark.django_db
class TestTheRuleOnTheModel:
    def test_a_rut_with_dots_is_stored_canonical(self):
        operator = Operator(
            employee_id="E-200", full_name="Ana Rivas", rut="12.345.678-5"
        )
        operator.full_clean()
        operator.save()

        assert Operator.objects.get(pk=operator.pk).rut == "12345678-5"

    def test_a_rut_with_a_wrong_check_digit_is_rejected(self):
        operator = Operator(
            employee_id="E-200", full_name="Ana Rivas", rut="12.345.678-9"
        )

        with pytest.raises(ValidationError) as raised:
            operator.full_clean()

        assert "rut" in raised.value.message_dict

    def test_a_rut_that_is_not_a_rut_is_rejected(self):
        operator = Operator(employee_id="E-200", full_name="Ana Rivas", rut="sin rut")

        with pytest.raises(ValidationError) as raised:
            operator.full_clean()

        assert "rut" in raised.value.message_dict

    def test_a_blank_rut_is_still_allowed(self):
        # El RUT no es obligatorio: hay fichas cargadas sin él, y exigirlo acá
        # convertiría cualquier edición en un trámite.
        operator = Operator(employee_id="E-200", full_name="Ana Rivas", rut="")

        operator.full_clean()

    def test_a_duplicate_rut_inside_the_tenant_is_rejected(self):
        Operator.objects.create(
            employee_id="E-100", full_name="Ana Rivas", rut="12345678-5"
        )
        second = Operator(
            employee_id="E-200", full_name="Ana Rivas Soto", rut="12.345.678-5"
        )

        with pytest.raises(ValidationError) as raised:
            second.full_clean()

        assert "Ana Rivas" in raised.value.message_dict["rut"][0]

    def test_the_same_rut_in_another_tenant_is_allowed(self):
        other = OperationalTenant.objects.create(name="Otra empresa")
        Operator.objects.create(
            tenant=other, employee_id="E-100", full_name="Ana Rivas", rut="12345678-5"
        )
        mine = Operator(employee_id="E-200", full_name="Ana Rivas", rut="12345678-5")

        mine.full_clean()

    def test_an_operator_whose_rut_is_already_duplicated_can_still_be_edited(self):
        # La puerta que protege las fichas del import: sin ella, corregir el
        # teléfono de un duplicado existente sería imposible.
        Operator.objects.create(
            employee_id="E-100", full_name="Ana Rivas", rut="12.345.678-5"
        )
        duplicate = Operator.objects.create(
            employee_id="E-200", full_name="Ana Rivas", rut="12.345.678-5"
        )

        duplicate.phone = "+56 9 1234 5678"
        duplicate.full_clean()
        duplicate.save()

        assert Operator.objects.get(pk=duplicate.pk).phone == "+56 9 1234 5678"

    def test_an_invalid_rut_already_on_file_does_not_block_an_unrelated_edit(self):
        operator = Operator.objects.create(
            employee_id="E-200", full_name="Ana Rivas", rut="sin rut"
        )

        operator.phone = "+56 9 1234 5678"
        operator.full_clean()

    def test_the_importer_can_still_create_a_duplicate(self):
        # `chapter1_docx_import` usa `objects.create()` sin `full_clean`, y esto
        # lo fija a propósito: si la regla se mueve a `save()`, el import del
        # Capítulo 1 se cae y este test lo dice antes que producción.
        Operator.objects.create(
            employee_id="RUT-123456785", full_name="Ana Rivas", rut="12.345.678-5"
        )
        Operator.objects.create(
            employee_id="RUT-123456785-2", full_name="Ana Rivas", rut="12.345.678-5"
        )

        assert Operator.objects.filter(rut="12.345.678-5").count() == 2


@pytest.mark.django_db
class TestTheRuleOnTheForm:
    def test_the_form_rejects_it_too_not_just_the_model(self):
        form = OperatorForm(data=_data(rut="12.345.678-9"))

        assert not form.is_valid()
        assert "rut" in form.errors

    def test_the_form_stores_the_canonical_value(self):
        form = OperatorForm(data=_data(rut="12.345.678-5"))

        assert form.is_valid(), form.errors
        assert form.save().rut == "12345678-5"

    def test_a_duplicate_rut_is_a_field_error_that_names_the_holder(self):
        Operator.objects.create(
            employee_id="E-100", full_name="Ana Rivas", rut="12345678-5"
        )

        form = OperatorForm(data=_data(employee_id="E-200"))

        assert not form.is_valid()
        assert "Ana Rivas" in form.errors["rut"][0]

    def test_the_form_offers_the_operator_that_already_has_the_rut(self):
        existing = Operator.objects.create(
            employee_id="E-100", full_name="Ana Rivas", rut="12345678-5"
        )

        form = OperatorForm(data=_data(employee_id="E-200"))
        form.is_valid()

        assert form.duplicate_of == existing

    def test_editing_an_operator_does_not_collide_with_its_own_rut(self):
        operator = Operator.objects.create(
            employee_id="E-200", full_name="Ana Rivas", rut="12345678-5"
        )

        form = OperatorForm(
            data=_data(rut="12.345.678-5", full_name="Ana Rivas Soto"),
            instance=operator,
        )

        assert form.is_valid(), form.errors
