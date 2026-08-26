"""LV-148: el panel se ordena por la pregunta que responde cada tramo.

Cierra lo que `LV-31` dejó abierto (reorden del panel, contraste de chips,
paleta de badges), a pedido del usuario: *"ver una opción además de lo dicho de
mejorar el dashboard general"*.

Tres cosas, y las tres eran defectos:

1. La grilla de tarjetas estaba **arriba** de la tira de "¿podemos operar hoy?" y
   mezclaba inventario, trabajo pendiente y cierre de período como si fueran lo
   mismo — con las dos que nunca cambian en las dos posiciones más leídas.
2. "Aeronaves activas" y "Operadores activos" eran el **denominador** de la tira
   de abajo dicho dos veces.
3. El mismo tramo de urgencia se pintaba distinto en dos pantallas, y no sólo
   distinto: `due_30` era ámbar en el panel y azul en la bandeja.

El orden se afirma por **posición en el HTML**, que es lo único que un test puede
ver de un reorden.
"""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.compliance.digest import BUCKET_BADGE_CSS, BUCKET_TEXT_CSS, BUCKETS
from apps.core.testing import login_as
from apps.registry.models import Aircraft, CostCenter

TODAY = timezone.localdate()


def _aircraft(**kwargs):
    return Aircraft.objects.create(
        registration=kwargs.pop("registration", "RPA-4025"),
        type="Multirotor",
        model="M4E",
        manufacturer="DJI",
        **kwargs,
    )


def _located_permission():
    """Un permiso con coordenadas: es lo que hace existir la tarjeta del clima."""
    from apps.operations.models import FlightPermission

    return FlightPermission.objects.create(
        cost_center=CostCenter.objects.create(code="CC738", name="MLP"),
        purpose="photogrammetry",
        area_type="unpopulated",
        status="approved",
        valid_from=TODAY,
        valid_until=TODAY + timedelta(days=30),
        location="Salamanca",
        latitude=-31.9,
        longitude=-70.7,
    )


def _panel(**params):
    return (
        login_as(
            "view_aircraft", "view_costcenter", "view_alert", "view_flightpermission"
        )
        .get(reverse("dashboard"), params)
        .content.decode()
    )


@pytest.mark.django_db
class TestTheOrderOfTheSections:
    def test_readiness_comes_before_the_work_row(self):
        _aircraft()

        content = _panel()

        assert content.index("readiness-strip") < content.index("kpi-grid")

    def test_the_expiry_list_comes_before_the_weather_card(self):
        # LV-D5 lo pedía ("lo accionable primero") y el clima seguía arriba. El
        # permiso con coordenadas es lo que hace que la tarjeta exista: con la
        # función apagada se dibuja igual, diciendo que el pronóstico no está.
        _aircraft(insurance_expiry=TODAY)
        _located_permission()

        content = _panel()

        assert content.index("upcoming-expirations") < content.index(
            "panel-weather-title"
        )

    def test_the_work_row_comes_before_the_weather_card(self):
        _aircraft(insurance_expiry=TODAY)
        _located_permission()

        content = _panel()

        assert content.index("kpi-grid") < content.index("panel-weather-title")


@pytest.mark.django_db
class TestTheInventoryCardsAreGone:
    def test_the_active_aircraft_card_is_gone(self):
        _aircraft()

        content = _panel()

        assert "Aeronaves activas" not in content

    def test_the_active_operators_card_is_gone(self):
        _aircraft()

        content = _panel()

        assert "Operadores activos" not in content

    def test_the_registry_is_still_reachable_from_the_readiness_strip(self):
        # Lo que se retira son dos números repetidos, no la navegación: las
        # tarjetas de flota y credenciales llevan a los mismos listados.
        _aircraft()

        content = _panel()

        assert reverse("aircraft-list") in content
        assert reverse("operator-list") in content

    def test_the_alert_card_shows_even_at_zero(self):
        # Excepción declarada a la regla de ocultar en cero: la tarjeta
        # representa la bandeja, y un 0 ahí es información.
        _aircraft()

        content = _panel()

        assert reverse("alert-list") in content


class TestOneScaleTwoRepresentations:
    def test_both_tables_cover_every_bucket_the_digest_declares(self):
        # El guardián anti-deriva: si mañana el digest gana un tramo, alguien
        # tiene que decidir sus dos colores, y este test lo obliga.
        declared = {key for key, _bound in BUCKETS} | {"later"}

        assert set(BUCKET_BADGE_CSS) == declared
        assert set(BUCKET_TEXT_CSS) == declared

    def test_the_scale_no_longer_disagrees_with_itself(self):
        # `due_30` era `bg-info-subtle` en la bandeja y ámbar en el panel. Ahora
        # las dos representaciones del mismo tramo salen de la misma familia.
        assert "info" in BUCKET_BADGE_CSS["due_30"]
        assert "info" in BUCKET_TEXT_CSS["due_30"]


@pytest.mark.django_db
class TestTheRowTakesItsColourFromTheScale:
    def test_an_overdue_row_carries_the_shared_tone(self):
        from apps.dashboard.views import upcoming_expirations

        _aircraft(insurance_expiry=TODAY - timedelta(days=5))

        items = upcoming_expirations(TODAY, TODAY + timedelta(days=30))

        assert items[0]["tone"] == BUCKET_TEXT_CSS["overdue"]

    def test_the_template_no_longer_hard_codes_the_palette(self):
        _aircraft(insurance_expiry=TODAY - timedelta(days=5))

        content = _panel()

        assert BUCKET_TEXT_CSS["overdue"] in content
        # La cadena de `if`s con su propia paleta se fue: lo que queda es el tono
        # que viene del contexto.
        assert "text-warning-emphasis fw-semibold" not in content
