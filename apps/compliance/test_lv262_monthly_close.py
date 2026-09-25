"""LV-262: el cierre mensual — registros operacionales y revisión, en una pantalla.

Pedido del usuario el 2026-09-25, pensando en la etapa de carga de datos:
*"ver cómo unificar y dejar herramientas más fácil y más condensado"*. En
producción los tres módulos estaban vacíos (0 registros, 0 revisiones, 0 no
conformidades, 0 vuelos), así que unificar no migraba ni arriesgaba nada.

Lo que se fija:

- una fila por faena **que opera**, haya volado en la app o no — con cero vuelos
  registrados en producción, el criterio de `LV-30` dejaba la pantalla vacía;
- los registros contados **por tipo**, y los que faltan, nombrados;
- marcar crea la revisión si no existe, y «no conforme» abre **una** no
  conformidad, enlazada a la revisión;
- los permisos y el alcance por tenant de siempre.
"""

from datetime import date

import pytest
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from apps.compliance.models import (
    Document,
    DocumentType,
    MonthlyComplianceReview,
    NonConformity,
)
from apps.core.testing import login_as
from apps.registry.models import CostCenter

MONTH = "2026-08"
PERIOD = date(2026, 8, 1)


@pytest.fixture
def types(db):
    return [
        DocumentType.objects.create(code=code, name=name, is_operational_record=True)
        for code, name in (
            ("flight-log", "Bitácora de vuelo (REG-015)"),
            ("rpa-checklist", "Check list RPA (LVE-003)"),
        )
    ]


def _centre(code, **extra):
    return CostCenter.objects.create(code=code, name=f"Faena {code}", **extra)


def _record(centre, doc_type, when=date(2026, 8, 10)):
    return Document.objects.create(
        title=f"{doc_type.code} {when}",
        doc_type=doc_type,
        content_type=ContentType.objects.get_for_model(CostCenter),
        object_id=centre.pk,
        file_path=f"rec/{centre.code}-{doc_type.code}-{when}.pdf",
        issue_date=when,
    )


def _rows(client):
    return client.get(reverse("monthly-review"), {"month": MONTH}).context["rows"]


@pytest.mark.django_db
class TestOneRowPerOperatingCostCentre:
    def test_a_cost_centre_that_did_not_fly_in_the_app_still_has_its_row(self, types):
        """El caso de producción: bitácoras en PDF, cero vuelos registrados."""
        _centre("CC1")

        rows = _rows(login_as("view_monthlycompliancereview"))

        assert [row["cost_center"].code for row in rows] == ["CC1"]
        assert rows[0]["flights"] == 0

    def test_non_flying_and_closed_cost_centres_are_left_out(self, types):
        """Las mismas que excluye el informe (`LV-205`, `LV-236`)."""
        _centre("CC1")
        _centre("CC110", operates_flights=False)
        _centre("CC9", contract_status=CostCenter.CONTRACT_CLOSED)

        rows = _rows(login_as("view_monthlycompliancereview"))

        assert [row["cost_center"].code for row in rows] == ["CC1"]

    def test_records_are_counted_by_type_and_the_missing_ones_named(self, types):
        log, checklist = types
        centre = _centre("CC1")
        _record(centre, log)
        _record(centre, log, date(2026, 8, 20))
        _record(centre, log, date(2026, 9, 2))  # otro mes: no cuenta

        row = _rows(login_as("view_monthlycompliancereview"))[0]

        counts = {item["doc_type"].code: item["count"] for item in row["records"]}
        assert counts == {"flight-log": 2, "rpa-checklist": 0}
        assert row["missing_types"] == [checklist]
        assert row["records_total"] == 2

    def test_the_chip_label_drops_the_form_code(self, types):
        _centre("CC1")

        response = login_as("view_monthlycompliancereview").get(
            reverse("monthly-review"), {"month": MONTH}
        )

        assert "Bitácora de vuelo · " in response.content.decode()

    def test_it_stays_within_three_queries_whatever_the_number_of_centres(
        self, types, django_assert_max_num_queries
    ):
        from apps.compliance.monthly import monthly_close_rows

        centres = [_centre(f"CC{n}") for n in range(8)]
        monthly_close_rows(PERIOD, centres, types)  # caché de ContentType caliente

        with django_assert_max_num_queries(3):
            monthly_close_rows(PERIOD, centres, types)


@pytest.mark.django_db
class TestMarkingFromTheClose:
    def _mark(self, client, centre, status, notes=""):
        return client.post(
            reverse("monthly-close-mark"),
            {
                "cost_center": centre.pk,
                "period": MONTH,
                "status": status,
                "notes": notes,
            },
        )

    def test_it_creates_the_review_when_there_is_none(self, types):
        centre = _centre("CC1")
        client = login_as("change_monthlycompliancereview")

        response = self._mark(client, centre, "completed")

        assert response.status_code == 302
        review = MonthlyComplianceReview.objects.get(cost_center=centre)
        assert review.period == PERIOD
        assert review.status == MonthlyComplianceReview.STATUS_COMPLETED

    def test_non_compliant_opens_one_non_conformity_linked_to_the_review(self, types):
        centre = _centre("CC1")
        client = login_as("change_monthlycompliancereview")

        self._mark(client, centre, "non_compliant", "Faltan los check list")
        self._mark(client, centre, "non_compliant", "Faltan los check list")

        review = MonthlyComplianceReview.objects.get(cost_center=centre)
        findings = NonConformity.objects.filter(cost_center=centre)
        assert findings.count() == 1
        finding = findings.get()
        assert finding.content_object == review
        assert finding.source == NonConformity.SOURCE_EXPIRED_DOCUMENT
        assert finding.description == "Faltan los check list"

    def test_compliant_opens_nothing(self, types):
        centre = _centre("CC1")

        self._mark(login_as("change_monthlycompliancereview"), centre, "completed")

        assert not NonConformity.objects.exists()

    def test_marking_needs_the_change_permission(self, types):
        centre = _centre("CC1")

        response = self._mark(
            login_as("view_monthlycompliancereview"), centre, "completed"
        )

        assert response.status_code == 403
        assert not MonthlyComplianceReview.objects.exists()

    def test_a_bad_period_is_refused(self, types):
        centre = _centre("CC1")
        client = login_as("change_monthlycompliancereview")

        response = client.post(
            reverse("monthly-close-mark"),
            {"cost_center": centre.pk, "period": "agosto", "status": "completed"},
        )

        assert response.status_code == 400


@pytest.mark.django_db
class TestReadingAndTenancy:
    def test_reading_needs_the_view_permission(self, types):
        assert login_as().get(reverse("monthly-review")).status_code == 403

    def test_another_tenants_cost_centre_is_neither_listed_nor_markable(self, types):
        from apps.core.models import OperationalTenant

        other = OperationalTenant.objects.create(name="Otro", slug="otro")
        foreign = _centre("CCX", tenant=other)
        _centre("CC1")
        client = login_as(
            "view_monthlycompliancereview", "change_monthlycompliancereview"
        )

        codes = [row["cost_center"].code for row in _rows(client)]
        response = client.post(
            reverse("monthly-close-mark"),
            {"cost_center": foreign.pk, "period": MONTH, "status": "completed"},
        )

        assert codes == ["CC1"]
        assert response.status_code == 404
        assert not MonthlyComplianceReview.objects.filter(cost_center=foreign).exists()


@pytest.mark.django_db
class TestTheMenu:
    def test_one_entry_for_the_close_and_none_for_the_old_list(self, admin_client):
        from django.utils.translation import gettext

        body = admin_client.get(reverse("dashboard")).content.decode()
        sidebar = body.split("<aside", 1)[1].split("</aside>", 1)[0]

        assert gettext("Monthly close") in sidebar
        assert reverse("operational-records") not in sidebar

    def test_the_records_list_is_still_reachable_and_links_back(self, admin_client):
        body = admin_client.get(reverse("operational-records")).content.decode()

        assert reverse("monthly-review") in body
