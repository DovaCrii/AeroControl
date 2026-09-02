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

from decimal import Decimal

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


class TestADerivedRegionSaysThatItWasDerived:
    """**Mitad (b), hecha — y este archivo es el que la fila mandaba cambiar.**

    Antes decía `TestTheRegionIsNeverDerived` y afirmaba que un permiso con
    coordenadas seguía mostrando "Sin informar". Su docstring anunciaba
    literalmente que *"el día que se derive, tendrá que decir que se derivó, y
    este test es el que hay que cambiar a propósito"*. Ese día es hoy, y lo que
    se conserva es **la condición**, no la prohibición: lo derivado se dibuja
    con su propio rótulo y con el aviso de la BCN, nunca con el aspecto de un
    dato declarado.
    """

    # Santiago centro. Se usa un punto **verificado contra la capa real** en vez
    # de uno elegido a ojo: las coordenadas del test anterior (-31.90, -71.51,
    # cerca de Los Vilos) devuelven `None`, porque la capa de la BCN está
    # simplificada a ~111 m y ahí no cubre. O sea que aquel test pasaba en parte
    # por la razón vecina — no sólo porque no se derivara.
    COVERED = (Decimal("-33.45"), Decimal("-70.66"))
    # Verificado que cae fuera de la cobertura, y sirve mejor que un punto en
    # medio del Pacífico: es un lugar donde alguien podría volar de verdad.
    UNCOVERED = (Decimal("-31.90"), Decimal("-71.51"))

    @pytest.mark.django_db
    def test_coordinates_produce_a_region_that_is_labelled_as_derived(self, db):
        latitude, longitude = self.COVERED

        body = _fiche(_permit(latitude=latitude, longitude=longitude))

        assert "Santiago" in body
        # Y **no** se disfraza de dato declarado: la fila sigue diciendo que no
        # hay nada informado, y lo deducido va aparte, rotulado y con el aviso
        # de la BCN.
        assert "Sin informar" in body or "Not recorded" in body
        assert "Derivada de las coordenadas" in body or "Derived from" in body
        assert "BCN" in body

    @pytest.mark.django_db
    def test_a_declared_region_is_not_overwritten_by_the_derivation(self, db):
        """Un permiso con región en el papel no necesita que se la deduzcan, y
        sobreponerle una inferencia sería reemplazar el dato bueno por uno
        aproximado."""
        latitude, longitude = self.COVERED

        body = _fiche(
            _permit(
                region="Región de Coquimbo",
                commune="Los Vilos",
                latitude=latitude,
                longitude=longitude,
            )
        )

        assert "Región de Coquimbo" in body
        assert "Derivada de las coordenadas" not in body
        assert "Derived from" not in body

    @pytest.mark.django_db
    def test_outside_the_covered_area_it_says_nothing_instead_of_guessing(self, db):
        """`locate` devuelve `None` fuera de cobertura y ese `None` se propaga.

        La respuesta honesta es la misma que antes: "Sin informar". Deducir algo
        aproximado ahí sería peor que no deducir nada.
        """
        latitude, longitude = self.UNCOVERED

        body = _fiche(_permit(latitude=latitude, longitude=longitude))

        assert "Sin informar" in body or "Not recorded" in body
        assert "Derivada de las coordenadas" not in body
        assert "Derived from" not in body
