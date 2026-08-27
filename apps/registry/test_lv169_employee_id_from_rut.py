"""LV-169: el ID de empleado se deriva del RUT en vez de tipearse dos veces.

Pedido del usuario, con captura del alta de operador en producción: el
formulario abre pidiendo "ID de empleado" como primer campo obligatorio, y dos
campos más abajo pide el RUT. En `p340` conviven `RUT-192135974` y la columna de
al lado diciendo `19213597-4`: el mismo número, tipeado dos veces, con el error
de transcripción incluido en el precio. Es la otra mitad del pedido que cerró
`LV-167` ("tomar el RUT e incorporarlo directo en las tablas").

Las propiedades que estos tests sostienen, y por qué cada una:

- **Sólo se rellena si está en blanco.** Un ID ya escrito es la llave con la que
  esa persona figura en otros sistemas; sobrescribirlo rompería esas referencias
  sin avisar a nadie.
- **Sólo se deriva de un RUT válido.** De uno inválido saldría un ID inválido y
  **único** — basura que pasa la constraint, justo en la llave del padrón.
- **El RUT no se vuelve obligatorio.** Eso congelaría las fichas legadas
  duplicadas, la trampa que `LV-143` evitó a propósito.
- **El aviso de duplicado corre sobre el ID derivado.** La unicidad por tenant no
  la valida Django desde el formulario (`tenant` no está ahí), así que sin este
  paso un choque viaja hasta el `INSERT` y vuelve como 500 sin decir de quién es
  el número: el mismo 500 que `LV-142` arregló para el ID escrito a mano.
- **El formato es el que ya existe.** Lo viene escribiendo el import del
  Capítulo 1 desde su primera corrida y hay fichas en producción con él; otro
  formato partiría el padrón en dos convenciones.
"""

import pytest
from django.core.exceptions import ValidationError

from apps.registry.forms import OperatorForm
from apps.registry.models import Operator
from apps.registry.rut import employee_id_from_rut

RUT = "19.213.597-4"
DERIVED = "RUT-192135974"


def _payload(**kwargs):
    return {
        "employee_id": "",
        "full_name": "Cristobal Muñoz",
        "rut": RUT,
        "email": "",
        "phone": "",
        "dgac_credential": "",
        "credential_expiry": "",
        "operator_type": "",
        "address": "",
        "authorizations": "",
        "cost_center": "",
        "user": "",
        **kwargs,
    }


def test_the_format_is_the_one_the_chapter1_import_already_writes():
    assert employee_id_from_rut(RUT) == DERIVED
    assert employee_id_from_rut("19213597-4") == DERIVED
    assert employee_id_from_rut("19213597k") == "RUT-19213597K"


def test_no_rut_means_no_derived_id():
    assert employee_id_from_rut("") == ""
    assert employee_id_from_rut(None) == ""


def test_an_unreadable_rut_does_not_become_an_unreadable_id():
    """`normalize_rut` devuelve el eco de lo ilegible; acá interesa la clave."""
    assert employee_id_from_rut("sin rut") == ""


@pytest.mark.django_db
def test_the_model_derives_the_id_when_it_is_blank():
    operator = Operator(employee_id="", full_name="Cristobal Muñoz", rut=RUT)

    operator.full_clean()

    assert operator.employee_id == DERIVED


@pytest.mark.django_db
def test_an_id_already_written_is_never_overwritten():
    """Es la llave con la que esa persona figura en otros sistemas."""
    operator = Operator(employee_id="E-042", full_name="Cristobal Muñoz", rut=RUT)

    operator.full_clean()

    assert operator.employee_id == "E-042"


@pytest.mark.django_db
def test_editing_a_record_does_not_rewrite_its_id():
    operator = Operator.objects.create(
        employee_id="E-042", full_name="Cristobal Muñoz", rut="19213597-4"
    )

    operator.phone = "+56 9 1234 5678"
    operator.full_clean()
    operator.save()

    operator.refresh_from_db()
    assert operator.employee_id == "E-042"


@pytest.mark.django_db
def test_without_a_rut_the_id_is_still_required():
    operator = Operator(employee_id="", full_name="Sin RUT", rut="")

    with pytest.raises(ValidationError) as error:
        operator.full_clean()

    assert "employee_id" in error.value.error_dict


@pytest.mark.django_db
def test_an_invalid_rut_never_produces_a_derived_id():
    """Un ID inválido y único es basura que pasa la constraint."""
    operator = Operator(employee_id="", full_name="RUT malo", rut="19213597-9")

    with pytest.raises(ValidationError) as error:
        operator.full_clean()

    assert "employee_id" in error.value.error_dict


@pytest.mark.django_db
def test_the_form_accepts_a_blank_id_and_fills_it_in():
    form = OperatorForm(data=_payload())

    assert form.is_valid(), form.errors
    operator = form.save()

    assert operator.employee_id == DERIVED


@pytest.mark.django_db
def test_the_form_no_longer_marks_the_id_as_required():
    assert OperatorForm().fields["employee_id"].required is False


@pytest.mark.django_db
def test_a_derived_id_that_collides_says_whose_it_is_instead_of_a_500():
    Operator.objects.create(employee_id=DERIVED, full_name="Ficha previa")

    form = OperatorForm(data=_payload(rut=RUT))

    assert not form.is_valid()
    assert "Ficha previa" in str(form.errors["employee_id"])


@pytest.mark.django_db
def test_a_derived_id_colliding_with_an_archived_record_says_to_restore_it():
    Operator.objects.create(
        employee_id=DERIVED, full_name="Ficha archivada", is_active=False
    )

    form = OperatorForm(data=_payload(rut=RUT))

    assert not form.is_valid()
    assert "Ficha archivada" in str(form.errors["employee_id"])


@pytest.mark.django_db
def test_a_blank_id_without_a_rut_is_reported_on_the_id_field():
    """El error tiene que caer donde está el campo, no en el pie del formulario."""
    form = OperatorForm(data=_payload(rut=""))

    assert not form.is_valid()
    assert "employee_id" in form.errors


@pytest.mark.django_db
def test_an_explicit_id_still_wins_over_the_rut():
    form = OperatorForm(data=_payload(employee_id="E-777"))

    assert form.is_valid(), form.errors
    assert form.save().employee_id == "E-777"


@pytest.mark.django_db
def test_a_duplicate_id_typed_by_hand_still_names_the_owner():
    """LV-142 sigue en pie: el camino del ID escrito no se tocó."""
    Operator.objects.create(employee_id="E-777", full_name="Ya existe")

    form = OperatorForm(data=_payload(employee_id="E-777"))

    assert not form.is_valid()
    assert "Ya existe" in str(form.errors["employee_id"])


@pytest.mark.django_db
def test_the_rut_is_not_made_mandatory():
    """LV-143: exigirlo congelaría las fichas legadas duplicadas."""
    form = OperatorForm(data=_payload(employee_id="E-900", rut=""))

    assert form.is_valid(), form.errors
    assert form.save().rut == ""
