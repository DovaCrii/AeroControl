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


class TestASavedRegionAlsoKnowsWhereItCameFrom:
    """La contradicción que la mitad (b) dejó abierta, cerrada.

    La (b) sólo avisaba cuando la región se calculaba **al dibujar**. Pero
    `fill_permission_from_plan` venía escribiendo región y comuna deducidas del
    polígono **en los campos del permiso**, sin marca, así que una región que
    salió de un polígono y una copiada del papel DGAC eran indistinguibles en la
    base y en la ficha — y esas sí se presentaban como declaradas, que es
    exactamente lo que la fila prohibía.

    Ahora la procedencia es un campo (`operations.0026`), así que el aviso deja de
    depender de que la columna esté vacía.
    """

    @pytest.mark.django_db
    def test_filling_from_a_plan_marks_the_two_as_derived(self, db):
        permit = _permit()

        filled = permit.fill_location_gaps(
            latitude=Decimal("-33.450000"),
            longitude=Decimal("-70.660000"),
            radius_m=500,
            commune="Santiago",
            region="Región Metropolitana de Santiago",
        )

        permit.refresh_from_db()
        assert permit.region_source == FlightPermission.LOCATION_DERIVED
        assert permit.commune_source == FlightPermission.LOCATION_DERIVED
        # Y la procedencia **no** se le enumera a la persona como un campo que se
        # completó: `filled` es lo que la pantalla lista, y "se completó
        # region_source" no le dice nada a nadie.
        assert "region_source" not in filled
        assert "commune" in filled

    @pytest.mark.django_db
    def test_a_saved_derived_region_carries_the_bcn_warning(self, db):
        permit = _permit()
        permit.fill_location_gaps(
            latitude=Decimal("-33.450000"),
            longitude=Decimal("-70.660000"),
            radius_m=500,
            commune="Santiago",
            region="Región Metropolitana de Santiago",
        )

        body = _fiche(permit)

        assert "Santiago" in body
        assert "Derivada de las coordenadas" in body or "Derived from" in body
        assert "BCN" in body

    @pytest.mark.django_db
    def test_correcting_it_by_hand_stops_calling_it_derived(self, db):
        """El aviso que sobrevive a la corrección es peor que no tener aviso.

        La capa de la BCN está simplificada a ~111 m: cerca del borde devuelve la
        comuna vecina, y alguien la corrige. Si el marcador quedara en `derived`,
        la ficha seguiría diciendo "deducido de las coordenadas" sobre un valor
        que una persona verificó contra el papel — y ese aviso se cree.
        """
        permit = _permit()
        permit.fill_location_gaps(
            latitude=Decimal("-33.450000"),
            longitude=Decimal("-70.660000"),
            radius_m=500,
            commune="Santiago",
            region="Región Metropolitana de Santiago",
        )

        fresh = FlightPermission.objects.get(pk=permit.pk)
        fresh.commune = "Providencia"
        fresh.save()

        fresh.refresh_from_db()
        assert fresh.commune_source == FlightPermission.LOCATION_DECLARED
        # La región no se tocó, así que sigue siendo deducida: los dos campos se
        # razonan por separado, igual que al rellenarlos.
        assert fresh.region_source == FlightPermission.LOCATION_DERIVED

    @pytest.mark.django_db
    def test_the_correction_survives_an_update_fields_save(self, db):
        """Quien guarda con `update_fields` no tiene por qué acordarse del
        marcador; si el modelo no lo suma, la corrección se pierde en silencio."""
        permit = _permit()
        permit.fill_location_gaps(
            latitude=Decimal("-33.450000"),
            longitude=Decimal("-70.660000"),
            radius_m=500,
            commune="Santiago",
            region="Región Metropolitana de Santiago",
        )

        fresh = FlightPermission.objects.get(pk=permit.pk)
        fresh.commune = "Providencia"
        fresh.save(update_fields=["commune"])

        fresh.refresh_from_db()
        assert fresh.commune_source == FlightPermission.LOCATION_DECLARED

    @pytest.mark.django_db
    def test_emptying_it_is_not_declaring_it(self, db):
        """Un campo en blanco no tiene procedencia. Dejarle `declared`
        afirmaría que alguien declaró la nada."""
        permit = _permit()
        permit.fill_location_gaps(
            latitude=Decimal("-33.450000"),
            longitude=Decimal("-70.660000"),
            radius_m=500,
            commune="Santiago",
            region="Región Metropolitana de Santiago",
        )

        fresh = FlightPermission.objects.get(pk=permit.pk)
        fresh.commune = ""
        fresh.save()

        fresh.refresh_from_db()
        assert fresh.commune_source == ""

    @pytest.mark.django_db
    def test_a_permit_that_predates_the_field_shows_no_warning(self, db):
        """Vacío es *no se sabe*, y se dibuja como siempre.

        La migración no rellena nada a propósito: no hay forma honesta de saber
        cuáles de los permisos ya cargados se teclearon del papel y cuáles las
        escribió el plan. Lo que sí tiene que cumplirse es que **nada
        retroceda**: sin marcador, la ficha se ve como antes.
        """
        permit = _permit(region="Coquimbo", commune="Los Vilos")
        # Se fuerza el estado anterior a la migración por la vía que no dispara
        # el modelo, porque crear ya marca `declared` -- y lo que se quiere
        # reproducir acá es justamente una fila sin marcador.
        FlightPermission.objects.filter(pk=permit.pk).update(
            region_source="", commune_source=""
        )

        body = _fiche(permit)

        assert "Coquimbo" in body
        assert "Derivada de las coordenadas" not in body
        assert "Derived from" not in body

    @pytest.mark.django_db
    def test_creating_a_permit_with_a_region_records_it_as_declared(self, db):
        """`fill_location_gaps` sólo rellena huecos de permisos que ya existen,
        así que lo único que escribe una región al crear es alguien copiándola
        del papel. Dejarla en "no se sabe" descartaría algo que sí se sabe."""
        permit = _permit(region="Coquimbo")

        assert permit.region_source == FlightPermission.LOCATION_DECLARED
        # La comuna quedó vacía, y vacío no tiene procedencia.
        assert permit.commune_source == ""
