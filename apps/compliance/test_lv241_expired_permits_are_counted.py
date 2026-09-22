"""LV-241: lo vencido se contaba mal, y por eso el panel se veía limpio.

Pedido del usuario el 2026-09-22, con captura del panel: *"el dashboard debe
contabilizar y marcar y dar el seguimiento completo sobre todo lo que hoy está
vencido, por lo cual no debe marcar vigente, indicar vencimiento claro en lo que se
lleva al mes"*.

En su pantalla, `CC684` tenía **dos documentos atrasados** en la lista de
vencimientos y su fila de la tabla de permisos estaba **entera en guiones**,
incluida la columna «Vigencia pasada».

⚠️ **Y la causa no era un rótulo: el vencido no se podía contar.** La columna miraba
los permisos **aprobados** con fecha pasada, y `expire_permissions` (`LV-83`) los
mueve a `expired` cada noche — o sea que el permiso vencido **salía del conjunto
antes de que nadie lo viera**. El docstring de `permit_counts` lo tenía escrito sin
sacar la conclusión: *"`lapsed` normalmente vale cero porque `expire_permissions`
los cierra cada noche"*. Un contador que en régimen normal vale cero no está
midiendo el vencimiento: está midiendo si corrió el cron.

Las dos decisiones son del usuario, preguntadas antes de tocar:

* **La ventana es el mes en curso.** Es el período en que esto se rinde, y un
  permiso renovado en julio deja de pesar en septiembre.
* 🔶 **El porcentaje no baja.** `total` sigue siendo los permisos vivos, así que la
  cifra que va firmada a la DGAC mide lo mismo que ayer y los informes emitidos no
  se mueven. Lo vencido se ve **al lado**, no dentro.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.compliance.kpis import permit_counts, permit_status_by_cost_center
from apps.operations.models import FlightPermission
from apps.registry.models import CostCenter

TODAY = timezone.localdate()
MONTH_START = TODAY.replace(day=1)


@pytest.fixture
def centre(db):
    return CostCenter.objects.create(code="CC684", name="Faena", operates_flights=True)


def _permit(centre, status, valid_from, valid_until):
    return FlightPermission.objects.create(
        cost_center=centre,
        purpose="photogrammetry",
        status=status,
        location="Sector",
        area_type="unpopulated",
        valid_from=valid_from,
        valid_until=valid_until,
    )


def _row(centre):
    return next(
        row
        for row in permit_status_by_cost_center(TODAY)
        if row["cost_center"].pk == centre.pk
    )


class TestTheExpiredPermitStopsBeingInvisible:
    @pytest.mark.django_db
    def test_a_permit_that_expired_this_month_is_counted(self, centre):
        """El caso del usuario: el trabajo nocturno ya lo cerró, y aun así tiene que
        verse. Antes de esta fila el estado `expired` no entraba en ningún conteo."""
        _permit(
            centre,
            FlightPermission.STATUS_EXPIRED,
            MONTH_START - timedelta(days=60),
            TODAY - timedelta(days=4),
        )

        assert permit_counts(TODAY, centre)["expired_this_month"] == 1

    @pytest.mark.django_db
    def test_its_cost_centre_no_longer_shows_a_row_of_dashes(self, centre):
        """⚠️ **La mitad que se ve.** La faena cuyo único permiso caducó
        desaparecía del conjunto de la tabla, así que salía con «Ninguno» y cuatro
        guiones — indistinguible de una faena que nunca tuvo permisos."""
        _permit(
            centre,
            FlightPermission.STATUS_EXPIRED,
            MONTH_START - timedelta(days=60),
            TODAY - timedelta(days=4),
        )

        row = _row(centre)

        assert row["expired_this_month"] == 1
        assert row["in_force"] == 0

    @pytest.mark.django_db
    def test_an_expiry_from_a_previous_month_does_not_pile_up(self, centre):
        """La ventana que eligió el usuario. Sin ella la columna acumula historia
        hasta volverse una lista que nadie termina de cerrar."""
        _permit(
            centre,
            FlightPermission.STATUS_EXPIRED,
            MONTH_START - timedelta(days=200),
            MONTH_START - timedelta(days=1),
        )

        assert permit_counts(TODAY, centre)["expired_this_month"] == 0
        assert _row(centre)["expired_this_month"] == 0


class TestTheAnomalyKeepsItsOwnCounter:
    @pytest.mark.django_db
    def test_an_approved_permit_with_a_past_date_is_still_lapsed(self, centre):
        """`lapsed` conserva su significado y **no** se funde con el anterior: un
        aprobado con la vigencia pasada es un permiso que nadie cerró, y eso delata
        que `expire_permissions` no corrió. Fundirlos perdería esa señal."""
        _permit(
            centre,
            FlightPermission.STATUS_APPROVED,
            MONTH_START - timedelta(days=60),
            TODAY - timedelta(days=3),
        )

        counts = permit_counts(TODAY, centre)

        assert counts["lapsed"] == 1
        assert counts["expired_this_month"] == 0

    @pytest.mark.django_db
    def test_the_anomaly_is_visible_however_old_it_is(self, centre):
        """Sin ventana, a diferencia del caducado: un aprobado sin cerrar desde hace
        tres meses significa que el trabajo nocturno lleva tres meses caído, y eso
        no debe dejar de verse por antiguo."""
        _permit(
            centre,
            FlightPermission.STATUS_APPROVED,
            MONTH_START - timedelta(days=300),
            MONTH_START - timedelta(days=90),
        )

        assert permit_counts(TODAY, centre)["lapsed"] == 1
        assert _row(centre)["lapsed"] == 1


class TestTheSignedFigureDoesNotMove:
    """🔶 Decisión del usuario: *"que no baje; mostrar aparte"*."""

    @pytest.mark.django_db
    def test_an_expired_permit_does_not_enter_the_denominator(self, centre):
        _permit(
            centre,
            FlightPermission.STATUS_APPROVED,
            TODAY - timedelta(days=10),
            TODAY + timedelta(days=10),
        )
        _permit(
            centre,
            FlightPermission.STATUS_EXPIRED,
            MONTH_START - timedelta(days=60),
            TODAY - timedelta(days=4),
        )

        counts = permit_counts(TODAY, centre)

        # Uno vivo y vigente: 1 de 1, no 1 de 2.
        assert (counts["in_force"], counts["total"]) == (1, 1)
        assert counts["pct"] == 100.0
        # Y el vencido se ve al lado.
        assert counts["expired_this_month"] == 1

    @pytest.mark.django_db
    def test_the_other_columns_are_untouched_by_the_wider_set(self, centre):
        """⚠️ La tabla pasó a **traer** los caducados para poder contarlos. Cada
        agregado filtra por su propio estado, así que eso no debe haber movido
        ninguna de las otras tres columnas — si las moviera, esta fila habría
        arreglado una cifra rompiendo tres.
        """
        _permit(
            centre,
            FlightPermission.STATUS_APPROVED,
            TODAY - timedelta(days=10),
            TODAY + timedelta(days=10),
        )
        _permit(
            centre,
            FlightPermission.STATUS_REQUESTED,
            TODAY,
            TODAY + timedelta(days=40),
        )
        _permit(
            centre,
            FlightPermission.STATUS_EXPIRED,
            MONTH_START - timedelta(days=60),
            TODAY - timedelta(days=4),
        )

        row = _row(centre)

        assert row["in_force"] == 1
        assert row["awaiting"] == 1
        assert row["soon"] == 1
        assert row["expired_this_month"] == 1
        # El caducado no se cuela en la próxima fecha de vencimiento, que manda la
        # renovación: `Min` mira sólo los aprobados con vigencia por delante.
        assert row["next_expiry"] == TODAY + timedelta(days=10)


class TestTheCardNoLongerPrintsANumberWithNoWord:
    @pytest.mark.django_db
    def test_every_readiness_row_names_its_shortfall(self, centre):
        """⚠️ **El guardián, y la razón de que sea sobre las cuatro filas.**

        El usuario reportó el número mudo en permisos, pero el defecto lo
        compartían tres de las cuatro: sólo la de flota declaraba
        `shortfall_label`, y la plantilla cae a `{{ shortfall }} {{
        shortfall_label }}` cuando el faltante no es ninguno de los términos
        nombrados. Se comprobó en pantalla: con una póliza con fecha futura y
        estado no activo, la tarjeta de seguros escribía *"0/1 · 1 · 1 vence en 30
        días"*.

        Una fila nueva sin rótulo vuelve a escribir un número solo, y eso no se ve
        leyendo el diccionario — se ve en la pantalla, tarde.
        """
        from apps.dashboard.views import panel_readiness

        rows = panel_readiness(TODAY, centre)["readiness"]

        assert len(rows) == 4
        assert all(row.get("shortfall_label") for row in rows), [
            row["key"] for row in rows if not row.get("shortfall_label")
        ]

    @pytest.mark.django_db
    def test_the_permits_row_names_its_shortfall(self, centre):
        """El usuario leyó *"13/14 · 1 · 2 vencen en 30 días"*: el 1 salía sin
        palabra porque esta fila era la única sin `shortfall_label`, y la plantilla
        caía a la rama que lo imprime seguido de una variable vacía."""
        from apps.dashboard.views import panel_readiness

        row = next(
            item
            for item in panel_readiness(TODAY, centre)["readiness"]
            if item["key"] == "permits"
        )

        assert row["shortfall_label"]

    @pytest.mark.django_db
    def test_an_approved_permit_that_has_not_started_says_so(self, centre):
        """Y ese 1 era esto: un permiso aprobado cuya vigencia empieza la semana que
        viene. `permit_counts` lo calculaba desde `LV-233` y el panel no lo dibujaba
        en ninguna parte, así que el número quedaba sin explicación posible."""
        from apps.dashboard.views import panel_readiness

        _permit(
            centre,
            FlightPermission.STATUS_APPROVED,
            TODAY + timedelta(days=7),
            TODAY + timedelta(days=60),
        )

        row = next(
            item
            for item in panel_readiness(TODAY, centre)["readiness"]
            if item["key"] == "permits"
        )

        assert row["not_started"] == 1
        # Y sigue sin contarse como vigente: existe y habilita, pero no hoy.
        assert (row["count"], row["total"]) == (0, 1)
