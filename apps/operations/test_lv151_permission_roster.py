"""LV-151: el roster del permiso, ordenado, acotado y con buscador.

`LV-38` había resuelto el alto de la página pasando las casillas a grilla
multicolumna, y por eso `LV-23` se cerró. Lo que quedaba sin resolver era
**encontrar**: con 41 operadores ofrecidos en el orden en que la base los
devuelve, elegir a una persona es un barrido a ojo. Textual del usuario:
*"tengo problemas a buscar los operadores"*.

Dos defectos y una función nueva:

- Ni `Operator` ni `Aircraft` declaran `Meta.ordering`, así que el
  `ModelMultipleChoiceField` los ofrecía sin orden.
- El queryset por defecto **no filtra `is_active`**, así que un operador
  archivado y una aeronave retirada seguían ofreciéndose para un permiso nuevo.
- Falta un filtro en vivo sobre las casillas, y decir cuántas van elegidas.

Los tests del filtro leen la plantilla y el JS, no una página renderizada: lo
que cambió es comportamiento del navegador, y el cliente de pruebas de Django no
lo ejecuta. Mismo criterio que `R10.3` con los iconos y `LV-136` con el mapa.
"""

from datetime import timedelta
from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from apps.core.testing import login_as
from apps.operations.forms import FlightPermissionForm, FlightPermissionUpdateForm
from apps.operations.models import FlightPermission
from apps.registry.models import Aircraft, CostCenter, Operator

TEMPLATE = Path(settings.BASE_DIR) / "templates" / "operations" / "_roster_field.html"
FORM_TEMPLATE = (
    Path(settings.BASE_DIR) / "templates" / "operations" / "permission_form.html"
)
SCRIPT = Path(settings.BASE_DIR) / "static" / "js" / "roster-filter.js"


def _aircraft(registration, **kwargs):
    return Aircraft.objects.create(
        registration=registration,
        type="Multirotor",
        model=kwargs.pop("model", "M4E"),
        manufacturer="DJI",
        **kwargs,
    )


@pytest.mark.django_db
class TestTheRosterIsOrdered:
    def test_operators_are_offered_alphabetically(self):
        # Creados a propósito en desorden: el orden que importa es el ofrecido,
        # no el de inserción.
        for employee_id, name in [
            ("E-3", "Roberto Salgado Ramos"),
            ("E-1", "Alex Lizama Paz"),
            ("E-2", "Braulio Gómez Torres"),
        ]:
            Operator.objects.create(employee_id=employee_id, full_name=name)

        offered = [
            operator.full_name
            for operator in FlightPermissionForm().fields["operators"].queryset
        ]

        assert offered == [
            "Alex Lizama Paz",
            "Braulio Gómez Torres",
            "Roberto Salgado Ramos",
        ]

    def test_aircraft_are_offered_by_registration(self):
        for registration in ["RPA-5534", "RPA-2019", "RPA-4025"]:
            _aircraft(registration)

        offered = [
            aircraft.registration
            for aircraft in FlightPermissionForm().fields["aircraft_fleet"].queryset
        ]

        assert offered == ["RPA-2019", "RPA-4025", "RPA-5534"]


@pytest.mark.django_db
class TestTheRosterOnlyOffersWhatCanFly:
    def test_an_archived_operator_is_not_offered(self):
        Operator.objects.create(
            employee_id="E-1", full_name="Ana Rivas", is_active=False
        )

        assert not FlightPermissionForm().fields["operators"].queryset.exists()

    def test_a_retired_aircraft_is_not_offered(self):
        _aircraft("RPA-2019", status="retired")

        assert not FlightPermissionForm().fields["aircraft_fleet"].queryset.exists()

    def test_an_archived_aircraft_is_not_offered(self):
        _aircraft("RPA-2019", is_active=False)

        assert not FlightPermissionForm().fields["aircraft_fleet"].queryset.exists()

    def test_a_damaged_aircraft_is_still_offered(self):
        # "Dañada" no es terminal: la aeronave sigue en la flota y un permiso
        # puede nombrarla. Sólo lo retirado sale del padrón.
        _aircraft("RPA-2019", status="damaged")

        assert FlightPermissionForm().fields["aircraft_fleet"].queryset.count() == 1

    def test_what_the_permit_already_chose_stays_offered_even_if_retired(self):
        # Si una aeronave se retira **después** de que el permiso la incluyó,
        # sacarla del queryset la borraría del permiso al guardar cualquier otra
        # edición -- una pérdida de datos silenciosa por un cambio de padrón.
        cost_center = CostCenter.objects.create(code="CC738", name="MLP")
        aircraft = _aircraft("RPA-2019")
        today = timezone.localdate()
        permission = FlightPermission.objects.create(
            cost_center=cost_center,
            purpose="aerial_survey",
            area_type="dan91",
            status="approved",
            valid_from=today,
            valid_until=today + timedelta(days=30),
        )
        permission.aircraft_fleet.add(aircraft)
        aircraft.status = "retired"
        aircraft.save()

        offered = (
            FlightPermissionUpdateForm(instance=permission)
            .fields["aircraft_fleet"]
            .queryset
        )

        assert list(offered) == [aircraft]


@pytest.mark.django_db
class TestTheFormRenders:
    def test_the_create_form_uses_the_sectioned_template(self):
        response = login_as("add_flightpermission").get(reverse("permission-create"))
        content = response.content.decode()

        assert response.status_code == 200
        assert "data-roster" in content
        assert "data-roster-search" in content
        assert "roster-filter.js" in content

    def test_the_roster_carries_each_option_as_a_filterable_item(self):
        Operator.objects.create(employee_id="E-1", full_name="Álvaro Arias")

        content = (
            login_as("add_flightpermission")
            .get(reverse("permission-create"))
            .content.decode()
        )

        assert "data-roster-item" in content
        assert 'data-roster-text="Álvaro Arias"' in content

    def test_it_is_403_without_the_add_permission(self):
        assert (
            login_as("view_flightpermission")
            .get(reverse("permission-create"))
            .status_code
            == 403
        )


class TestTheFilterIsNotInlineJavascript:
    def test_the_template_has_no_inline_handler(self):
        source = TEMPLATE.read_text(encoding="utf-8")

        assert "onclick=" not in source
        assert "oninput=" not in source
        assert "<script" not in source

    def test_the_script_is_served_as_a_file(self):
        source = FORM_TEMPLATE.read_text(encoding="utf-8")

        assert "{% static 'js/roster-filter.js' %}" in source
        assert SCRIPT.exists()

    def test_the_script_carries_no_user_facing_text(self):
        # Los rótulos los traduce el servidor y viajan en `data-*`; un literal en
        # el JS saldría en inglés en la app en español y ningún guardián de
        # traducciones lo vería.
        source = SCRIPT.read_text(encoding="utf-8")

        assert "textContent = '" not in source
        assert "data-roster-count-label" in TEMPLATE.read_text(encoding="utf-8")
