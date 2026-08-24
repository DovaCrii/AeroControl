"""R10.7: posicionar el catálogo de SIGO con las coordenadas del AIP-Chile.

El catálogo tenía **6 posiciones de 51**, así que "el más cercano" se elegía
entre seis. El AIP de la DGAC publica la posición de 452 aeródromos chilenos, y
cruzándolo por designador OACI cubre casi todo lo que faltaba **sin agregar
nombres nuevos**, que es la restricción que manda: la casilla del formulario de
SIGO sólo acepta lo que su propio selector ofrece.

El último test es el que fija la semántica, y hay que leerlo entero antes de
"arreglarlo": el AMC que la app propone es el más cercano **entre los que SIGO
ofrece**, no el más cercano del país.
"""

import csv

import pytest
from django.core.management import call_command

from apps.geo.sections import nearest_aerodromes
from apps.registry.management.commands.import_aip_aerodromes import (
    DATA_FILE,
    NAME_MISMATCH,
)
from apps.registry.models import Aerodrome

# Centro de "CG-01 | Circunferencia grande | Quebrada km 13.760", CC 738.
CG01 = (-31.906392, -70.717982)


def _catalog():
    return list(
        Aerodrome.objects.filter(
            is_active=True, latitude__isnull=False, longitude__isnull=False
        )
    )


class TestTheDataFile:
    def test_it_parses_and_every_row_is_usable(self):
        with DATA_FILE.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))

        # Sin número exacto: el AIP se actualiza y el CSV se regenera. Lo que se
        # fija es el orden de magnitud, que delata un volcado truncado.
        assert len(rows) > 400
        codes = [row["code"] for row in rows]
        assert len(codes) == len(set(codes)), "hay códigos OACI repetidos"
        for row in rows:
            assert 3 <= len(row["code"]) <= 10, row
            assert row["name"], row
            assert row["closed"] in {"0", "1"}, row
            assert row["use"] in {"", "PUB", "PVT", "MIL"}, row
            if row["latitude"]:
                # Chile continental, insular y antártico: nada al norte del
                # ecuador ni fuera del rango de longitudes válidas.
                assert -90 <= float(row["latitude"]) < 0, row
                assert -180 <= float(row["longitude"]) <= 0, row


@pytest.mark.django_db
class TestWhatItRefusesToDo:
    def test_it_never_creates_an_aerodrome(self):
        """La restricción del usuario, reafirmada el 2026-08-24: sólo entran los
        nombres que están en las capturas de SIGO. El AIP publica 452 y el
        selector del Estado ofrece muchos menos; uno que allá no se puede elegir
        no sirve de nada acá."""
        call_command("import_aip_aerodromes")

        assert Aerodrome.objects.count() == 0

    def test_it_leaves_a_code_the_two_sources_disagree_about(self):
        """`SCSA`: SIGO lo llama "Alberto Santos Dumont" (que es Río de Janeiro)
        y el AIP-Chile "Rungue Dr. C. Barría B.". El código es la llave, pero
        cuando el nombre la desmiente la llave no alcanza -- y una posición con
        cara de autoritativa y sin respaldo es lo que `LV-93` prohibió."""
        call_command("seed_aerodromes")
        assert "SCSA" in NAME_MISMATCH

        call_command("import_aip_aerodromes")

        assert Aerodrome.objects.get(code="SCSA").is_locatable is False


@pytest.mark.django_db
class TestPositioningTheCatalog:
    def test_it_fills_what_the_aip_knows_and_a_rerun_changes_nothing(self):
        call_command("seed_aerodromes")
        antes = len(_catalog())
        assert antes == 6  # el punto de partida que motivó la fila

        call_command("import_aip_aerodromes")
        despues = len(_catalog())

        # 9 de las 10 que el AIP cubre: `SCSA` queda fuera por la discrepancia.
        assert despues == 15
        # Y no aparecieron nombres nuevos.
        assert Aerodrome.objects.count() == 50

        call_command("import_aip_aerodromes")

        assert len(_catalog()) == despues

    def test_it_keeps_the_name_sigo_uses(self):
        """La regla 1. El AIP lo llama "Frutillar"; SIGO, "Ad. Frutillar". El
        segundo es el que la persona tiene que encontrar en el formulario."""
        call_command("seed_aerodromes")

        call_command("import_aip_aerodromes")

        frutillar = Aerodrome.objects.get(code="SCFR")
        assert frutillar.name == "Ad. Frutillar"
        assert frutillar.is_locatable

    def test_it_corrects_a_position_that_was_already_there(self):
        """La regla 2. Dos de las seis sembradas a mano estaban movidas: `SCEL`
        737 m y `SCBA` 417 m. En una distancia declarada al Estado eso se ve."""
        call_command("seed_aerodromes")
        antes = Aerodrome.objects.get(code="SCEL")
        assert float(antes.longitude) == pytest.approx(-70.7858)

        call_command("import_aip_aerodromes")

        despues = Aerodrome.objects.get(code="SCEL")
        assert float(despues.longitude) != pytest.approx(-70.7858)
        assert "AIP-Chile" in despues.notes

    def test_a_closed_aerodrome_stops_being_proposed(self):
        """La regla 3. `SCZC` (Casas Viejas) está cerrado en el AIP. No está en
        las capturas de SIGO, así que se monta el caso: si alguien lo agrega
        desde la app, la posición entra y el aeródromo queda fuera del cálculo.
        """
        Aerodrome.objects.create(code="SCZC", name="Casas Viejas")

        call_command("import_aip_aerodromes")

        casas_viejas = Aerodrome.objects.get(code="SCZC")
        assert casas_viejas.is_locatable
        assert casas_viejas.is_active is False
        assert casas_viejas not in _catalog()


@pytest.mark.django_db
class TestWhatTheAmcActuallyMeans:
    def test_the_proposed_amc_is_the_nearest_among_the_ones_sigo_offers(self):
        """**No es un error que este número sea grande.**

        Para `CG-01` la app propone Quintero a ~124 km teniendo Pichidangui
        (`SCDI`) a 79 km. Pichidangui **no está en el catálogo** porque no
        apareció en el selector de SIGO, y proponer algo que allá no se puede
        elegir dejaría a la persona con un dato que no puede usar.

        La forma de mejorar esta distancia no es tocar el cálculo: es **capturar
        el resto del selector de SIGO** (las imágenes del 2026-08-20 llegaban de
        la "A" hasta "Bermuda Intl") y volver a correr el posicionamiento.
        """
        call_command("seed_aerodromes")
        call_command("import_aip_aerodromes")

        propuesto, distancia_km = nearest_aerodromes(CG01, _catalog(), limit=1)[0]

        assert propuesto.code == "SCER"
        assert distancia_km == pytest.approx(124, abs=2)
        assert not Aerodrome.objects.filter(code="SCDI").exists()

    def test_positioning_did_not_change_which_aerodrome_wins_here(self):
        """Contrapeso: el posicionamiento agregó nueve aeródromos al cálculo, y
        ninguno de ellos está más cerca del Choapa que Quintero. Si un día este
        test cambia, es porque el catálogo creció -- que es justo lo que se
        espera, y entonces hay que revisar el número de arriba, no este."""
        call_command("seed_aerodromes")
        antes = nearest_aerodromes(CG01, _catalog(), limit=1)[0][0].code

        call_command("import_aip_aerodromes")
        despues = nearest_aerodromes(CG01, _catalog(), limit=1)[0][0].code

        assert antes == despues == "SCER"
