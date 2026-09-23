"""LV-254: las listas más usadas, con reparto de columnas y un vacío que sirve.

Fase 2 del plan de mejora del 2026-09-23. El reparto en sí lo vigila
`test_lv162_table_column_widths` (ahora también el sobrante de la columna
flexible); acá va lo que se ve en la página: la nómina recortada en permisos, el
vacío que ofrece quitar el filtro en las listas que tienen filtros propios, y
mantención entrando por la tabla de trabajo compartida.
"""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext

from apps.core.testing import login_as

TODAY = timezone.localdate()
CLEAR = gettext("Clear filters")


def _rows(content):
    """Sólo el cuerpo de la tabla: el armazón comparte vocabulario con las filas
    (lección de `LV-118`)."""
    return content.split('id="table-body"')[-1].split("</tbody>")[0]


@pytest.mark.django_db
class TestThePermitRowNamesThreeOperators:
    def _permit_with(self, count):
        from apps.operations.models import FlightPermission
        from apps.registry.models import CostCenter, Operator

        centre = CostCenter.objects.create(code="CC254", name="Faena 254")
        permit = FlightPermission.objects.create(
            cost_center=centre,
            purpose="photogrammetry",
            status="approved",
            location="Sector",
            area_type="unpopulated",
            valid_from=TODAY,
            valid_until=TODAY + timedelta(days=60),
        )
        operators = [
            Operator.objects.create(
                employee_id=f"E-254-{index}",
                full_name=f"Operador {index:02d}",
                cost_center=centre,
            )
            for index in range(count)
        ]
        permit.operators.set(operators)
        return operators

    def test_a_long_roster_is_cut_to_three_with_the_rest_counted(self, admin_client):
        """Once operadores, como un permiso real: la fila crecía a 338 px."""
        operators = self._permit_with(11)
        shown = sorted(str(operator) for operator in operators)

        rows = _rows(admin_client.get(reverse("permission-list")).content.decode())
        cell = rows.split("data-more-operators")[0]

        assert "data-more-operators" in rows
        assert "+8" in rows
        visible = [name for name in shown if f">{name}" in cell or f", {name}" in cell]
        assert len(visible) == 3, visible

    def test_the_title_keeps_the_whole_roster(self, admin_client):
        operators = self._permit_with(5)

        rows = _rows(admin_client.get(reverse("permission-list")).content.decode())
        title = rows.split("data-more-operators")[1].split('title="')[1].split('"')[0]

        for operator in operators:
            assert str(operator) in title

    def test_a_short_roster_is_not_cut(self, admin_client):
        self._permit_with(3)

        rows = _rows(admin_client.get(reverse("permission-list")).content.decode())

        assert "data-more-operators" not in rows


@pytest.mark.django_db
class TestAnEmptyFilterOffersTheWayBack:
    """`SearchMixin` sólo cuenta `q`/`is_active`. Estas tres listas tienen filtros
    propios, y un filtro sin resultados decía «todavía no hay registros»."""

    @pytest.mark.parametrize(
        "url_name, codename, query",
        [
            ("nonconformity-list", "view_nonconformity", {"status": "closed"}),
            ("document-list", "view_document", {"is_current_version": "false"}),
            ("maintenance-list", "view_maintenancerecord", {"status": "completed"}),
        ],
    )
    def test_the_own_filter_counts_as_a_filter(self, url_name, codename, query):
        client = login_as(codename)

        response = client.get(reverse(url_name), query)

        assert response.status_code == 200
        assert response.context["is_filtered"] is True
        assert CLEAR in _rows(response.content.decode())

    @pytest.mark.parametrize(
        "url_name, codename",
        [
            ("nonconformity-list", "view_nonconformity"),
            ("document-list", "view_document"),
            ("maintenance-list", "view_maintenancerecord"),
        ],
    )
    def test_without_filters_it_is_not_filtered(self, url_name, codename):
        client = login_as(codename)

        response = client.get(reverse(url_name))

        assert response.context["is_filtered"] is False
        assert CLEAR not in _rows(response.content.decode())


@pytest.mark.django_db
class TestTheDocumentListMarksWhatLapsed:
    def test_an_expired_document_carries_the_mark(self, admin_client):
        from django.contrib.contenttypes.models import ContentType

        from apps.compliance.models import Document, DocumentType
        from apps.registry.models import Aircraft

        aircraft = Aircraft.objects.create(
            registration="RPA-254", type="RPA", model="M3", manufacturer="DJI"
        )
        Document.objects.create(
            content_type=ContentType.objects.get_for_model(Aircraft),
            object_id=aircraft.pk,
            doc_type=DocumentType.objects.create(code="P254", name="Póliza"),
            title="Póliza vencida",
            file_path="x.pdf",
            issue_date=TODAY - timedelta(days=400),
            expiry_date=TODAY - timedelta(days=5),
        )

        rows = _rows(admin_client.get(reverse("document-list")).content.decode())

        assert 'class="badge sev-critical">⚠ ' + gettext("Expired") in rows


@pytest.mark.django_db
class TestMaintenanceUsesTheSharedWorktable:
    def _record(self):
        from apps.maintenance.models import MaintenanceRecord
        from apps.registry.models import Aircraft

        aircraft = Aircraft.objects.create(
            registration="RPA-2540", type="RPA", model="M3", manufacturer="DJI"
        )
        return MaintenanceRecord.objects.create(
            aircraft=aircraft,
            maintenance_type="scheduled",
            status="pending",
            description="Revisión",
        )

    def test_the_rows_are_selectable(self, admin_client):
        record = self._record()

        content = admin_client.get(reverse("maintenance-list")).content.decode()

        assert f'data-pk="{record.pk}"' in _rows(content)
        assert "table-normalized" in content

    def test_a_live_search_returns_its_own_rows(self, admin_client):
        """Sin su parcial, la respuesta HTMX caería en el genérico y la tabla
        colapsaría a las columnas de nombre/creado/estado."""
        record = self._record()

        response = admin_client.get(
            reverse("maintenance-list"), {"q": "RPA-2540"}, HTTP_HX_REQUEST="true"
        )

        assert [t.name for t in response.templates][0] == (
            "maintenance/_record_rows.html"
        )
        assert f'data-pk="{record.pk}"' in response.content.decode()

    def test_reading_needs_the_view_permission(self):
        assert login_as().get(reverse("maintenance-list")).status_code == 403
