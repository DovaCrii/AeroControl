"""LV-300: la habilitación escrita en la ficha del operador también cumple.

Reporte del usuario (2026-10-13): el sistema avisaba que un operador no cumplía las
habilitaciones, pero sí cumplía: tenía «Mavic-Phantom-Matrice / Series» en su ficha. La
comprobación sólo miraba las `Qualification` formales y los operadores importados de los
capítulos tienen su habilitación como texto libre. Criterio del usuario: *«si tiene una
parte del nombre del equipo ya cumple, como Mavic series»*.
"""

from types import SimpleNamespace

import pytest

from apps.registry.models import Aircraft, CostCenter, Operator
from apps.registry.selectors import (
    aircraft_series,
    operator_aircraft_compatibility_gaps,
)


@pytest.fixture
def centre(db):
    return CostCenter.objects.create(code="CC706", name="Centinela")


def _operator(centre, text, employee_id="E-1"):
    return Operator.objects.create(
        full_name="Luis Piña",
        employee_id=employee_id,
        authorizations=text,
        cost_center=centre,
    )


def _aircraft(centre, model, registration="RPA-1"):
    return Aircraft.objects.create(
        registration=registration,
        type="RPA",
        model=model,
        manufacturer="DJI",
        cost_center=centre,
    )


class TestTheSeriesOfAnAircraft:
    @pytest.mark.parametrize(
        ("model", "series"),
        [
            ("Mavic 3 Enterprise", "mavic"),
            ("MATRICE 300 RTK", "matrice"),
            ("Matrice-4 Thermal", "matrice"),
            ("Phantom 4 Pro", "phantom"),
            ("ELIOS3", "elios"),
            ("M3", ""),
            ("", ""),
            ("300 RTK", ""),
        ],
    )
    def test_it_is_the_first_word(self, model, series):
        assert aircraft_series(SimpleNamespace(model=model)) == series


@pytest.mark.django_db
class TestTheWrittenAuthorizationCounts:
    def test_the_series_in_the_free_text_covers_the_model(self, centre):
        operator = _operator(centre, "Mavic-Phantom-Matrice / Series")
        aircraft = _aircraft(centre, "Mavic 3 Enterprise")

        assert operator_aircraft_compatibility_gaps([operator], [aircraft]) == []

    def test_each_series_in_the_text_covers_its_own_models(self, centre):
        operator = _operator(centre, "Mavic-Phantom-Matrice / Series")
        fleet = [
            _aircraft(centre, "Matrice 300 RTK", "RPA-2"),
            _aircraft(centre, "Phantom 4 Pro", "RPA-3"),
        ]

        assert operator_aircraft_compatibility_gaps([operator], fleet) == []

    def test_case_and_accents_do_not_decide(self, centre):
        operator = _operator(centre, "MÁVIC series")
        aircraft = _aircraft(centre, "mavic 3")

        assert operator_aircraft_compatibility_gaps([operator], [aircraft]) == []

    def test_a_shared_word_of_another_series_does_not_cover(self, centre):
        """«Enterprise» está en modelos de series distintas: no basta."""
        operator = _operator(centre, "Mavic 3 Enterprise")
        aircraft = _aircraft(centre, "Matrice 4 Enterprise")

        assert operator_aircraft_compatibility_gaps([operator], [aircraft]) == [
            (operator, aircraft)
        ]

    def test_an_operator_without_text_or_qualification_is_still_a_gap(self, centre):
        operator = _operator(centre, "")
        aircraft = _aircraft(centre, "Mavic 3 Enterprise")

        assert operator_aircraft_compatibility_gaps([operator], [aircraft]) == [
            (operator, aircraft)
        ]

    def test_an_unrelated_text_is_a_gap(self, centre):
        operator = _operator(centre, "Autel EVO II")
        aircraft = _aircraft(centre, "Mavic 3 Enterprise")

        assert operator_aircraft_compatibility_gaps([operator], [aircraft]) == [
            (operator, aircraft)
        ]
