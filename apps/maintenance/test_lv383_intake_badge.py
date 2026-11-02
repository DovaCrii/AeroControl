"""LV-383 (PR 4 de 4): el distintivo «Enviado sin aviso a casa matriz» y el filtro
`?sent_by=` de la lista de mantenciones.

Un equipo que el centro de costo manda al taller por su cuenta (`sent_by ==
"cost_center"`) no pasó por casa matriz. `head_office` y `unknown` no llevan el
distintivo: «no se sabe» no es lo mismo que «nadie avisó».

El distintivo se localiza por `data-intake-badge`, un atributo que sólo dibuja
este bloque; buscar por la clase `sev-caution` sería medir también cualquier
otro distintivo de la pantalla.
"""

import pytest
from django.urls import reverse
from django.utils.translation import gettext

from apps.core.models import OperationalTenant
from apps.core.testing import login_as
from apps.maintenance.models import MaintenanceRecord, WorkshopIntake
from apps.registry.models import Aircraft, CostCenter

MARKER = 'data-intake-badge="no-notice"'
LABEL = "Sent without notice to head office"


def _record(registration, tenant=None):
    extra = {"tenant": tenant} if tenant else {}
    aircraft = Aircraft.objects.create(
        registration=registration,
        type="RPA",
        model="M3",
        manufacturer="DJI",
        **extra,
    )
    return MaintenanceRecord.objects.create(
        aircraft=aircraft, maintenance_type="preventive", description="Revision"
    )


def _intake(record, sent_by, **extra):
    values = {"record": record, "workshop_name": "Taller Ejemplo", "sent_by": sent_by}
    if sent_by == WorkshopIntake.SENT_BY_COST_CENTER:
        values["sender_cost_center"] = CostCenter.objects.get_or_create(
            code="CC-EJ", defaults={"name": "Centro Ejemplo"}
        )[0]
    values.update(extra)
    return WorkshopIntake.objects.create(**values)


def _listing(client, **params):
    return client.get(reverse("maintenance-list"), params)


SENT_BY_VALUES = [value for value, _label in WorkshopIntake.SENT_BY_CHOICES]


@pytest.fixture
def three_records():
    """Una mantención por cada valor de `sent_by`, más una sin ingreso."""
    records = {}
    for index, value in enumerate(SENT_BY_VALUES):
        records[value] = _record(f"CC-S{index}")
        _intake(records[value], value)
    records["none"] = _record("CC-NONE")
    return records


@pytest.mark.django_db
class TestBadgeOnFiche:
    @pytest.mark.parametrize("sent_by", SENT_BY_VALUES)
    def test_badge_only_when_a_cost_center_sent_it(self, sent_by):
        record = _record("CC-AAA")
        _intake(record, sent_by)

        body = (
            login_as("view_maintenancerecord")
            .get(reverse("maintenance-detail", args=[record.pk]))
            .content.decode()
        )

        assert (MARKER in body) is (sent_by == WorkshopIntake.SENT_BY_COST_CENTER)

    def test_no_badge_without_an_intake(self):
        record = _record("CC-AAA")
        body = (
            login_as("view_maintenancerecord")
            .get(reverse("maintenance-detail", args=[record.pk]))
            .content.decode()
        )
        assert MARKER not in body

    def test_archived_intake_does_not_count(self):
        record = _record("CC-AAA")
        _intake(record, WorkshopIntake.SENT_BY_COST_CENTER, is_active=False)
        assert record.sent_without_head_office_notice is False

    def test_label_is_translated(self):
        from django.utils import translation

        with translation.override("es"):
            assert gettext(LABEL) == "Enviado sin aviso a casa matriz"


@pytest.mark.django_db
class TestBadgeInList:
    def test_badge_only_on_the_cost_center_row(self, three_records):
        body = _listing(login_as("view_maintenancerecord")).content.decode()

        # Una sola fila lleva el distintivo, y es la del centro de costo.
        assert body.count(MARKER) == 1
        row = body.split(MARKER)[0].rsplit("<tr", 1)[-1]
        assert (
            three_records[WorkshopIntake.SENT_BY_COST_CENTER].aircraft.registration
            in row
        )

    def test_list_does_not_query_the_intake_per_row(
        self, three_records, django_assert_max_num_queries
    ):
        client = login_as("view_maintenancerecord")
        _listing(client)  # calienta cachés de sesión y permisos
        with django_assert_max_num_queries(14):
            _listing(client)


@pytest.mark.django_db
class TestSentByFilter:
    @pytest.mark.parametrize("sent_by", SENT_BY_VALUES)
    def test_filter_keeps_only_that_origin(self, three_records, sent_by):
        body = _listing(
            login_as("view_maintenancerecord"), sent_by=sent_by
        ).content.decode()

        for key, record in three_records.items():
            assert (record.aircraft.registration in body) is (key == sent_by)

    def test_invalid_value_is_ignored(self, three_records):
        response = _listing(login_as("view_maintenancerecord"), sent_by="nonsense")
        body = response.content.decode()

        for record in three_records.values():
            assert record.aircraft.registration in body
        assert response.context["current_sent_by"] == ""

    def test_archived_intake_is_not_matched(self):
        record = _record("CC-AAA")
        _intake(record, WorkshopIntake.SENT_BY_COST_CENTER, is_active=False)

        body = _listing(
            login_as("view_maintenancerecord"),
            sent_by=WorkshopIntake.SENT_BY_COST_CENTER,
        ).content.decode()

        assert "CC-AAA" not in body

    def test_filter_is_kept_in_pagination_and_sort(self):
        for index in range(30):
            _intake(_record(f"CC-P{index:02d}"), WorkshopIntake.SENT_BY_COST_CENTER)

        body = _listing(
            login_as("view_maintenancerecord"),
            sent_by=WorkshopIntake.SENT_BY_COST_CENTER,
            sort="aircraft",
        ).content.decode()

        assert "page=2" in body
        assert body.count("sent_by=cost_center") >= 2  # paginación y orden

    def test_selected_option_is_marked(self):
        response = _listing(login_as("view_maintenancerecord"), sent_by="head_office")
        assert 'value="head_office" selected' in response.content.decode()

    def test_filter_is_scoped_to_the_tenant(self):
        a = OperationalTenant.objects.create(name="A", slug="a")
        b = OperationalTenant.objects.create(name="B", slug="b")
        mine = _record("CC-AAA", tenant=a)
        theirs = _record("CC-BBB", tenant=b)
        _intake(mine, WorkshopIntake.SENT_BY_COST_CENTER)
        _intake(theirs, WorkshopIntake.SENT_BY_COST_CENTER)

        body = _listing(
            login_as("view_maintenancerecord", member_of=a),
            sent_by=WorkshopIntake.SENT_BY_COST_CENTER,
        ).content.decode()

        assert "CC-AAA" in body
        assert "CC-BBB" not in body

    def test_list_is_403_without_view_permission(self):
        response = _listing(login_as(), sent_by=WorkshopIntake.SENT_BY_COST_CENTER)
        assert response.status_code == 403
