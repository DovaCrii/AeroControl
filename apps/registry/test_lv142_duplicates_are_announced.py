"""LV-142: un duplicado se avisa nombrando quién tiene el valor, no con un 500.

Tres caminos daban `IntegrityError` sin mensaje, y ninguno tenía test que
ejercitara el **formulario** (los únicos que existían afirmaban a nivel ORM que
la base rechaza el duplicado, que es precisamente el 500):

- `Operator.employee_id` y `CostCenter.code`, porque su `UniqueConstraint`
  incluye `tenant`, que no está en el formulario, y Django omite la constraint
  entera cuando alguno de sus campos está excluido.
- `Aircraft.serial_number`, porque `save()` normalizaba **después** de validar.

El test del serial con espacio y en minúsculas es el que falla sin el fix — y no
como `form.errors`, sino con la excepción que llegaba al usuario como 500.
"""

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.core.testing import login_as
from apps.registry.forms import AircraftForm, CostCenterForm, OperatorForm
from apps.registry.models import Aircraft, CostCenter, Operator


def _aircraft_data(**overrides):
    data = {
        "registration": "RPA-9101",
        "type": "Multirotor",
        "model": "M4E",
        "manufacturer": "DJI",
        "insurance_status": Aircraft.INSURANCE_STATUS_MISSING,
        "status": "active",
        "current_location": "headquarters",
        "vlos": "",
        "parachute": "",
    }
    data.update(overrides)
    return data


def _operator_data(**overrides):
    data = {"employee_id": "E-100", "full_name": "Pilot One"}
    data.update(overrides)
    return data


def _cost_center_data(**overrides):
    data = {
        "code": "CC738",
        "name": "Minera Los Pelambres",
        "responsible": "Juan Quiroz",
        "responsible_type": "administrator",
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
class TestTheOperatorFormSaysWhoHasTheNumber:
    def test_a_duplicate_employee_id_is_a_form_error_not_a_500(self):
        Operator.objects.create(employee_id="E-100", full_name="Ana Rivas")

        form = OperatorForm(data=_operator_data())

        assert not form.is_valid()
        assert "employee_id" in form.errors

    def test_the_message_names_the_operator_that_has_it(self):
        Operator.objects.create(employee_id="E-100", full_name="Ana Rivas")

        form = OperatorForm(data=_operator_data())
        form.is_valid()

        assert "Ana Rivas" in form.errors["employee_id"][0]

    def test_an_archived_holder_is_reported_as_archived_and_restorable(self):
        # `merge_operators` archiva el duplicado en vez de borrarlo, así que en
        # producción hay `employee_id` ocupados por filas archivadas. Si el
        # chequeo filtrara por activas, diría "no hay duplicado" y el INSERT
        # reventaría igual.
        Operator.objects.create(
            employee_id="E-100", full_name="Ana Rivas", is_active=False
        )

        form = OperatorForm(data=_operator_data())
        form.is_valid()

        message = form.errors["employee_id"][0]
        assert "Ana Rivas" in message
        assert "archiv" in message.lower()

    def test_editing_an_operator_does_not_collide_with_itself(self):
        operator = Operator.objects.create(employee_id="E-100", full_name="Ana Rivas")

        form = OperatorForm(
            data=_operator_data(full_name="Ana Rivas Soto"), instance=operator
        )

        assert form.is_valid(), form.errors

    def test_a_different_case_of_the_same_id_is_caught(self):
        # El índice de la base distingue caja; la comparación del formulario no,
        # que es más estricto y por lo tanto el lado seguro.
        Operator.objects.create(employee_id="e-100", full_name="Ana Rivas")

        form = OperatorForm(data=_operator_data(employee_id="E-100"))

        assert not form.is_valid()

    def test_an_operator_whose_id_differs_only_in_case_can_still_be_edited(self):
        # La puerta "sólo cuando el valor cambia": sin ella, el `__iexact` haría
        # imposible editar el teléfono de una ficha legada.
        Operator.objects.create(employee_id="e-100", full_name="Ana Rivas")
        legacy = Operator.objects.create(employee_id="E-100", full_name="Luis Paz")

        form = OperatorForm(
            data=_operator_data(employee_id="E-100", full_name="Luis Paz Mora"),
            instance=legacy,
        )

        assert form.is_valid(), form.errors


@pytest.mark.django_db
class TestTheFormOffersTheExistingRecord:
    def test_the_response_links_to_the_record_that_already_exists(self):
        existing = Operator.objects.create(employee_id="E-100", full_name="Ana Rivas")
        client = login_as("add_operator", "view_operator")

        response = client.post(
            reverse("operator-create"), _operator_data(), HTTP_HX_REQUEST="true"
        )
        body = response.content.decode()

        assert response.status_code == 422
        assert reverse("operator-detail", args=[existing.pk]) in body
        assert "Ana Rivas" in body

    def test_the_link_is_absent_without_permission_to_read_the_record(self):
        # LV-130: un enlace que termina en 403 enseña a desconfiar de la
        # pantalla. El mensaje sigue nombrando el registro, que es información
        # que quien tipeó el valor ya tenía.
        existing = Operator.objects.create(employee_id="E-100", full_name="Ana Rivas")
        client = login_as("add_operator")

        response = client.post(
            reverse("operator-create"), _operator_data(), HTTP_HX_REQUEST="true"
        )
        body = response.content.decode()

        assert response.status_code == 422
        assert reverse("operator-detail", args=[existing.pk]) not in body
        assert "Ana Rivas" in body


@pytest.mark.django_db
class TestTheCostCenterFormSaysTheCodeIsTaken:
    def test_a_duplicate_code_is_a_form_error(self):
        CostCenter.objects.create(code="CC738", name="Minera Los Pelambres")

        form = CostCenterForm(data=_cost_center_data())

        assert not form.is_valid()
        assert "code" in form.errors

    def test_the_cc_prefix_is_normalised_before_comparing(self):
        # Escribir "738" teniendo "CC738" es el mismo centro de costo: la
        # comparación va después de normalizar, sobre el valor que se guarda.
        CostCenter.objects.create(code="CC738", name="Minera Los Pelambres")

        form = CostCenterForm(data=_cost_center_data(code="738"))

        assert not form.is_valid()
        assert "CC738" in form.errors["code"][0]

    def test_an_archived_cost_center_holding_the_code_is_named(self):
        CostCenter.objects.create(
            code="CC738", name="Minera Los Pelambres", is_active=False
        )

        form = CostCenterForm(data=_cost_center_data())
        form.is_valid()

        assert "archiv" in form.errors["code"][0].lower()

    def test_editing_a_cost_center_does_not_collide_with_itself(self):
        cost_center = CostCenter.objects.create(code="CC738", name="MLP")

        form = CostCenterForm(
            data=_cost_center_data(name="Minera Los Pelambres"), instance=cost_center
        )

        assert form.is_valid(), form.errors


@pytest.mark.django_db
class TestTheSerialIsComparedNormalised:
    def test_a_serial_typed_with_a_space_and_in_lower_case_is_caught(self):
        # El test que falla sin el fix: `save()` normalizaba después de validar,
        # así que esto pasaba el formulario y moría en el INSERT.
        Aircraft.objects.create(
            registration="RPA-4436",
            type="Multirotor",
            model="M4E",
            manufacturer="DJI",
            serial_number="1581F5FHC245",
        )

        form = AircraftForm(data=_aircraft_data(serial_number="1581f5 fhc245"))

        assert not form.is_valid()
        assert "serial_number" in form.errors
        assert "RPA-4436" in form.errors["serial_number"][0]

    def test_the_model_normalises_it_in_clean_too(self):
        # AGENTS.md: la regla no puede ser sólo del formulario, que es evadible
        # desde el admin, la API o un import. `full_clean` corre `clean()` antes
        # de `validate_unique`, así que la unicidad ve el valor canónico.
        Aircraft.objects.create(
            registration="RPA-4436",
            type="Multirotor",
            model="M4E",
            manufacturer="DJI",
            serial_number="1581F5FHC245",
        )
        duplicate = Aircraft(
            registration="RPA-4401",
            type="Multirotor",
            model="M4E",
            manufacturer="DJI",
            serial_number="1581f5 fhc245",
        )

        with pytest.raises(ValidationError) as raised:
            duplicate.full_clean()

        assert "serial_number" in raised.value.message_dict

    def test_an_empty_serial_stays_null_and_several_are_allowed(self):
        first = AircraftForm(data=_aircraft_data(registration="RPA-9101"))
        second = AircraftForm(data=_aircraft_data(registration="RPA-9102"))

        assert first.is_valid(), first.errors
        assert second.is_valid(), second.errors
        assert first.save().serial_number is None
        assert second.save().serial_number is None


@pytest.mark.django_db
class TestTheRegistrationIsComparedInUpperCase:
    def test_a_registration_typed_in_lower_case_is_stored_upper_case(self):
        form = AircraftForm(data=_aircraft_data(registration="rpa-7213"))

        assert form.is_valid(), form.errors
        assert form.save().registration == "RPA-7213"

    def test_the_same_registration_in_another_case_is_caught(self):
        # Antes de LV-142 `rpa-7126` y `RPA-7126` eran dos aeronaves distintas
        # para la base, así que el duplicado entraba sin aviso.
        Aircraft.objects.create(
            registration="RPA-7126", type="Multirotor", model="M4E", manufacturer="DJI"
        )

        form = AircraftForm(data=_aircraft_data(registration="rpa-7126"))

        assert not form.is_valid()
        assert "registration" in form.errors

    def test_editing_an_aircraft_does_not_collide_with_itself(self):
        aircraft = Aircraft.objects.create(
            registration="RPA-7126", type="Multirotor", model="M4E", manufacturer="DJI"
        )

        form = AircraftForm(
            data=_aircraft_data(registration="RPA-7126", model="M4 Enterprise"),
            instance=aircraft,
        )

        assert form.is_valid(), form.errors


@pytest.mark.django_db
class TestNobodyGetsThereWithoutPermission:
    def test_a_user_without_add_operator_gets_403_on_the_create_form(self):
        assert login_as("view_operator").get(
            reverse("operator-create")
        ).status_code == (403)

    def test_a_user_without_change_costcenter_gets_403_on_the_edit_form(self):
        cost_center = CostCenter.objects.create(code="CC738", name="MLP")

        response = login_as("view_costcenter").get(
            reverse("costcenter-update", args=[cost_center.pk])
        )

        assert response.status_code == 403
