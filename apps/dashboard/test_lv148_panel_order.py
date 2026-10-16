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
    """Un permiso con coordenadas, que es lo que hacía aparecer la tarjeta del clima.

    `LV-237` retiró también el cálculo, así que hoy esto es justamente lo contrario:
    el caso que **habría** dibujado la tarjeta, para que el test de abajo afirme el
    retiro sobre los datos que lo harían fallar si volviera.
    """
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
    def test_attention_comes_before_readiness_and_expirations(self):
        """**LV-310 reescribe el orden de esta fila.** Antes: indicadores, rejilla de
        seis tarjetas de trabajo, vencimientos. Ahora la rejilla se fue y su lugar lo
        toma «Requiere atención», que va **primero**: lo que alguien tiene que hacer
        hoy se lee antes que «¿podemos operar?». La pregunta del test es la misma
        —qué tramo responde qué— y la respuesta cambió a propósito."""
        _aircraft()

        content = _panel()

        assert (
            content.index('id="panel-attention"')
            < content.index("readiness-strip")
            < content.index('id="upcoming-expirations"')
        )
        assert "kpi-grid" not in content

    def test_lv216_the_weather_card_is_no_longer_on_the_panel(self):
        """**Estos dos tests se funden en uno con `LV-216`.** Afirmaban que la
        lista de vencimientos y la fila de trabajo iban **antes** que la tarjeta
        del clima — lo que `LV-D5` pedía ("lo accionable primero") y que el clima
        no cumplía.

        El usuario retiró la tarjeta del panel, así que ya no hay nada después de
        lo que ponerse: la pregunta que estos tests hacían dejó de existir. Lo que
        queda por afirmar es el retiro, y que lo accionable sigue estando.
        """
        _aircraft(insurance_expiry=TODAY)
        _located_permission()

        content = _panel()

        assert "panel-weather-title" not in content
        assert "upcoming-expirations" in content
        # LV-310: lo accionable es «Requiere atención», y va antes de los vencimientos.
        assert 'id="panel-attention"' in content
        assert content.index('id="panel-attention"') < content.index(
            'id="upcoming-expirations"'
        )


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

    def test_the_alert_card_is_gone_but_the_tray_is_still_reachable(self):
        # LV-310: la tarjeta «Alertas pendientes» salió con la rejilla (la bandeja
        # tiene su contador en el menú y el enlace en la sección de vencimientos).
        # Se afirma sobre la **región de contenido**, no la página entera: el menú
        # lateral enlaza a la bandeja siempre y haría pasar el test aunque el
        # panel no llevara a ella.
        _aircraft(insurance_expiry=TODAY - timedelta(days=5))

        content = _panel()
        body = content.split('id="panel-attention"')[-1]

        assert "Alertas pendientes" not in body
        assert reverse("alert-list") in body


class TestOneScaleTwoRepresentations:
    def test_both_tables_cover_every_bucket_the_digest_declares(self):
        # El guardián anti-deriva: si mañana el digest gana un tramo, alguien
        # tiene que decidir sus dos colores, y este test lo obliga.
        declared = {key for key, _bound in BUCKETS} | {"later"}

        assert set(BUCKET_BADGE_CSS) == declared
        assert set(BUCKET_TEXT_CSS) == declared

    def test_the_scale_no_longer_disagrees_with_itself(self):
        """El defecto original: `due_30` era azul en la bandeja y ámbar en el panel.

        **UX-01 permite comprobarlo mejor de lo que se podía antes.** Este test
        preguntaba `"info" in ...` en las dos tablas — o sea, se apoyaba en que
        las dos usaran el nombre de la misma utilidad de Bootstrap, que es una
        coincidencia de nomenclatura y no una garantía. Con los tokens de
        severidad, cada tramo declara su **nivel**, así que se puede exigir lo que
        de verdad importa: que los cinco tramos coincidan de nivel en las dos
        representaciones, no sólo el que se rompió una vez.
        """
        de_pastilla = {
            bucket: css.removeprefix("sev-") for bucket, css in BUCKET_BADGE_CSS.items()
        }
        de_texto = {
            bucket: css.removeprefix("sev-text-")
            for bucket, css in BUCKET_TEXT_CSS.items()
        }

        assert de_pastilla == de_texto


@pytest.mark.django_db
class TestTheRowTakesItsColourFromTheScale:
    def test_an_overdue_row_carries_the_shared_tone(self):
        from apps.compliance.expirations import upcoming_expirations

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
