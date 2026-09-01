"""LV-220: la región tiene que aparecer en la ficha del permiso.

Textual del usuario, mirando `JEJ-2026-001`: *"sumar ahí que debe aparecer la
región"*. La fila existía, pero envuelta en un `{% if region or commune or
area_name %}`: con los tres vacíos **desaparecía entera**. Y se vacían a menudo,
porque `LV-197` sacó esas casillas del alta y ahora sólo las trae un plan
vinculado.

Una fila ausente no se distingue de un dato que no aplica, y la región sí aplica:
la DGAC la pide en el formulario del SIGO. Misma lectura que `LV-146` para el chip
de faena — el caso vacío es un caso real y se dice.
"""

import pytest
from django.urls import reverse

from apps.core.testing import login_as
from apps.registry.models import CostCenter

from .models import FlightPermission


def _permit(**extra):
    cc = CostCenter.objects.create(code="CC1", name="Uno", operates_flights=True)
    return FlightPermission.objects.create(
        cost_center=cc,
        purpose="photogrammetry",
        status=FlightPermission.STATUS_REQUESTED,
        location="Tranque el Mauro",
        area_type="unpopulated",
        **extra,
    )


def _fiche(permission):
    client = login_as("view_flightpermission")
    return client.get(
        reverse("permission-detail", args=[permission.pk])
    ).content.decode()


class TestTheRowIsAlwaysThere:
    @pytest.mark.django_db
    def test_an_empty_region_says_so_instead_of_vanishing(self, db):
        body = _fiche(_permit())

        # **La etiqueta se pide al catálogo, no se escribe.** `"Región" in body`
        # también pasaba, pero no discrimina: cualquier otro rótulo de la página
        # que contenga la palabra lo satisface, y con el `{% if %}` viejo puesto
        # de vuelta el test seguiría verde. Y escribir el texto en español a mano
        # es la trampa de `LV-95`: pasa en aislado y falla en la suite completa
        # según qué idioma dejó activo otro test.
        from django.utils.translation import gettext

        assert gettext("Region / Commune") in body

    @pytest.mark.django_db
    def test_a_recorded_region_is_shown(self, db):
        body = _fiche(_permit(region="Coquimbo", commune="Los Vilos"))

        assert "Coquimbo" in body
        assert "Los Vilos" in body

    @pytest.mark.django_db
    def test_the_area_name_still_leads_when_it_exists(self, db):
        """No se cambió el formato de la fila llena, sólo el caso vacío."""
        body = _fiche(_permit(area_name="El Mauro", region="Coquimbo"))

        assert "El Mauro" in body
        assert "Coquimbo" in body


class TestTheRegionIsNeverDerived:
    @pytest.mark.django_db
    def test_coordinates_alone_do_not_produce_a_region(self, db):
        """Mitad (b) de la fila, deliberadamente sin hacer.

        El permiso tiene coordenadas y aun así la región queda "sin informar".
        Derivarla de la coordenada y dibujarla igual que una declarada haría que
        quien llena el SIGO no pueda distinguir el dato del papel de una
        inferencia nuestra. Este test fija esa decisión: el día que se derive,
        tendrá que decir que se derivó, y este test es el que hay que cambiar
        **a propósito**.
        """
        from decimal import Decimal

        body = _fiche(_permit(latitude=Decimal("-31.90"), longitude=Decimal("-71.51")))

        assert "Coquimbo" not in body
