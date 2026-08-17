"""LV-112/LV-113: dos defectos de la bandeja, encontrados analizándola.

Salieron del análisis que el usuario pidió tras `LV-111`
(`docs/dev/analisis-alertas-2026-08-14.md`), y los dos son de la misma familia:
la pantalla donde se trabaja a diario mostrando cosas que no ayudan.

`LV-113` es el que importa: `generate_alerts` sólo excluía los estados
terminales en las reglas que vigilan `status`. Las reglas de **fecha** —seguros,
credenciales, habilitaciones, o sea casi todas las reales— no excluían nada, así
que una aeronave dada de baja con el seguro vencido sostenía su alerta para
siempre. `LV-90` ya había documentado y corregido este defecto **en la otra
mitad** del motor.

`LV-112` es el orden: sin `ordering` declarado, la lista salía como quisiera la
base. Además del triage al azar, un `LIMIT/OFFSET` sin `ORDER BY` puede repetir
o saltarse filas entre páginas.
"""

from datetime import timedelta

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.utils import timezone

from apps.compliance.models import Alert, AlertRule
from apps.registry.models import Aircraft, CostCenter, Operator

TODAY = timezone.localdate()
LAPSED = TODAY - timedelta(days=60)


@pytest.fixture
def insurance_rule(db):
    return AlertRule.objects.create(
        name="Seguros JAC por vencer",
        entity_type="registry.aircraft",
        field_to_watch="insurance_expiry",
        days_before_expiry=30,
    )


def _aircraft(registration, status):
    return Aircraft.objects.create(
        registration=registration,
        type="RPA",
        model="M300",
        manufacturer="DJI",
        status=status,
        insurance_expiry=LAPSED,
    )


@pytest.mark.django_db
class TestRetiredRecordsStopAlerting:
    def test_a_retired_aircraft_raises_no_insurance_alert(self, insurance_rule):
        """El caso del análisis: nadie puede actuar sobre el seguro de una
        aeronave que ya no está en la flota."""
        _aircraft("RPA-BAJA", "retired")

        call_command("generate_alerts")

        assert Alert.objects.count() == 0

    def test_an_active_one_still_does(self, insurance_rule):
        """La otra mitad, sin la cual esto sería un silenciador y no un filtro."""
        _aircraft("RPA-VIVA", "active")

        call_command("generate_alerts")

        assert Alert.objects.count() == 1

    def test_a_model_without_terminal_statuses_is_not_filtered(self, db):
        """`Operator` no declara estados terminales, así que la exclusión no
        debe inventarse una: filtrar por un campo que el modelo no tiene sería
        romper las reglas de credenciales, que son de las más usadas."""
        cost_center = CostCenter.objects.create(code="OPS", name="Operations")
        Operator.objects.create(
            employee_id="P1",
            full_name="Pilot One",
            cost_center=cost_center,
            credential_expiry=LAPSED,
        )
        AlertRule.objects.create(
            name="Credenciales DGAC por vencer",
            entity_type="registry.operator",
            field_to_watch="credential_expiry",
            days_before_expiry=30,
        )

        call_command("generate_alerts")

        assert Alert.objects.count() == 1


@pytest.mark.django_db
class TestTheInboxHasAnOrder:
    def _alerts(self, rule, count):
        content_type = ContentType.objects.get_for_model(Aircraft)
        for index in range(count):
            aircraft = _aircraft(f"RPA-{index}", "active")
            Alert.objects.create(
                alert_rule=rule,
                content_type=content_type,
                object_id=aircraft.pk,
                message=f"alerta {index}",
            )

    def test_open_alerts_come_before_resolved_ones(self, insurance_rule):
        self._alerts(insurance_rule, 3)
        first = Alert.objects.first()
        first.resolve(reason="ya gestionado")

        listed = list(Alert.objects.all())

        assert listed[-1].pk == first.pk
        assert [alert.is_resolved for alert in listed] == [False, False, True]

    def test_the_order_is_declared_so_pagination_is_stable(self):
        """Sin `ordering`, `LIMIT/OFFSET` puede repetir o saltarse filas entre
        páginas -- y eso no se ve mirando la primera."""
        assert Alert._meta.ordering == ["is_resolved", "triggered_at"]
