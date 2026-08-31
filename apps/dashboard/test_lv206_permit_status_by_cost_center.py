"""LV-206: qué faenas tienen permisos vigentes y cuáles no.

Pedido del usuario: *"necesito además una opción de poner los CC que hoy tienen y
los que no tienen permisos vigentes, quitar el clima ahí y poner una tabla
interactiva; ahora los 2 CC que no deben estar para la tabla, poder poner cuáles
serán vistos y cuáles no, ya que el CC110 de casa matriz o 410 por ejemplo estamos
a cargo más de los equipos que volar"*.

Tres cosas, y se hicieron separadas:

1. **La tabla parte de las faenas, no de los permisos.** Un `GROUP BY` sobre
   permisos sólo devuelve las faenas que tienen alguno, y las que interesan son
   las que **no** tienen ninguno: al revés, esas filas no existirían y la tabla
   contestaría lo contrario de la pregunta.
2. **`operates_flights` en `CostCenter`**, un eje declarado y no una lista de
   códigos en el código: `CC110` y `CC410` son los de hoy, y una constante con
   esos dos se desactualiza —en silencio, y del lado que declara incumplimientos
   falsos— el día que alguien abre una faena nueva de bodega.
3. **El clima se mueve, no se quita.** Es el único lugar desde donde se registra
   la revisión meteorológica, y el usuario **acaba de confirmar en `LV-194` que esa
   revisión es necesaria** en el expediente: quitándola, ese renglón quedaría sin
   la pantalla que lo cierra. La tabla ocupa su lugar y el clima baja.
"""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.compliance.kpis import permit_status_by_cost_center
from apps.operations.models import FlightPermission
from apps.registry.models import CostCenter

TODAY = timezone.localdate()


def _center(code, name="Faena", flies=True):
    return CostCenter.objects.create(code=code, name=name, operates_flights=flies)


def _permit(center, folio, status=FlightPermission.STATUS_APPROVED, until_days=60):
    return FlightPermission.objects.create(
        internal_folio=folio,
        cost_center=center,
        purpose="patrol",
        valid_from=TODAY - timedelta(days=1),
        valid_until=TODAY + timedelta(days=until_days),
        location="Quebrada km 13",
        area_type="unpopulated",
        status=status,
    )


def _row(rows, code):
    return next(row for row in rows if row["cost_center"].code == code)


@pytest.mark.django_db
class TestTheTableAnswersTheQuestion:
    def test_a_cost_center_with_no_permits_is_listed(self):
        """**La razón de existir de la tabla.** Es la fila que un recorrido sobre
        permisos no devolvería."""
        _center("CC738", "MLP")

        rows = permit_status_by_cost_center(TODAY)

        assert _row(rows, "CC738")["in_force"] == 0

    def test_one_with_permits_shows_its_count(self):
        center = _center("CC738", "MLP")
        _permit(center, "JEJ-001")
        _permit(center, "JEJ-002")

        assert _row(permit_status_by_cost_center(TODAY), "CC738")["in_force"] == 2

    def test_the_three_columns_are_separate(self):
        """Vigentes, esperando y con la vigencia pasada se arreglan distinto — la
        lección de `LV-129`, y la misma separación que la tarjeta del panel."""
        center = _center("CC738", "MLP")
        _permit(center, "JEJ-001")
        _permit(center, "JEJ-002", status=FlightPermission.STATUS_REQUESTED)
        _permit(center, "JEJ-003", until_days=-5)

        row = _row(permit_status_by_cost_center(TODAY), "CC738")

        assert (row["in_force"], row["awaiting"], row["lapsed"]) == (1, 1, 1)

    def test_expiring_soon_is_counted(self):
        center = _center("CC738", "MLP")
        _permit(center, "JEJ-001", until_days=10)

        assert _row(permit_status_by_cost_center(TODAY), "CC738")["soon"] == 1

    def test_it_is_ordered_by_code(self):
        _center("CC861", "Talabre")
        _center("CC110", "Casa Matriz")
        _center("CC738", "MLP")

        codes = [row["cost_center"].code for row in permit_status_by_cost_center(TODAY)]

        assert codes == ["CC110", "CC738", "CC861"]

    def test_it_does_not_cost_a_query_per_cost_center(self, django_assert_num_queries):
        """Recorrer `permit_counts` por faena habría costado cuatro consultas por
        fila en una pantalla que se abre en cada inicio de sesión. Son dos: las
        faenas y el agregado de todos sus permisos."""
        for index in range(6):
            center = _center(f"CC{index:03d}")
            _permit(center, f"JEJ-{index:03d}")

        with django_assert_num_queries(2):
            permit_status_by_cost_center(TODAY)


@pytest.mark.django_db
class TestTheOnesThatDoNotFly:
    def test_they_are_left_out(self):
        """`CC110` administra equipos: listarla como "sin permisos vigentes" la
        declararía incumplida por una operación que no le toca."""
        _center("CC738", "MLP")
        _center("CC110", "Casa Matriz", flies=False)

        codes = [row["cost_center"].code for row in permit_status_by_cost_center(TODAY)]

        assert codes == ["CC738"]

    def test_the_default_is_that_it_flies(self):
        """El valor por defecto no puede cambiar nada para las faenas que ya
        existen: la mayoría vuela."""
        assert CostCenter.objects.create(code="CC999").operates_flights is True

    def test_an_archived_cost_center_is_out_too(self):
        _center("CC738", "MLP")
        archived = _center("CC861", "Talabre")
        archived.is_active = False
        archived.save(update_fields=["is_active"])

        codes = [row["cost_center"].code for row in permit_status_by_cost_center(TODAY)]

        assert codes == ["CC738"]

    def test_the_form_offers_the_switch(self):
        """Sin el campo en el formulario, el eje existiría y nadie podría ponerlo
        — que es la mitad del pedido."""
        from apps.registry.forms import CostCenterForm

        assert "operates_flights" in CostCenterForm().fields


@pytest.mark.django_db
class TestOnThePanel:
    def _content(self, client, django_user_model):
        # La aeronave no es decoración: sin flota ni padrón el panel dibuja la
        # tarjeta de bienvenida y esconde todo lo demás — es el guard de `LV-187`,
        # y acá se le da a la operación lo mínimo para que el panel sea el panel.
        from apps.registry.models import Aircraft

        Aircraft.objects.create(
            registration="RPA-4401", serial_number="S1", status="active"
        )
        django_user_model.objects.create_superuser("admin", "a@test.com", "password")
        assert client.login(username="admin", password="password")
        return client.get(reverse("dashboard")).content.decode()

    def test_the_table_is_drawn(self, client, django_user_model):
        center = _center("CC738", "MLP")
        _permit(center, "JEJ-001")

        content = self._content(client, django_user_model)

        assert "Permisos de vuelo por centro de costo" in content
        assert "CC738" in content

    def test_a_cost_center_with_none_says_so(self, client, django_user_model):
        _center("CC738", "MLP")

        content = self._content(client, django_user_model)

        assert "Ninguno" in content

    def test_the_table_comes_before_the_weather(self, client, django_user_model):
        """El pedido era el **lugar**: la tabla donde estaba el clima. El clima no
        se quita porque es de donde se registra la revisión meteorológica, que
        `LV-194` acaba de confirmar como necesaria en el expediente."""
        center = _center("CC738", "MLP")
        _permit(center, "JEJ-001")

        content = self._content(client, django_user_model)

        # Se comparan los `id` de las dos secciones y no su texto: el título del
        # clima se ve en mayúsculas por CSS, así que buscarlo tal como aparece en
        # pantalla es la fragilidad que `LV-95` dejó documentada.
        assert "panel-permit-status-title" in content
        if "panel-weather-title" in content:
            assert content.index("panel-permit-status-title") < content.index(
                "panel-weather-title"
            )
