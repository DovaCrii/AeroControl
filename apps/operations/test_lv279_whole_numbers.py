"""LV-279: SIGO no acepta decimales, así que la hoja entrega números cerrados.

Pedido del usuario (2026-10-06, captura de «Datos para SIGO»): segundos
`16.48`/`50.48` y distancia `206,8 km`, valores que el formulario rechaza.
Se redondea al presentar; lo guardado conserva su precisión.
"""

from decimal import Decimal

import pytest

from apps.geo.sections import whole
from apps.operations.flight_requests import sigo_sheet


class TestWhole:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [(206.8, 207), (16.48, 16), (50.48, 50), (0.5, 1), (1.5, 2), (2.5, 3)],
    )
    def test_half_goes_up_and_the_rest_to_the_nearest(self, value, expected):
        """`round(2.5)` da 2 (redondeo al par); una casilla de SIGO no puede
        depender de si el entero vecino es par."""
        assert whole(value) == expected

    def test_a_decimal_from_the_database_works_too(self):
        assert whole(Decimal("206.8")) == 207


class _Request:
    """Lo mínimo que lee `sigo_sheet`: sin base de datos."""

    center_lat = Decimal("-31.894392")
    center_lon = Decimal("-70.123456")
    amc = None
    amc_distance_km = Decimal("206.8")
    radius_m = 30
    altitude_m = 120
    hour_from = hour_to = None
    commune = area_name = ""

    area_modality = "center_point"
    vertices = []
    approx_flight_minutes = 0

    def get_request_type_display(self):
        return "Punto centro"

    def get_area_modality_display(self):
        return "Punto Centro"

    class work_items:  # noqa: N801
        @staticmethod
        def select_related(*args):
            return []


def test_the_sheet_has_no_decimals_anywhere():
    sheet = sigo_sheet(_Request())

    assert sheet["amc_distance_km"] == 207
    for key in ("lat_seconds", "lon_seconds"):
        assert isinstance(sheet[key], int)
    for key in ("lat_readable", "lon_readable"):
        assert "." not in sheet[key]
