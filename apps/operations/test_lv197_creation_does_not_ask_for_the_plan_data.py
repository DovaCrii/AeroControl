"""LV-197: el alta tampoco pide los datos que el plan trae.

Segunda mitad del pedido de `LV-166`, hecha cuando el usuario volvió a mirar el
formulario de alta: *"quitar esos elementos del permiso […] ya que saldrán
automáticos […] que el operador no la llene, pero que siempre se llene con el
geoespacial es clave, así ahorra espacio en la propuesta"*. Su frase de `LV-166`
había sido casi la misma, y esa fila **excluyó el alta a propósito**: no hay
`pk`, el plan se elige en ese mismo formulario, así que al dibujarlo no hay nada
de dónde sacar el dato.

Lo que cambia no es esa observación sino la política que se deduce de ella. Que
el dato no esté *todavía* no es razón para pedirlo a mano, porque **hay tres
caminos para llenarlo y ninguno es tipearlo**: elegir el plan en el alta
(`source_plan`, que rellena al guardar), vincularlo después en la ficha
(`R10.2`), o editar el permiso — que es donde siguen a la vista mientras estén
vacíos, y por eso esto no cierra ninguna puerta.

Los dos que no se tocan, por lo que `LV-166` ya había escrito: `max_altitude_m`
porque **ningún KMZ trae altitud** —esconderla la dejaría sin forma de cargarse—
y `location`, el texto libre obligatorio, con el que un permiso nunca nace sin
decir dónde vuela.
"""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.core.testing import login_as
from apps.operations.forms import FlightPermissionForm, FlightPermissionUpdateForm
from apps.operations.models import FlightPermission
from apps.registry.models import CostCenter

TODAY = timezone.localdate()
FROM_THE_PLAN = FlightPermissionForm.PLAN_PROVIDED_FIELDS


@pytest.fixture
def center(db):
    return CostCenter.objects.create(code="CC738", name="MLP")


def _permit(center, **overrides):
    values = {
        "internal_folio": "JEJ-2026-197",
        "cost_center": center,
        "purpose": "patrol",
        "valid_from": TODAY,
        "valid_until": TODAY + timedelta(days=60),
        "location": "Quebrada km 13",
        "area_type": "unpopulated",
    }
    values.update(overrides)
    return FlightPermission.objects.create(**values)


@pytest.mark.django_db
class TestTheCreationForm:
    def test_it_does_not_ask_for_what_the_plan_provides(self):
        form = FlightPermissionForm()

        for name in FROM_THE_PLAN:
            assert name not in form.fields, name

    def test_it_still_asks_for_the_altitude(self):
        """Ningún KMZ la trae. Esconderla la dejaría sin ninguna forma de
        cargarse, que es lo que `LV-166` dejó escrito al elegir su lista."""
        assert "max_altitude_m" in FlightPermissionForm().fields

    def test_it_still_asks_where_it_flies_in_words(self):
        """`location` es el texto libre obligatorio: con él, un permiso no puede
        nacer sin decir dónde vuela, aunque no traiga coordenadas."""
        assert "location" in FlightPermissionForm().fields

    def test_it_still_offers_the_plan_selector(self):
        """El camino que reemplaza al tipeo. Si esto se fuera, quitar las casillas
        habría dejado el alta sin ninguna forma de traer la ubicación."""
        assert "source_plan" in FlightPermissionForm().fields

    def test_the_manual_escape_brings_them_back(self):
        """La misma puerta que `LV-166` dejó para el papel de la DGAC, que tiene
        más autoridad que lo preparado antes de presentar."""
        form = FlightPermissionForm(manual_location=True)

        for name in FROM_THE_PLAN:
            assert name in form.fields, name

    def test_the_escape_works_on_the_page_too(self, center):
        """El escape tiene que existir en **las dos** pantallas: hasta acá vivía
        sólo en la edición, así que el alta lo habría perdido justo al empezar a
        esconder las casillas."""
        client = login_as("add_flightpermission", "view_flightpermission")

        content = client.get(
            reverse("permission-create"), {"ubicacion": "manual"}
        ).content.decode()

        assert "Latitud" in content

    def test_the_plain_page_does_not_show_them(self, center):
        content = (
            login_as("add_flightpermission", "view_flightpermission")
            .get(reverse("permission-create"))
            .content.decode()
        )

        assert "Latitud" not in content


@pytest.mark.django_db
class TestTheEditFormStillOffersThem:
    def test_a_permit_with_no_plan_can_still_be_completed_by_hand(self, center):
        """**La razón de que esto no cierre ninguna puerta.** Si el plan no trajo
        la comuna —o no hay plan—, la pantalla de edición la sigue pidiendo."""
        form = FlightPermissionUpdateForm(instance=_permit(center))

        for name in FROM_THE_PLAN:
            assert name in form.fields, name

    def test_what_the_plan_already_filled_stays_hidden(self, center):
        """El comportamiento de `LV-166`, intacto: se esconde el campo que ya
        tiene valor **y** un plan vinculado del que salió."""
        from django.contrib.auth.models import User

        from apps.geo.models import GeoPlan

        permit = _permit(center, latitude=-24.25, longitude=-70.0)
        GeoPlan.objects.create(
            title="CG-02",
            cost_center=center,
            created_by=User.objects.create_user("autor-197"),
            flight_permission=permit,
        )

        form = FlightPermissionUpdateForm(instance=permit)

        assert "latitude" not in form.fields
        # La comuna sigue vacía, así que sigue pidiéndose: la regla mira el valor
        # y no una lista fija, que es lo que `LV-166` decidió y sigue valiendo.
        assert "commune" in form.fields
