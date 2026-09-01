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


class TestThePermitNowStoresMetres:
    """Paso 2: la unidad cambia, y con ella desaparece una clase de error."""

    @pytest.mark.django_db
    def test_the_form_asks_for_metres(self, cc):
        from .forms import FlightPermissionForm

        fields = FlightPermissionForm().fields

        assert "max_altitude_m" in fields
        # El viejo sale de la pantalla y se queda en la base (ver el modelo).
        assert "max_altitude_ft" not in fields

    @pytest.mark.django_db
    def test_the_label_says_metres(self, cc):
        from .forms import FlightPermissionForm

        label = str(FlightPermissionForm().fields["max_altitude_m"].label)

        assert "m)" in label
        assert "ft" not in label

    @pytest.mark.django_db
    def test_the_feet_equivalent_is_calculated_not_stored(self, cc):
        """El caso del usuario: 120 m se transcriben al SIGO como 394 ft."""
        permit = FlightPermission.objects.create(
            cost_center=cc,
            purpose="photogrammetry",
            status=FlightPermission.STATUS_REQUESTED,
            location="Site",
            area_type="unpopulated",
            max_altitude_m=120,
        )

        assert permit.max_altitude_ft_equivalent == 394
        # Y no se guardó en ninguna columna: dos columnas con el mismo hecho en
        # distinta unidad son dos columnas que se desincronizan — el estado del
        # que viene esta fila.
        assert permit.max_altitude_ft is None

    @pytest.mark.django_db
    def test_no_altitude_means_no_equivalent(self, cc):
        permit = FlightPermission.objects.create(
            cost_center=cc,
            purpose="photogrammetry",
            status=FlightPermission.STATUS_REQUESTED,
            location="Site",
            area_type="unpopulated",
        )

        assert permit.max_altitude_ft_equivalent is None

    @pytest.mark.django_db
    def test_the_plan_no_longer_converts(self, cc):
        """La conversión que protegía una ruta y faltaba en la otra, eliminada.

        `fill_location_gaps` hacía `round(altitude_m * 3.28084)`. Ahora copia, y
        por eso el formulario manual ya no puede producir el error que el KMZ
        tenía cubierto.
        """
        permit = FlightPermission.objects.create(
            cost_center=cc,
            purpose="photogrammetry",
            status=FlightPermission.STATUS_REQUESTED,
            location="Site",
            area_type="unpopulated",
        )

        filled = permit.fill_location_gaps(altitude_m=120)

        assert permit.max_altitude_m == 120
        assert "max_altitude_m" in filled

    @pytest.mark.django_db
    def test_the_fiche_shows_both_units(self, cc):
        """Metros porque es como se opera; pies porque es lo que pide el SIGO."""
        from django.urls import reverse

        from apps.core.testing import login_as

        permit = FlightPermission.objects.create(
            cost_center=cc,
            purpose="photogrammetry",
            status=FlightPermission.STATUS_REQUESTED,
            location="Site",
            area_type="unpopulated",
            max_altitude_m=120,
        )
        body = (
            login_as("view_flightpermission")
            .get(reverse("permission-detail", args=[permit.pk]))
            .content.decode()
        )

        assert "120 m" in body
        assert "394 ft" in body


class TestTheMigrationCorrectedTheLabelNotTheNumber:
    @pytest.mark.django_db
    def test_the_migration_copies_without_converting(self, cc):
        """**Lo contrario de una conversión de unidades, y a propósito.**

        No se convirtieron pies a metros: se corrigió la etiqueta de un dato que
        siempre estuvo en metros. Aplicar `/ 3.28084` habría dejado 36 m donde la
        operación quiso 120 — el error que esta fila vino a cerrar.

        Sólo era válido porque se midió primero (`check_altitudes`): 3 filas,
        todas con el mismo valor y ninguna aprobada. Este test fija el criterio
        para que nadie "arregle" la migración añadiéndole la conversión.
        """
        from pathlib import Path

        source = Path(
            "apps/operations/migrations/0025_flightpermission_max_altitude_m.py"
        ).read_text(encoding="utf-8")
        # Se mira **el código y no el archivo entero**: el docstring del módulo
        # menciona el factor a propósito, para explicar por qué no se aplica.
        # Buscarlo en todo el texto reprobaba la explicación junto con el error.
        code = source.split('"""', 2)[2]

        assert "3.28084" not in code
        assert "max_altitude_m = row.max_altitude_ft" in code
