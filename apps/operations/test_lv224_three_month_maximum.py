"""LV-224: la DGAC autoriza 3 meses como máximo.

Textual del usuario: *"además es importante sumar que como fecha límite o máxima,
o mensaje que indique, que duración máxima de permisos son por la DGAC 3 meses"*.
El dato salió de armar el informe mensual de reportabilidad RPA
(`SPEC_REPORTE_MENSUAL_RPA.md` §4.1), donde gobierna todo el calendario: la
renovación no es automática, exige una carta nueva del mandante.

**Es el complemento de `LV-219`.** Esa fila movió la vigencia al momento de
aprobar; ésta acota el rango que se escribe entonces. Sin el techo, un `2027`
tecleado por `2026` produce un permiso que la app cree vigente nueve meses de más,
con sus alertas, su fila en el calendario y su aporte al porcentaje de vigentes.

**Rechaza, pero con salida.** Un rechazo sin escape obligaría a falsear una fecha
el día que la DGAC otorgue un plazo distinto, que es el mal que `LV-219` acaba de
quitar del alta. El patrón es el de `LV-101`: lo excepcional se permite y deja un
motivo escrito.
"""

from datetime import date

import pytest
from django.core.exceptions import ValidationError

from apps.registry.models import Aircraft, CostCenter, Operator

from .forms import FlightPermissionForm
from .models import FlightPermission


def _cc(code="CC1"):
    return CostCenter.objects.create(code=code, name=code, operates_flights=True)


def _roster(cc):
    operator = Operator.objects.create(
        employee_id="P1", full_name="Pilot One", cost_center=cc
    )
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Fixed",
        model="A",
        manufacturer="Maker",
        cost_center=cc,
    )
    return operator, aircraft


def _permit(cc, **extra):
    extra.setdefault("status", FlightPermission.STATUS_REQUESTED)
    return FlightPermission.objects.create(
        cost_center=cc,
        purpose="photogrammetry",
        location="Site",
        area_type="unpopulated",
        **extra,
    )


class TestTheLimitIsThreeCalendarMonths:
    """Meses calendario, no 90 días: la diferencia mueve una fecha real."""

    @pytest.mark.django_db
    def test_the_spec_example_lands_on_the_same_day_three_months_later(self, db):
        """Criterio 5 del SPEC: emitido 2026-07-04 vence 2026-10-04.

        Con `+90 días` daría 2026-10-02. Dos días de vigencia que la app diría de
        menos, y dos días de corrimiento en cada alerta encadenada.
        """
        permit = _permit(_cc(), valid_from=date(2026, 7, 4))

        assert permit.latest_allowed_valid_until() == date(2026, 10, 4)

    @pytest.mark.django_db
    def test_a_day_that_does_not_exist_in_the_target_month_is_clamped(self, db):
        """30 de noviembre + 3 meses = fin de febrero, no un 30 imposible."""
        permit = _permit(_cc(), valid_from=date(2026, 11, 30))

        # 2027 no es bisiesto.
        assert permit.latest_allowed_valid_until() == date(2027, 2, 28)

    @pytest.mark.django_db
    def test_a_leap_february_is_respected(self, db):
        permit = _permit(_cc(), valid_from=date(2027, 11, 30))

        assert permit.latest_allowed_valid_until() == date(2028, 2, 29)

    @pytest.mark.django_db
    def test_it_crosses_the_year_end(self, db):
        permit = _permit(_cc(), valid_from=date(2026, 12, 15))

        assert permit.latest_allowed_valid_until() == date(2027, 3, 15)

    @pytest.mark.django_db
    def test_without_a_start_date_there_is_no_ceiling(self, db):
        """Pasa a menudo desde `LV-219`: el permiso pedido no tiene fechas."""
        assert _permit(_cc()).latest_allowed_valid_until() is None


class TestTheModelEnforcesIt:
    @pytest.mark.django_db
    def test_exactly_three_months_is_accepted(self, db):
        """El caso normal, y el borde: el límite es inclusive."""
        permit = _permit(
            _cc(), valid_from=date(2026, 7, 4), valid_until=date(2026, 10, 4)
        )

        permit.clean()  # no levanta

    @pytest.mark.django_db
    def test_one_day_over_is_rejected(self, db):
        permit = _permit(
            _cc(), valid_from=date(2026, 7, 4), valid_until=date(2026, 10, 5)
        )

        with pytest.raises(ValidationError) as raised:
            permit.clean()

        assert "valid_until" in raised.value.message_dict

    @pytest.mark.django_db
    def test_the_error_names_the_latest_allowed_date(self, db):
        """Decir "tres meses" sin decir cuál es la fecha obliga a calcularla."""
        permit = _permit(
            _cc(), valid_from=date(2026, 7, 4), valid_until=date(2027, 1, 4)
        )

        with pytest.raises(ValidationError) as raised:
            permit.clean()

        assert "2026-10-04" in str(raised.value.message_dict["valid_until"])

    @pytest.mark.django_db
    def test_a_written_reason_lets_the_long_window_through(self, db):
        permit = _permit(
            _cc(),
            valid_from=date(2026, 7, 4),
            valid_until=date(2027, 1, 4),
            validity_override_reason="Resolución DGAC 1234 otorga 6 meses",
        )

        permit.clean()  # no levanta

    @pytest.mark.django_db
    def test_whitespace_is_not_a_reason(self, db):
        """Un espacio en la casilla no es una justificación."""
        permit = _permit(
            _cc(),
            valid_from=date(2026, 7, 4),
            valid_until=date(2027, 1, 4),
            validity_override_reason="   ",
        )

        with pytest.raises(ValidationError):
            permit.clean()

    @pytest.mark.django_db
    def test_the_reason_is_ignored_when_the_window_is_normal(self, db):
        """Vacío no es "no aplica" sino "no hizo falta"."""
        permit = _permit(
            _cc(), valid_from=date(2026, 7, 4), valid_until=date(2026, 8, 4)
        )

        permit.clean()  # no levanta, con o sin motivo


class TestTheFormMirrorsIt:
    """`AGENTS.md`: la regla del modelo tiene su espejo en el formulario."""

    @pytest.mark.django_db
    def test_the_form_rejects_a_window_over_three_months(self, db):
        cc = _cc()
        operator, aircraft = _roster(cc)
        form = FlightPermissionForm(
            data={
                "status": "requested",
                "purpose": "photogrammetry",
                "location": "Site",
                "area_type": "unpopulated",
                "cost_center": str(cc.pk),
                "operators": [str(operator.pk)],
                "aircraft_fleet": [str(aircraft.pk)],
                "valid_from": "2026-07-04",
                "valid_until": "2027-01-04",
            }
        )

        assert not form.is_valid()
        assert "valid_until" in form.errors

    @pytest.mark.django_db
    def test_the_form_accepts_it_with_a_reason(self, db):
        cc = _cc()
        operator, aircraft = _roster(cc)
        form = FlightPermissionForm(
            data={
                "status": "requested",
                "purpose": "photogrammetry",
                "location": "Site",
                "area_type": "unpopulated",
                "cost_center": str(cc.pk),
                "operators": [str(operator.pk)],
                "aircraft_fleet": [str(aircraft.pk)],
                "valid_from": "2026-07-04",
                "valid_until": "2027-01-04",
                "validity_override_reason": "Resolución DGAC 1234",
            }
        )

        assert form.is_valid(), form.errors


class TestTheEscapeFieldReachesTheScreen:
    @pytest.mark.django_db
    def test_the_field_is_rendered_by_the_form_template(self, db):
        """`LV-211`: un campo en `Meta.fields` y ausente de la plantilla se borra.

        Esta plantilla dibuja campo por campo, así que el campo nuevo tiene que
        estar listado — si no, llega vacío en cada POST y el motivo escrito se
        pierde justo cuando hace falta.
        """
        from pathlib import Path

        template = Path("templates/operations/permission_form.html").read_text(
            encoding="utf-8"
        )

        assert "form.validity_override_reason" in template

    @pytest.mark.django_db
    def test_editing_a_permit_does_not_wipe_the_reason(self, db):
        """El escenario real de pérdida, no sólo la presencia en la plantilla."""
        from .forms import FlightPermissionUpdateForm

        cc = _cc()
        operator, aircraft = _roster(cc)
        permit = _permit(
            cc,
            valid_from=date(2026, 7, 4),
            valid_until=date(2027, 1, 4),
            validity_override_reason="Resolución DGAC 1234",
        )
        permit.operators.add(operator)
        permit.aircraft_fleet.add(aircraft)

        form = FlightPermissionUpdateForm(
            instance=permit,
            data={
                "purpose": "photogrammetry",
                "location": "Otro sitio",  # se cambia sólo esto
                "area_type": "unpopulated",
                "cost_center": str(cc.pk),
                "operators": [str(operator.pk)],
                "aircraft_fleet": [str(aircraft.pk)],
                "valid_from": "2026-07-04",
                "valid_until": "2027-01-04",
                "validity_override_reason": "Resolución DGAC 1234",
            },
        )

        assert form.is_valid(), form.errors
        saved = form.save()
        assert saved.validity_override_reason == "Resolución DGAC 1234"
