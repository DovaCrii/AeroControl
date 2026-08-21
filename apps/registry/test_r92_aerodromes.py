"""R9.2: el catálogo de aeródromos y el cálculo del AMC.

La solicitud de vuelo de SIGO pide "Aeródromo más Cercano (AMC)" y "Distancia
al AMC (Kilómetros)". La lista se copia del selector de SIGO (decisión del
usuario, 2026-08-20) y las coordenadas se siembran **sólo cuando son
verificables**: una distancia calculada contra una posición inventada se ve
autoritativa y no lo es.
"""

import pytest
from django.core.management import call_command

from apps.geo.sections import nearest_aerodromes
from apps.registry.models import Aerodrome

# Centro real de "Quebrada km 13.760" en el KMZ de MLP.
MLP_CENTER = (-31.89439167, -70.70220833)


@pytest.fixture
def catalog(db):
    call_command("seed_aerodromes")
    return Aerodrome.objects


class TestTheCatalog:
    @pytest.mark.django_db
    def test_it_seeds_the_list_from_the_sigo_screenshots(self, catalog):
        """No es una base aeronáutica: es lo que el selector de SIGO ofrece.
        Ofrecer un nombre que ese selector no tiene sería inútil, porque el
        dato se copia a mano allá."""
        assert catalog.filter(code="SCEL").exists()
        assert catalog.filter(code="OMAA").exists()  # Abu Dhabi: la lista es global
        assert catalog.count() >= 50

    @pytest.mark.django_db
    def test_it_is_idempotent_and_does_not_overwrite_a_filled_coordinate(self, catalog):
        """Alguien completa a mano la posición que el seed dejó en blanco; un
        rerun no puede pisarla."""
        aerodrome = catalog.get(code="OMAA")
        aerodrome.latitude, aerodrome.longitude = 24.433, 54.651
        aerodrome.save(update_fields=["latitude", "longitude", "updated_at"])
        before = catalog.count()

        call_command("seed_aerodromes")

        aerodrome.refresh_from_db()
        assert catalog.count() == before
        assert float(aerodrome.latitude) == 24.433

    @pytest.mark.django_db
    def test_unverified_positions_stay_blank(self, catalog):
        """La mitad que evita el dato falso-autoritativo: sin coordenada no hay
        distancia, y eso es más honesto que una distancia inventada."""
        assert catalog.get(code="TXKF").latitude is None
        assert catalog.get(code="SCEL").latitude is not None

    @pytest.mark.django_db
    def test_is_locatable_says_who_can_take_part(self, catalog):
        assert catalog.get(code="SCEL").is_locatable is True
        assert catalog.get(code="TXKF").is_locatable is False


class TestNearestAerodrome:
    @pytest.mark.django_db
    def test_the_real_mlp_center_resolves_to_quintero(self, catalog):
        """Caso real: las quebradas de MLP quedan a ~126 km de Quintero, que es
        el aeródromo con coordenadas más cercano del catálogo."""
        ranked = nearest_aerodromes(MLP_CENTER, list(catalog.all()))

        aerodrome, distance_km = ranked[0]
        assert aerodrome.code == "SCER"
        assert 120 < distance_km < 130

    @pytest.mark.django_db
    def test_it_returns_runners_up_so_a_person_can_doubt(self, catalog):
        """La casilla de SIGO es una sola, pero la persona confirma contra la
        carta AIP: un segundo candidato a distancia parecida es justo lo que
        necesita ver. Con una sola respuesta la pantalla no daría margen."""
        ranked = nearest_aerodromes(MLP_CENTER, list(catalog.all()))

        assert len(ranked) == 3
        assert ranked[0][1] <= ranked[1][1] <= ranked[2][1]

    @pytest.mark.django_db
    def test_aerodromes_without_coordinates_are_skipped_not_pushed_last(self, catalog):
        """Un aeródromo sin posición no puede ser "el más cercano". Se ignora,
        y quien llama cuenta cuántos quedaron fuera para decirlo en pantalla."""
        ranked = nearest_aerodromes(MLP_CENTER, list(catalog.all()), limit=99)

        assert all(a.is_locatable for a, _d in ranked)
        assert len(ranked) == catalog.filter(latitude__isnull=False).count()

    @pytest.mark.django_db
    def test_an_empty_catalog_yields_nothing_rather_than_guessing(self, db):
        assert nearest_aerodromes(MLP_CENTER, []) == []
