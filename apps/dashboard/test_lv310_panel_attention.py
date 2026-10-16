"""LV-310: «Requiere atención» y «Próximas mantenciones» en el panel.

El panel pasa de una rejilla de seis tarjetas de igual peso a un orden por la
pregunta que responde cada tramo: **qué hay que hacer** (chips con cifra, texto y
enlace), después «¿podemos operar?» y después el detalle. Estos tests afirman las
dos garantías que importan de un chip:

1. **Cada cifra lleva a una lista con el mismo número.** Un chip que dice 3 y
   enlaza a una lista de 5 filas enseña a desconfiar del panel entero.
2. **Sólo aparece lo que es mayor que cero**, y con todo en cero queda una línea
   neutra: «sin pendientes críticos» es justo lo que se viene a leer.

Las cifras se comparan contra el **contexto y las listas reales**, no contra
textos o clases tecleados a mano.
"""

from datetime import date, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.core.testing import login_as
from apps.maintenance.models import MaintenanceRecord
from apps.operations.models import FlightRequest
from apps.registry.models import Aircraft, CostCenter

TODAY = timezone.localdate()


def _aircraft(registration="RPA-0001", cost_center=None, **kwargs):
    return Aircraft.objects.create(
        registration=registration,
        type="RPA",
        model="M3",
        manufacturer="DJI",
        status="active",
        cost_center=cost_center,
        **kwargs,
    )


def _record(aircraft, scheduled=None, kind="preventive", status="pending", **kwargs):
    return MaintenanceRecord.objects.create(
        aircraft=aircraft,
        maintenance_type=kind,
        scheduled_date=scheduled,
        status=status,
        **kwargs,
    )


def _request(centre, title="Quebrada", status=FlightRequest.STATUS_FILED, **kwargs):
    return FlightRequest.objects.create(
        title=title,
        cost_center=centre,
        center_lat=-31.7,
        center_lon=-70.6,
        status=status,
        filed_on=TODAY - timedelta(days=4),
        **kwargs,
    )


def _chips(response):
    return {item["key"]: item for item in response.context["attention"]}


@pytest.mark.django_db
class TestEachChipCarriesItsNumberAndItsLink:
    def test_lapsed_expiries_link_to_the_expirations_section(self, admin_client):
        _aircraft(insurance_expiry=TODAY - timedelta(days=5))

        response = admin_client.get(reverse("dashboard"))

        chip = _chips(response)["overdue"]
        assert chip["count"] == response.context["overdue_count"] == 1
        assert chip["severity"] == "critical"
        assert chip["url"] == "#upcoming-expirations"
        assert 'id="upcoming-expirations"' in response.content.decode()
        # La cifra es la de las filas **vencidas** de esa lista, no otra.
        assert (
            sum(
                1
                for row in response.context["expirations"]
                if row["bucket"] == "overdue"
            )
            == chip["count"]
        )

    def test_sites_without_a_permit_link_to_the_table_that_lists_them(
        self, admin_client
    ):
        _aircraft()
        CostCenter.objects.create(
            code="CC900", name="Sin permiso", operates_flights=True
        )
        CostCenter.objects.create(code="CC901", name="Tampoco", operates_flights=True)

        response = admin_client.get(reverse("dashboard"))

        chip = _chips(response)["sites_without_permit"]
        content = response.content.decode()
        assert chip["severity"] == "critical"
        assert chip["url"] == "#panel-permit-status-title"
        assert 'id="panel-permit-status-title"' in content
        # La cifra es el número de filas de la tabla a la que enlaza que no tienen
        # permiso vigente.
        rows = response.context["permit_status_rows"]
        assert chip["count"] == sum(1 for row in rows if not row["in_force"]) == 2

    def test_maintenance_to_define_links_to_a_list_with_the_same_number(
        self, admin_client
    ):
        aircraft = _aircraft()
        _record(aircraft, kind="to_be_defined")  # cuenta: tipo por definir
        _record(aircraft, scheduled=None, status="in_progress")  # cuenta: sin fecha
        _record(aircraft, scheduled=TODAY + timedelta(days=9))  # no: tiene fecha
        _record(aircraft, kind="to_be_defined", status="completed")  # no: terminada
        _record(aircraft, kind="to_be_defined", is_active=False)  # no: archivada

        response = admin_client.get(reverse("dashboard"))
        chip = _chips(response)["maintenance_to_define"]
        listed = admin_client.get(chip["url"])

        assert chip["severity"] == "warning"
        assert chip["count"] == response.context["incomplete_maintenance_count"] == 2
        assert listed.context["paginator"].count == chip["count"]

    def test_awaiting_sigo_links_to_the_filed_requests_and_names_the_wait(
        self, admin_client
    ):
        _aircraft()
        centre = CostCenter.objects.create(code="CC738", name="Faena")
        _request(centre, "Uno")
        _request(centre, "Dos")
        _request(centre, "Borrador", status=FlightRequest.STATUS_PREPARED)

        response = admin_client.get(reverse("dashboard"))
        chip = _chips(response)["awaiting_sigo"]
        listed = admin_client.get(chip["url"])

        assert chip["count"] == response.context["awaiting_count"] == 2
        assert chip["longest_wait"] == 4
        assert listed.context["paginator"].count == chip["count"]

    def test_a_pending_monthly_close_links_to_the_monthly_review(self, admin_client):
        from apps.compliance.models import MonthlyComplianceReview

        _aircraft()
        centre = CostCenter.objects.create(code="CC738", name="Faena")
        MonthlyComplianceReview.objects.create(
            cost_center=centre, period=date(TODAY.year, TODAY.month, 1)
        )

        response = admin_client.get(reverse("dashboard"))

        chip = _chips(response)["monthly_close"]
        assert chip["count"] == response.context["monthly_records"]["pending"] == 1
        assert chip["severity"] == "warning"
        assert chip["url"] == reverse("monthly-review")


@pytest.mark.django_db
class TestOnlyWhatIsAboveZeroAppears:
    def test_with_everything_at_zero_there_is_one_neutral_line(self, admin_client):
        from django.utils.translation import gettext

        _aircraft(insurance_expiry=TODAY + timedelta(days=300))

        response = admin_client.get(reverse("dashboard"))
        content = response.content.decode()
        section = content.split('id="panel-attention"')[1].split("</section>")[0]

        assert response.context["attention"] == []
        assert "attention-chip" not in section
        assert "✓" in section
        assert gettext("No critical pending items") in section

    def test_red_is_only_for_lapsed_and_sites_without_a_permit(self, admin_client):
        aircraft = _aircraft(insurance_expiry=TODAY - timedelta(days=5))
        CostCenter.objects.create(code="CC900", name="Sin", operates_flights=True)
        _record(aircraft, kind="to_be_defined")
        _request(CostCenter.objects.get(code="CC900"))

        response = admin_client.get(reverse("dashboard"))

        severities = {key: chip["severity"] for key, chip in _chips(response).items()}
        assert severities == {
            "overdue": "critical",
            "sites_without_permit": "critical",
            "maintenance_to_define": "warning",
            "awaiting_sigo": "warning",
        }
        # Y van en ese orden: lo crítico primero.
        assert list(severities.values()) == sorted(severities.values())

    def test_the_site_figure_obeys_the_chosen_cost_centre(self, admin_client):
        """El defecto que esta fila corrige: `permit_status_by_cost_center` devuelve
        todas las faenas, así que «Faenas sin permiso» decía 2 sobre un panel
        filtrado a una sola, mientras el resto de las cifras obedecía el filtro."""
        _aircraft()
        chosen = CostCenter.objects.create(
            code="CC900", name="Uno", operates_flights=True
        )
        CostCenter.objects.create(code="CC901", name="Dos", operates_flights=True)

        everything = admin_client.get(reverse("dashboard"))
        filtered = admin_client.get(reverse("dashboard"), {"cost_center": chosen.pk})

        assert everything.context["cost_centres_without_permit"] == 2
        assert filtered.context["cost_centres_without_permit"] == 1
        assert _chips(filtered)["sites_without_permit"]["count"] == 1
        assert [
            row["cost_center"] for row in filtered.context["permit_status_rows"]
        ] == [chosen]


@pytest.mark.django_db
class TestUpcomingMaintenance:
    def test_the_five_nearest_with_no_date_first_and_completed_excluded(
        self, admin_client
    ):
        aircraft = _aircraft()
        undated = _record(aircraft, scheduled=None, kind="to_be_defined")
        dated = [
            _record(aircraft, scheduled=TODAY + timedelta(days=days))
            for days in (30, 3, 12, 7, 20, 40)
        ]
        _record(aircraft, scheduled=TODAY + timedelta(days=1), status="completed")

        response = admin_client.get(reverse("dashboard"))

        shown = response.context["upcoming_maintenance"]
        assert len(shown) == 5
        assert shown[0] == undated
        by_date = sorted(dated, key=lambda record: record.scheduled_date)
        assert shown[1:] == by_date[:4]
        assert all(record.status != "completed" for record in shown)

    def test_each_row_names_the_aircraft_and_links_to_the_record(self, admin_client):
        record = _record(_aircraft("RPA-7777"), scheduled=TODAY + timedelta(days=3))

        content = admin_client.get(reverse("dashboard")).content.decode()
        section = content.split('id="upcoming-maintenance"')[1].split("</section>")[0]

        assert "RPA-7777" in section
        assert record.get_absolute_url() in section
        assert record.get_maintenance_type_display() in section

    def test_the_chosen_cost_centre_narrows_the_list(self, admin_client):
        mine = CostCenter.objects.create(code="CC900", name="Mía")
        other = CostCenter.objects.create(code="CC901", name="Otra")
        kept = _record(_aircraft("RPA-1", mine), scheduled=TODAY + timedelta(days=3))
        _record(_aircraft("RPA-2", other), scheduled=TODAY + timedelta(days=2))

        response = admin_client.get(reverse("dashboard"), {"cost_center": mine.pk})

        assert response.context["upcoming_maintenance"] == [kept]

    def test_without_the_read_permission_the_section_is_absent(self):
        """Nombra matrículas: sin `view_maintenancerecord` ni se consulta ni se
        dibuja (LV-191). Se prueba con un usuario que **sí** ve el panel."""
        _record(_aircraft("RPA-7777"), scheduled=TODAY + timedelta(days=3))
        client = login_as("view_aircraft")

        response = client.get(reverse("dashboard"))

        assert response.status_code == 200
        assert response.context["upcoming_maintenance"] == []
        assert 'id="upcoming-maintenance"' not in response.content.decode()
        assert "RPA-7777" not in response.content.decode()

    def test_the_maintenance_type_chart_is_gone(self, admin_client):
        _record(_aircraft(), scheduled=TODAY + timedelta(days=3))

        response = admin_client.get(reverse("dashboard"))

        assert "maintenance_by_type" not in response.context["chart_data"]
        assert "chart-maint-type" not in response.content.decode()


@pytest.mark.django_db
class TestTheMaintenanceListFilter:
    def test_needs_planning_is_the_same_criterion_as_the_panel(self, admin_client):
        aircraft = _aircraft()
        _record(aircraft, kind="to_be_defined")
        _record(aircraft, scheduled=TODAY + timedelta(days=5))

        everything = admin_client.get(reverse("maintenance-list"))
        planning = admin_client.get(reverse("maintenance-list"), {"needs_planning": 1})

        assert everything.context["paginator"].count == 2
        assert planning.context["paginator"].count == 1
        assert planning.context["is_filtered"] is True


@pytest.mark.django_db
class TestTheExpirationRowIsReadableWithoutColour:
    def test_an_overdue_row_has_a_dot_and_a_text_badge(self, admin_client):
        from apps.compliance.digest import BUCKET_BADGE_CSS

        _aircraft(insurance_expiry=TODAY - timedelta(days=5))

        response = admin_client.get(reverse("dashboard"))
        content = response.content.decode()
        section = content.split('id="upcoming-expirations"')[1]
        row = section.split("border-bottom py-1")[1].split("</a>")[0]

        assert (
            response.context["expirations"][0]["badge_css"]
            == (BUCKET_BADGE_CSS["overdue"])
        )
        assert "●" in row
        assert f"badge {BUCKET_BADGE_CSS['overdue']}" in row
