"""LV-111: lo resuelto no vuelve, salvo que sea un caso nuevo de verdad.

Reportado por el usuario con captura: la credencial de un operador aparecía dos
veces en la bandeja —una resuelta el 2026-08-03 y otra abierta el 2026-08-15—
por la misma regla y la misma fecha vencida. Igual con `RPA-5532`.

Causa: `generate_alerts` evitaba duplicados mirando **sólo las alertas
abiertas**, así que resolver una la hacía volver esa misma noche, porque el dato
seguía vencido. Una bandeja donde lo resuelto reaparece enseña a no resolver, y
con ella se pierde la evidencia ISO 10.2 que el modal de resolver recoge.

La condición que el usuario puso, y que estos tests fijan, tiene **dos mitades**
y ninguna sirve sola: lo resuelto no vuelve **a menos que** sea un caso nuevo,
por ejemplo tras una renovación. Suprimir siempre sería peor que el defecto:
escondería el vencimiento siguiente.
"""

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.compliance.models import Alert, AlertRule
from apps.registry.models import CostCenter, Operator

TODAY = timezone.localdate()


@pytest.fixture
def rule(db):
    return AlertRule.objects.create(
        name="Credenciales DGAC por vencer",
        entity_type="registry.operator",
        field_to_watch="credential_expiry",
        days_before_expiry=30,
    )


@pytest.fixture
def operator(db):
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    return Operator.objects.create(
        employee_id="P1",
        full_name="Carlos Peñailillo Latorre",
        cost_center=cost_center,
        credential_expiry=TODAY - timedelta(days=90),
    )


@pytest.mark.django_db
def test_a_resolved_alert_does_not_come_back_on_the_next_run(rule, operator):
    """El caso exacto de la captura."""
    call_command("generate_alerts")
    alert = Alert.objects.get()
    alert.resolve(reason="Fuera de CC con operación RPA")

    call_command("generate_alerts")

    assert Alert.objects.count() == 1


@pytest.mark.django_db
def test_nor_on_many_later_runs(rule, operator):
    """El trabajo corre todos los días: una supresión que dure una noche no es
    una supresión."""
    call_command("generate_alerts")
    Alert.objects.get().resolve(reason="Ya gestionado")

    for _ in range(5):
        call_command("generate_alerts")

    assert Alert.objects.count() == 1


@pytest.mark.django_db
def test_a_renewal_does_raise_a_new_alert(rule, operator):
    """La otra mitad, y la que impide que el arreglo tape vencimientos: con una
    credencial renovada, el próximo vencimiento es un caso **nuevo**."""
    call_command("generate_alerts")
    Alert.objects.get().resolve(reason="Credencial renovada")
    operator.credential_expiry = TODAY + timedelta(days=10)
    operator.save(update_fields=["credential_expiry"])

    call_command("generate_alerts")

    assert Alert.objects.count() == 2
    assert Alert.objects.filter(is_resolved=False).count() == 1


@pytest.mark.django_db
def test_an_open_alert_still_dedupes(rule, operator):
    """No se rompe lo que ya funcionaba: sin resolver nada, la corrida diaria
    sigue sin acumular copias."""
    call_command("generate_alerts")
    call_command("generate_alerts")

    assert Alert.objects.count() == 1


@pytest.mark.django_db
def test_the_alert_records_the_value_it_was_about(rule, operator):
    """Lo que hace posible todo lo anterior: el valor queda congelado, porque
    leerlo después devolvería el del registro *hoy*, no el que la disparó."""
    call_command("generate_alerts")

    assert Alert.objects.get().watched_value == operator.credential_expiry.isoformat()


@pytest.mark.django_db
def test_reopening_an_alert_does_not_create_a_second_one(rule, operator):
    """ "Deshacer" existe para cuando alguien resolvió por error; la corrida
    siguiente no debe agregar una copia encima de la reabierta."""
    call_command("generate_alerts")
    alert = Alert.objects.get()
    alert.resolve(reason="Error")
    alert.is_resolved = False
    alert.resolved_at = None
    alert.save(update_fields=["is_resolved", "resolved_at"])

    call_command("generate_alerts")

    assert Alert.objects.count() == 1
