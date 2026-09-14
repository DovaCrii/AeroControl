"""Una faena con contrato cerrado sale del indicador de cumplimiento.

Pedido del usuario el 2026-09-14, mirando el panel: *"cuando el centro de costo
cierra no es necesario que lo muestre el panel"* — siete faenas cerradas ocupando
la tabla con «Ninguno».

⚠️ **Y no era sólo ruido de pantalla.** Esas filas son el universo del indicador
que va **firmado a la DGAC**: `cost_centres_with_operation` es su denominador y
`cost_centres_without_permit` su numerador. Una faena cerrada no tiene permisos
vigentes —obviamente, ya no opera— así que cada una empeoraba una cifra de
cumplimiento por una operación terminada. El síntoma estaba en el panel; el daño,
en el papel.

Es el mismo razonamiento que el comentario de `operates_flights` ya tenía
escrito para `CC110` y `CC410`: *"listada como sin permisos vigentes, queda
declarada incumplida por una operación que no le toca"*. Una faena cerrada está
en esa misma situación.

**La regla es la del usuario y no admite excepción**: *"independiente que tenga
permiso o no, si está cerrado no cuenta"*.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.compliance.kpis import permit_status_by_cost_center
from apps.operations.models import FlightPermission
from apps.registry.models import CostCenter

TODAY = timezone.localdate()


def _centre(code, **kwargs):
    kwargs.setdefault("operates_flights", True)
    return CostCenter.objects.create(code=code, name=code, **kwargs)


def _permit(centre, status=FlightPermission.STATUS_APPROVED, days=90):
    return FlightPermission.objects.create(
        cost_center=centre,
        purpose="photogrammetry",
        status=status,
        location="Sector 1",
        area_type="unpopulated",
        valid_from=TODAY - timedelta(days=10),
        valid_until=TODAY + timedelta(days=days),
    )


def _codes(rows):
    return {row["cost_center"].code for row in rows}


class TestAClosedContractLeavesTheTable:
    @pytest.mark.django_db
    def test_a_closed_cost_centre_is_not_listed(self, db):
        _centre("CC001")
        _centre("CC002", contract_status=CostCenter.CONTRACT_CLOSED)

        assert _codes(permit_status_by_cost_center(TODAY)) == {"CC001"}

    @pytest.mark.django_db
    def test_even_when_it_still_holds_a_live_permit(self, db):
        """⚠️ La regla del usuario, sin excepción: *"independiente que tenga
        permiso o no, si está cerrado no cuenta"*.

        Se propuso dejar visible este caso —un permiso DGAC vigente sobre un
        contrato terminado es una contradicción que alguien debería cerrar— y se
        descartó. Lo que se pierde queda dicho: ese permiso ya no aparece en esta
        tabla, aunque sigue en la lista de permisos y en los vencimientos.
        """
        closed = _centre("CC002", contract_status=CostCenter.CONTRACT_CLOSED)
        _permit(closed)

        assert _codes(permit_status_by_cost_center(TODAY)) == set()

    @pytest.mark.django_db
    def test_and_when_it_has_one_awaiting_the_dgac(self, db):
        closed = _centre("CC002", contract_status=CostCenter.CONTRACT_CLOSED)
        _permit(closed, status=FlightPermission.STATUS_REQUESTED)

        assert _codes(permit_status_by_cost_center(TODAY)) == set()

    @pytest.mark.django_db
    def test_an_empty_contract_status_still_counts(self, db):
        """`blank=True` en el campo: cerrar un contrato es un acto ocasional, así
        que hay fichas viejas con el valor vacío. Vacío **no** es cerrado — leerlo
        así sacaría del indicador a media flota de un plumazo."""
        _centre("CC001", contract_status="")

        assert _codes(permit_status_by_cost_center(TODAY)) == {"CC001"}

    @pytest.mark.django_db
    def test_the_other_two_filters_still_apply(self, db):
        """Cerrar no reemplaza a los criterios que ya estaban: la faena que no
        vuela y la archivada siguen fuera por sus propias razones."""
        _centre("CC110", operates_flights=False)
        _centre("CC003", is_active=False)
        _centre("CC001")

        assert _codes(permit_status_by_cost_center(TODAY)) == {"CC001"}


class TestTheReportStopsAccusingAClosedSite:
    """La mitad que no se ve en el panel y sí en el papel firmado."""

    @pytest.mark.django_db
    def test_a_closed_site_is_out_of_both_halves_of_the_indicator(self, db):
        from apps.reporting.builder import build

        _centre("CC001")
        _centre("CC002", contract_status=CostCenter.CONTRACT_CLOSED)

        payload, _missing = build(TODAY.replace(day=1), cutoff=TODAY)
        kpis = payload["kpis"]

        # El denominador: una faena con operación, no dos.
        assert kpis["cost_centres_with_operation"]["value"] == 1
        # Y el numerador: la cerrada no se cuenta como incumplida.
        assert kpis["cost_centres_without_permit"]["value"] == 1

    @pytest.mark.django_db
    def test_the_denominator_can_no_longer_drift_from_the_rows(self, db):
        """⚠️ Era una consulta aparte que **debía** devolver el mismo universo que
        la tabla, con el docstring advirtiéndolo: *"dos recorridos separados es
        cómo el informe empieza a decir 7 de 12 en una página y 7 de 11 en la
        siguiente"*. El 2026-09-14 se separaron de verdad — la tabla dejó fuera
        las cerradas y la consulta las seguía contando.

        Ahora el denominador **son** las filas, así que no hay dos criterios que
        mantener sincronizados.
        """
        from apps.reporting.builder import build

        for index in range(3):
            _centre(f"CC10{index}")
        _centre("CC900", contract_status=CostCenter.CONTRACT_CLOSED)

        payload, _missing = build(TODAY.replace(day=1), cutoff=TODAY)

        assert payload["kpis"]["cost_centres_with_operation"]["value"] == len(
            payload["cost_centres"]
        )


class TestTheCodeUsesTheConstantAndNotALiteral:
    def test_the_filter_reads_the_model_constant(self):
        """`contract_status` pasó de ser un dato de la ficha a decidir quién entra
        en el indicador. Un `"closed"` tecleado mal en ese filtro no falla: deja
        de excluir, y nadie se entera."""
        from pathlib import Path

        from django.conf import settings

        source = (
            Path(settings.BASE_DIR) / "apps" / "compliance" / "kpis.py"
        ).read_text(encoding="utf-8")

        assert "CostCenter.CONTRACT_CLOSED" in source
        assert 'contract_status="closed"' not in source
