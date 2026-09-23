"""LV-243: «todo al día» sobre un conjunto vacío es una afirmación falsa.

Último hallazgo de la revisión de brechas del 2026-09-21. Con `total` en cero no
hay nada vencido, nada sin fecha y nada esperando, así que la tarjeta caía a la
última rama de la plantilla y declaraba **cumplimiento** — en la tira que existe
para contestar *"¿puedo operar hoy?"*.

Basta elegir una faena administrativa en el filtro del panel para leerlo: una que
no vuela no tiene flota, y la tarjeta de seguros decía *"0/0 · todo al día"*.

⚠️ **Es la misma familia que `LV-241`**: allá el problema era un contador que no
podía contar lo que decía contar; acá es una frase que afirma sobre lo que no
existe. Las dos se leen como tranquilidad.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.dashboard.views import panel_readiness
from apps.registry.models import Aircraft, CostCenter

TODAY = timezone.localdate()


def _rows(cost_center=None):
    return {row["key"]: row for row in panel_readiness(TODAY, cost_center)["readiness"]}


@pytest.mark.django_db
class TestAnEmptySetDoesNotClaimCompliance:
    def test_a_site_with_no_fleet_reports_no_records(self, db):
        """El caso que se lee eligiendo una faena administrativa."""
        empty = CostCenter.objects.create(
            code="CC410", name="Administración", operates_flights=True
        )

        rows = _rows(empty)

        assert rows["insurance"]["total"] == 0
        assert rows["insurance"]["pct"] is None

    def test_the_template_says_it_instead_of_all_up_to_date(self, client, admin_user):
        """De punta a punta, porque lo que falla es la **frase**: el contexto ya
        decía `total = 0` y `pct = None`, y la plantilla igual escribía que estaba
        todo al día. Un test sobre el diccionario habría pasado con el defecto
        puesto.
        """
        from django.urls import reverse

        empty = CostCenter.objects.create(
            code="CC410", name="Administración", operates_flights=True
        )
        client.force_login(admin_user)

        content = client.get(
            reverse("dashboard"), {"cost_center": empty.pk}
        ).content.decode()

        assert "sin registros" in content
        assert "todo al día" not in content

    def test_a_real_all_up_to_date_still_says_so(self, client, admin_user):
        """⚠️ La otra mitad, y la que evita que el arreglo apague una frase útil:
        cuando **sí** hay registros y **sí** están todos al día, eso es información
        y tiene que seguir diciéndose."""
        from django.urls import reverse

        site = CostCenter.objects.create(
            code="CC738", name="Faena", operates_flights=True
        )
        Aircraft.objects.create(
            registration="RPA-0001",
            type="RPA",
            model="M3",
            manufacturer="DJI",
            cost_center=site,
            status="active",
            insurance_status=Aircraft.INSURANCE_STATUS_ACTIVE,
            insurance_expiry=TODAY + timedelta(days=200),
        )
        client.force_login(admin_user)

        content = client.get(
            reverse("dashboard"), {"cost_center": site.pk}
        ).content.decode()

        assert "todo al día" in content
