"""LV-221: el diagnóstico de altitudes antes de tocar la unidad.

Pedido del usuario, textual: *"sumar eso, la altitud es en unidad metros como
trabajamos"*. El campo es `max_altitude_ft` y en su captura hay un **120**, que
en pies son 36,6 m — mientras 120 **metros** es el techo real de trabajo (394 ft).

**El riesgo no es el rótulo, son los datos.** Cambiar la unidad del campo sin
saber cuáles están mal cargados convertiría un dato equivocado en otro dato
equivocado con otra etiqueta, así que la fila exige medir producción primero.
Estos tests cubren la heurística de ese diagnóstico: es lo único que se puede
afirmar sin la autorización de la DGAC en la mano.
"""

from io import StringIO

import pytest
from django.core.management import call_command

from apps.registry.models import CostCenter

from .models import FlightPermission


def _permit(cc, altitude, folio_hint=""):
    return FlightPermission.objects.create(
        cost_center=cc,
        purpose="photogrammetry",
        status=FlightPermission.STATUS_REQUESTED,
        location=folio_hint or "Site",
        area_type="unpopulated",
        max_altitude_ft=altitude,
    )


@pytest.fixture
def cc(db):
    return CostCenter.objects.create(code="CC1", name="Uno", operates_flights=True)


def _run():
    out = StringIO()
    call_command("check_altitudes", stdout=out)
    return out.getvalue()


class TestTheHeuristicFlagsWhatLooksLikeMetres:
    @pytest.mark.django_db
    def test_the_users_own_case_is_flagged(self, cc):
        """El 120 de la captura: en pies son 36 m, que no es altitud de trabajo."""
        _permit(cc, 120)

        body = _run()

        assert "REVISAR" in body
        # Y dice la cifra que sirve para corregir: 120 m son 394 ft.
        assert "394 ft" in body

    @pytest.mark.django_db
    def test_a_plausible_altitude_is_left_alone(self, cc):
        """394 ft (120 m) es exactamente el techo de trabajo: no se toca."""
        _permit(cc, 394)

        body = _run()

        assert "REVISAR" not in body
        assert "1 plausibles, 0 a revisar" in body

    @pytest.mark.django_db
    def test_something_over_the_dan_151_ceiling_is_flagged(self, cc):
        """El techo son 130 m AGL (426 ft): más que eso no sale de una DGAC normal."""
        _permit(cc, 1200)

        body = _run()

        assert "REVISAR" in body
        assert "DAN 151" in body

    @pytest.mark.django_db
    def test_the_boundaries_are_inclusive_where_they_should_be(self, cc):
        """150 ft pasa y 149 no: el umbral tiene que ser un borde y no una zona."""
        _permit(cc, 150)
        _permit(cc, 149)

        body = _run()

        assert "1 plausibles, 1 a revisar" in body

    @pytest.mark.django_db
    def test_permits_without_an_altitude_are_counted_apart(self, cc):
        """Sin dato no es sospechoso: el campo es nulo por los permisos viejos."""
        FlightPermission.objects.create(
            cost_center=cc,
            purpose="photogrammetry",
            status=FlightPermission.STATUS_REQUESTED,
            location="Site",
            area_type="unpopulated",
        )

        body = _run()

        assert "(1 sin dato)" in body
        assert "REVISAR" not in body

    @pytest.mark.django_db
    def test_it_writes_nothing(self, cc):
        """Cuál valor está mal lo sabe quien tiene el papel, no una heurística."""
        permit = _permit(cc, 120)

        _run()

        permit.refresh_from_db()
        assert permit.max_altitude_ft == 120
