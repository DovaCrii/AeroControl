"""LV-229: los equipos de una faena que no vuela no cuentan como brecha.

Encontrado midiendo `LV-74` en producción: `RPA-2019` figuraba entre las aeronaves
"sin vigencia de seguro JAC", y está en `CC110` — uno de los centros
administrativos que `LV-205` distinguió a pedido del usuario, textual: *"el CC110
de casa matriz o 410, por ejemplo, estamos a cargo más de los equipos que
volar"*. Confirmado con él: ese equipo está en bodega y no opera, así que **no es
una brecha de seguro**.

**Lo que estaba mal no era el dato, era el indicador.** `permit_status_by_cost_center`
(`LV-206`) ya excluía los centros que no vuelan, y este contador no: dos
indicadores del mismo panel respondían distinto a la misma pregunta sobre la misma
faena, y el de seguros bajaba por una decisión correcta.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.registry.models import Aircraft, CostCenter


def _aircraft(registration, cost_center, **extra):
    return Aircraft.objects.create(
        registration=registration,
        type="Multirotor",
        model="M3E",
        manufacturer="DJI",
        cost_center=cost_center,
        **extra,
    )


def _by_key(figures):
    """Las tarjetas por su clave estable y no por su posición ni su etiqueta.

    `LV-129` puso `key` justamente para esto: la etiqueta es traducible, así que
    un test que la compare pasa o falla según el idioma activo — la trampa que
    `LV-95` dejó documentada y que este archivo no va a volver a pagar.
    """
    return {card["key"]: card for card in figures["readiness"]}


@pytest.fixture
def today():
    return timezone.localdate()


class TestTheFleetFigureExcludesNonFlyingCostCentres:
    @pytest.mark.django_db
    def test_a_stored_aircraft_without_insurance_is_not_a_gap(self, today):
        """El caso real: `RPA-2019` en `CC110`, en bodega y sin seguro."""
        from apps.dashboard.views import panel_readiness

        warehouse = CostCenter.objects.create(
            code="CC110", name="Casa matriz", operates_flights=False
        )
        _aircraft("RPA-2019", warehouse)

        figures = _by_key(panel_readiness(today))

        assert figures["fleet"]["total"] == 0

    @pytest.mark.django_db
    def test_an_aircraft_of_a_flying_cost_centre_still_counts(self, today):
        from apps.dashboard.views import panel_readiness

        site = CostCenter.objects.create(
            code="CC738", name="MLP", operates_flights=True
        )
        _aircraft("RPA-7126", site)

        figures = _by_key(panel_readiness(today))

        assert figures["fleet"]["total"] == 1

    @pytest.mark.django_db
    def test_an_aircraft_with_no_cost_centre_still_counts(self, today):
        """**Sin faena no es lo mismo que no vuela**, y la diferencia importa.

        Una aeronave sin faena es una aeronave cuya pertenencia falta, y eso sí es
        una brecha que hay que ver. Excluirla junto a las de bodega escondería un
        hueco real detrás de una regla escrita para otro caso.
        """
        from apps.dashboard.views import panel_readiness

        _aircraft("RPA-9999", None)

        figures = _by_key(panel_readiness(today))

        assert figures["fleet"]["total"] == 1

    @pytest.mark.django_db
    def test_the_insured_count_matches_the_same_scope(self, today):
        """El numerador y el denominador tienen que mirar la misma flota.

        Si la exclusión se aplicara sólo al total, el porcentaje diría que hay más
        asegurados que aeronaves.
        """
        from apps.dashboard.views import panel_readiness

        warehouse = CostCenter.objects.create(
            code="CC110", name="Casa matriz", operates_flights=False
        )
        site = CostCenter.objects.create(
            code="CC738", name="MLP", operates_flights=True
        )
        # La de bodega, asegurada: no debe sumar ni al total ni al numerador.
        _aircraft(
            "RPA-2019",
            warehouse,
            insurance_status=Aircraft.INSURANCE_STATUS_ACTIVE,
            insurance_expiry=today + timedelta(days=90),
        )
        _aircraft(
            "RPA-7126",
            site,
            insurance_status=Aircraft.INSURANCE_STATUS_ACTIVE,
            insurance_expiry=today + timedelta(days=90),
        )

        figures = _by_key(panel_readiness(today))

        assert figures["fleet"]["total"] == 1
        assert figures["insurance"]["count"] == 1


class TestTheTwoPanelIndicatorsNowAgree:
    @pytest.mark.django_db
    def test_permits_and_fleet_apply_the_same_rule(self, today):
        """`LV-206` ya excluía los centros que no vuelan; esto lo alinea.

        Dos indicadores del mismo panel que responden distinto sobre la misma
        faena es lo que hace que nadie confíe en ninguno de los dos.
        """
        from apps.compliance.kpis import permit_status_by_cost_center
        from apps.dashboard.views import panel_readiness

        warehouse = CostCenter.objects.create(
            code="CC110", name="Casa matriz", operates_flights=False
        )
        _aircraft("RPA-2019", warehouse)
        # **Una faena que sí vuela, para que la comprobación de abajo ejercite
        # algo.** La primera versión de este test sólo creaba la de bodega, así
        # que `permit_status_by_cost_center` devolvía una lista vacía y la
        # comprensión no evaluaba su cuerpo: el test pasaba sin comprobar nada, y
        # de hecho pasaba con la clave equivocada (`row["code"]`, cuando la fila
        # trae el objeto `cost_center`). Encontrado al escribir el colector del
        # informe, que sí lee esas filas de verdad.
        site = CostCenter.objects.create(
            code="CC738", name="MLP", operates_flights=True
        )
        _aircraft("RPA-7126", site)

        rows = permit_status_by_cost_center(today)
        figures = _by_key(panel_readiness(today))

        codes = [row["cost_center"].code for row in rows]
        # La faena que vuela está y la de bodega no, en los dos indicadores.
        assert codes == ["CC738"]
        assert figures["fleet"]["total"] == 1
