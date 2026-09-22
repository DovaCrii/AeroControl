"""LV-237: el panel tiene un techo de consultas, y alguien lo vigila.

**Por qué existe este archivo.** El panel es la primera pantalla de cada inicio de
sesión y la única que todos abren todos los días, así que es donde una consulta de
más se paga más veces. Había techos sobre funciones sueltas —`document_subjects`,
`permit_status_by_cost_center`, `cost_centers_for_refs`— y **ninguno sobre la vista
entera**, que es justo donde se acumula lo que nadie mira.

Eso no es teórico: `LV-216` retiró la tarjeta del clima de la plantilla a pedido del
usuario (*"no es necesario que muestre el clima"*) y la vista **siguió calculándola un
mes entero** —candidatos de permisos, sitios con coordenadas, el plan geo ligado y una
posible salida a Open-Meteo— para un contexto que ninguna plantilla leía. Un techo
sobre la vista lo habría delatado el mismo día.

⚠️ **El número no se adivina, se mide.** Si un cambio legítimo lo sube, se sube acá a
propósito y se dice por qué en el commit; lo que este test impide es que suba **sin
que nadie se entere**, que es la única forma en que llegó a donde estaba.
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.operations.models import FlightPermission
from apps.registry.models import Aircraft, CostCenter, Operator

# Medido, no elegido. Ver el aviso del encabezado antes de tocarlo.
#
# Medición del 2026-09-21 sobre la operación del fixture, con el proceso caliente:
# **58 antes de `LV-237` y 48 después**. Las diez que se fueron son el clima que ya no
# se calcula, la segunda vuelta de `permit_counts` y las dos agregaciones de los
# gráficos que `LV-89` había retirado de la pantalla.
PANEL_QUERY_BUDGET = 48
# Elegir una faena cuesta exactamente **una** consulta más —el `SELECT` de esa faena—
# y cambia los `WHERE` del resto sin agregar recorridos. Se mide aparte igualmente:
# que hoy sea "una más" es justo lo que un techo propio mantiene verdadero. Antes de
# `LV-237` eran 59.
PANEL_FILTERED_QUERY_BUDGET = 49


@pytest.fixture
def auth_client(db):
    user = User.objects.create_user("budget-user", password="pw")
    client = Client()
    assert client.login(username=user.username, password="pw")
    return client


@pytest.fixture
def operation(db):
    """Una operación pequeña pero **completa**: el techo tiene que medirse sobre un
    panel que dibuja todas sus secciones, no sobre una base vacía donde la mitad de
    los bloques se saltan por un `{% if %}`."""
    today = timezone.localdate()
    soon = today + timedelta(days=10)
    centre = CostCenter.objects.create(code="CC738", name="Faena")
    other = CostCenter.objects.create(code="CC861", name="Otra")
    for index, cc in enumerate((centre, other)):
        aircraft = Aircraft.objects.create(
            registration=f"RPA-{index}000",
            type="RPA",
            model="M3",
            manufacturer="DJI",
            cost_center=cc,
            status="active",
            insurance_expiry=soon,
        )
        operator = Operator.objects.create(
            employee_id=f"E{index}",
            full_name=f"Piloto {index}",
            cost_center=cc,
            credential_expiry=soon,
        )
        permit = FlightPermission.objects.create(
            cost_center=cc,
            purpose="Survey",
            location="Sector",
            valid_from=today,
            valid_until=soon,
        )
        permit.operators.add(operator)
        permit.aircraft_fleet.add(aircraft)
    return centre


def _warm(client, **params):
    """Una carga de calentamiento, para que la que se mida sea la siguiente.

    ⚠️ **Sin esto el número no es del panel sino del orden de la suite.** Django
    cachea `ContentType.objects.get_for_model` por proceso, así que la primera carga
    paga las consultas de `django_content_type` y las siguientes no: el mismo test
    daba 57 aislado y 49 dentro de la suite completa, midiendo exactamente lo mismo.
    Lo que interesa es el proceso ya caliente, que es como corre en producción — un
    servidor que lleva días arriba no vuelve a pedir esa tabla.
    """
    client.get(reverse("dashboard"), params)


@pytest.mark.django_db
def test_the_panel_stays_within_its_query_budget(
    auth_client, operation, django_assert_num_queries
):
    _warm(auth_client)

    with django_assert_num_queries(PANEL_QUERY_BUDGET):
        response = auth_client.get(reverse("dashboard"))

    assert response.status_code == 200


@pytest.mark.django_db
def test_choosing_a_cost_centre_does_not_change_the_shape(
    auth_client, operation, django_assert_num_queries
):
    _warm(auth_client, cost_center=operation.pk)

    with django_assert_num_queries(PANEL_FILTERED_QUERY_BUDGET):
        response = auth_client.get(reverse("dashboard"), {"cost_center": operation.pk})

    assert response.status_code == 200
    assert response.context["selected_cost_center"] == operation


@pytest.mark.django_db
def test_the_panel_no_longer_computes_the_weather(auth_client, operation):
    """`LV-216` borró la tarjeta de la plantilla; la vista siguió calculándola.

    Se afirma sobre el **contexto** y no sobre el HTML a propósito: que la tarjeta no
    se dibuje ya lo cubre `test_lv148_panel_order.py`, y era cierto todo el mes en que
    el cálculo siguió corriendo. Lo que esta fila retira es el trabajo, y el trabajo
    sólo se ve acá.
    """
    response = auth_client.get(reverse("dashboard"))

    assert not [key for key in response.context.keys() if key.startswith("weather")]


@pytest.mark.django_db
def test_the_budget_does_not_grow_with_the_operation(
    auth_client, operation, django_assert_num_queries
):
    """⚠️ **La mitad que de verdad importa.** Un techo fijo sobre una operación fija
    sólo prueba que hoy son N; lo que hunde esta pantalla es una consulta **por fila**,
    y eso no se ve hasta que la base crece. Acá la operación se multiplica y el número
    tiene que quedarse donde estaba.
    """
    today = timezone.localdate()
    soon = today + timedelta(days=10)
    for index in range(2, 12):
        cc = CostCenter.objects.create(code=f"CC{index:03d}", name=f"Faena {index}")
        aircraft = Aircraft.objects.create(
            registration=f"RPA-{index}500",
            type="RPA",
            model="M3",
            manufacturer="DJI",
            cost_center=cc,
            status="active",
            insurance_expiry=soon,
        )
        operator = Operator.objects.create(
            employee_id=f"E{index}00",
            full_name=f"Piloto {index}",
            cost_center=cc,
            credential_expiry=soon,
        )
        permit = FlightPermission.objects.create(
            cost_center=cc,
            purpose="Survey",
            location="Sector",
            valid_from=today,
            valid_until=soon,
        )
        permit.operators.add(operator)
        permit.aircraft_fleet.add(aircraft)

    _warm(auth_client)

    with django_assert_num_queries(PANEL_QUERY_BUDGET):
        auth_client.get(reverse("dashboard"))
