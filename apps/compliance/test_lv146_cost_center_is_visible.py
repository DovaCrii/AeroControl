"""LV-146: cada fila dice a qué faena pertenece, y la bandeja se puede filtrar.

Textual del usuario: *"las alarmas y el dashboard debe tener claro a qué centro
de costo […] está siendo afectada, para buscarlo, visualizar más rápido"*.

La mitad del trabajo ya estaba hecha y sin usar: `ALERT_COST_CENTER_PATHS` y
`alerts_for_cost_center` existen desde `LV-129` y sólo los llamaba el panel. La
columna nueva se construye **sobre la misma tabla de rutas**, así que no puede
discrepar del filtro — y el test que sostiene todo el diseño es
`test_it_agrees_with_alerts_for_cost_center`.

El caso difícil es `Document`: dos relaciones genéricas encadenadas (alerta →
documento → sujeto), resuelto en dos pasos y no con recursión, porque el sujeto
de un documento nunca es otro documento.
"""

from datetime import timedelta

import pytest
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import timezone

from apps.compliance.models import Alert, AlertRule, Document, DocumentType
from apps.compliance.reports import alerts_for_cost_center, cost_centers_for_refs
from apps.core.testing import login_as
from apps.maintenance.models import MaintenanceRecord
from apps.registry.models import (
    Aircraft,
    CostCenter,
    Operator,
    Qualification,
    QualificationType,
)

TODAY = timezone.localdate()


@pytest.fixture
def rule(db):
    return AlertRule.objects.create(
        name="Seguros JAC por vencer",
        entity_type="aircraft",
        field_to_watch="insurance_expiry",
        days_before_expiry=30,
    )


def _alert(rule, record, **kwargs):
    return Alert.objects.create(
        alert_rule=rule,
        content_type=ContentType.objects.get_for_model(type(record)),
        object_id=record.pk,
        message=kwargs.pop("message", "vence"),
        **kwargs,
    )


def _aircraft(registration, cost_center=None, **kwargs):
    return Aircraft.objects.create(
        registration=registration,
        type="Multirotor",
        model="M4E",
        manufacturer="DJI",
        cost_center=cost_center,
        **kwargs,
    )


def _ref(record):
    return (ContentType.objects.get_for_model(type(record)).id, record.pk)


@pytest.mark.django_db
class TestTheResolverFindsTheCostCenter:
    def test_an_aircraft_resolves_through_its_own_field(self):
        cost_center = CostCenter.objects.create(code="CC738", name="MLP")
        aircraft = _aircraft("RPA-4025", cost_center)

        mapping = cost_centers_for_refs([_ref(aircraft)])

        assert mapping[_ref(aircraft)] == cost_center

    def test_a_qualification_resolves_through_its_operator(self):
        cost_center = CostCenter.objects.create(code="CC738", name="MLP")
        operator = Operator.objects.create(
            employee_id="E-1", full_name="Ana Rivas", cost_center=cost_center
        )
        qualification = Qualification.objects.create(
            operator=operator,
            qualification_type=QualificationType.objects.create(
                name="Multirotor", code="MR"
            ),
            expiry_date=TODAY,
        )

        mapping = cost_centers_for_refs([_ref(qualification)])

        assert mapping[_ref(qualification)] == cost_center

    def test_a_maintenance_record_resolves_through_its_aircraft(self):
        cost_center = CostCenter.objects.create(code="CC738", name="MLP")
        aircraft = _aircraft("RPA-4025", cost_center)
        record = MaintenanceRecord.objects.create(
            aircraft=aircraft,
            maintenance_type="preventive",
            description="Revisión de hélices",
            scheduled_date=TODAY,
        )

        mapping = cost_centers_for_refs([_ref(record)])

        assert mapping[_ref(record)] == cost_center

    def test_a_document_resolves_through_the_record_it_hangs_from(self):
        # El caso difícil: dos relaciones genéricas encadenadas.
        cost_center = CostCenter.objects.create(code="CC738", name="MLP")
        aircraft = _aircraft("RPA-4025", cost_center)
        document = Document.objects.create(
            doc_type=DocumentType.objects.create(name="Póliza", code="poliza"),
            title="Póliza 2026",
            issue_date=TODAY,
            content_type=ContentType.objects.get_for_model(Aircraft),
            object_id=aircraft.pk,
        )

        mapping = cost_centers_for_refs([_ref(document)])

        assert mapping[_ref(document)] == cost_center

    def test_a_null_cost_center_resolves_to_nothing(self):
        # `Aircraft.cost_center` es nulo: "sin faena" es un caso real, no un
        # error, y la clave simplemente no está en el mapa.
        aircraft = _aircraft("RPA-4025", None)

        assert cost_centers_for_refs([_ref(aircraft)]) == {}

    def test_an_archived_record_still_belongs_to_its_cost_center(self):
        # Sin filtro `is_active`, igual que `alerts_for_cost_center`: una alerta
        # sobre un registro archivado sigue siendo de su faena.
        cost_center = CostCenter.objects.create(code="CC738", name="MLP")
        aircraft = _aircraft("RPA-4025", cost_center, is_active=False)

        assert cost_centers_for_refs([_ref(aircraft)])[_ref(aircraft)] == cost_center

    def test_no_refs_costs_no_queries(self, django_assert_num_queries):
        with django_assert_num_queries(0):
            assert cost_centers_for_refs([]) == {}

    def test_it_agrees_with_alerts_for_cost_center(self, rule):
        # El invariante que sostiene el diseño: lo que el mapa atribuye a una
        # faena es exactamente lo que el filtro devuelve para ella. Si alguna vez
        # dejan de coincidir, la columna estaría afirmando lo contrario de lo que
        # hace el filtro de al lado.
        mine = CostCenter.objects.create(code="CC738", name="MLP")
        other = CostCenter.objects.create(code="CC861", name="Talabre")
        alerts = [
            _alert(rule, _aircraft("RPA-1", mine)),
            _alert(rule, _aircraft("RPA-2", other)),
            _alert(rule, _aircraft("RPA-3", None)),
        ]

        mapping = cost_centers_for_refs(
            (alert.content_type_id, alert.object_id) for alert in alerts
        )
        attributed = {
            alert.pk
            for alert in alerts
            if mapping.get((alert.content_type_id, alert.object_id)) == mine
        }
        filtered = set(
            alerts_for_cost_center(Alert.objects.all(), mine).values_list(
                "pk", flat=True
            )
        )

        assert attributed == filtered

    def test_it_costs_one_query_per_model_not_one_per_row(
        self, rule, django_assert_max_num_queries
    ):
        cost_center = CostCenter.objects.create(code="CC738", name="MLP")
        refs = [_ref(_aircraft(f"RPA-{index}", cost_center)) for index in range(1, 21)]

        # Una por el modelo presente + una por los centros de costo. El tope es
        # holgado a propósito: lo que se afirma es que no crece con las filas.
        with django_assert_max_num_queries(4):
            cost_centers_for_refs(refs)


@pytest.mark.django_db
class TestTheTrayShowsAndFiltersIt:
    def test_the_row_shows_the_code(self, rule):
        cost_center = CostCenter.objects.create(code="CC738", name="MLP")
        _alert(rule, _aircraft("RPA-4025", cost_center))

        content = (
            login_as("view_alert", "view_costcenter")
            .get(reverse("alert-list"))
            .content.decode()
        )

        assert "cc-chip" in content
        assert "CC738" in content

    def test_an_entity_with_no_cost_center_renders_no_chip(self, rule):
        _alert(rule, _aircraft("RPA-4025", None))

        content = (
            login_as("view_alert", "view_costcenter")
            .get(reverse("alert-list"))
            .content.decode()
        )

        assert "cc-chip" not in content

    def test_filtering_narrows_the_list(self, rule):
        mine = CostCenter.objects.create(code="CC738", name="MLP")
        other = CostCenter.objects.create(code="CC861", name="Talabre")
        _alert(rule, _aircraft("RPA-1", mine))
        _alert(rule, _aircraft("RPA-2", other))
        client = login_as("view_alert", "view_costcenter")

        response = client.get(reverse("alert-list"), {"cost_center": mine.pk})

        assert len(response.context["objects"]) == 1

    def test_alerts_with_no_cost_center_drop_out_when_filtering(self, rule):
        mine = CostCenter.objects.create(code="CC738", name="MLP")
        _alert(rule, _aircraft("RPA-1", mine))
        _alert(rule, _aircraft("RPA-2", None))
        client = login_as("view_alert", "view_costcenter")

        response = client.get(reverse("alert-list"), {"cost_center": mine.pk})

        assert len(response.context["objects"]) == 1

    def test_without_a_filter_nothing_is_hidden(self, rule):
        mine = CostCenter.objects.create(code="CC738", name="MLP")
        _alert(rule, _aircraft("RPA-1", mine))
        _alert(rule, _aircraft("RPA-2", None))

        response = login_as("view_alert", "view_costcenter").get(reverse("alert-list"))

        assert len(response.context["objects"]) == 2

    def test_a_malformed_cost_center_is_a_no_op_not_a_500(self, rule):
        _alert(rule, _aircraft("RPA-1", None))

        response = login_as("view_alert", "view_costcenter").get(
            reverse("alert-list"), {"cost_center": "abc"}
        )

        assert response.status_code == 200

    def test_the_select_is_absent_without_view_costcenter(self, rule):
        CostCenter.objects.create(code="CC738", name="MLP")

        content = login_as("view_alert").get(reverse("alert-list")).content.decode()

        assert 'name="cost_center"' not in content

    def test_the_param_is_ignored_without_view_costcenter(self, rule):
        mine = CostCenter.objects.create(code="CC738", name="MLP")
        _alert(rule, _aircraft("RPA-1", mine))
        _alert(rule, _aircraft("RPA-2", None))

        response = login_as("view_alert").get(
            reverse("alert-list"), {"cost_center": mine.pk}
        )

        assert len(response.context["objects"]) == 2

    def test_the_code_shows_for_a_role_that_cannot_list_cost_centers(self, rule):
        # El chip no se gatea: un código junto a un registro que ya puedes leer
        # no es el padrón. El **selector** sí, porque ése es el catálogo.
        cost_center = CostCenter.objects.create(code="CC738", name="MLP")
        _alert(rule, _aircraft("RPA-4025", cost_center))

        content = login_as("view_alert").get(reverse("alert-list")).content.decode()

        assert "CC738" in content

    def test_the_tray_is_403_without_view_alert(self):
        assert login_as().get(reverse("alert-list")).status_code == 403

    def test_the_export_is_403_without_view_alert(self):
        # Un parámetro nuevo no puede ser un camino alrededor del permiso.
        response = login_as().get(
            reverse("alert-list"), {"cost_center": "x", "export": "csv"}
        )

        assert response.status_code == 403

    def test_the_list_does_not_cost_a_query_per_row(
        self, rule, django_assert_max_num_queries
    ):
        cost_center = CostCenter.objects.create(code="CC738", name="MLP")
        for index in range(12):
            _alert(rule, _aircraft(f"RPA-{index}", cost_center))
        client = login_as("view_alert", "view_costcenter")
        client.get(reverse("alert-list"))  # calentamiento: content types, sesión

        with django_assert_max_num_queries(20):
            client.get(reverse("alert-list"))


@pytest.mark.django_db
class TestTheExportNamesTheEntity:
    def _csv(self, client, **params):
        # `all` explícito: la bandeja abre en "sin resolver" (LV-118) y el export
        # honra el mismo filtro, así que sin esto una alerta resuelta no sale.
        response = client.get(
            reverse("alert-list"), {"export": "csv", "is_resolved": "all", **params}
        )
        return b"".join(response.streaming_content).decode("utf-8-sig")

    def test_the_csv_names_the_entity_and_its_cost_center(self, rule):
        cost_center = CostCenter.objects.create(code="CC738", name="MLP")
        _alert(rule, _aircraft("RPA-4025", cost_center))

        content = self._csv(login_as("view_alert", "view_costcenter"))

        assert "CC738" in content
        assert "RPA-4025" in content

    def test_the_csv_no_longer_emits_the_raw_content_type_and_object_id(self, rule):
        cost_center = CostCenter.objects.create(code="CC738", name="MLP")
        aircraft = _aircraft("RPA-4025", cost_center)
        _alert(rule, aircraft)

        content = self._csv(login_as("view_alert", "view_costcenter"))

        assert str(aircraft.pk) not in content

    def test_a_formula_in_a_resolution_reason_is_neutralized(self, rule):
        cost_center = CostCenter.objects.create(code="CC738", name="MLP")
        _alert(
            rule,
            _aircraft("RPA-4025", cost_center),
            is_resolved=True,
            resolution_reason="=SUM(A1:A9)",
        )

        content = self._csv(login_as("view_alert", "view_costcenter"))

        assert "'=SUM(A1:A9)" in content

    def test_a_formula_in_a_calculated_column_is_neutralized_too(self, rule):
        # La columna del centro de costo es calculada: pasa por `neutralize`
        # igual que las de campo, que es lo que AGENTS.md exige.
        cost_center = CostCenter.objects.create(code="=CC738", name="MLP")
        _alert(rule, _aircraft("RPA-4025", cost_center))

        content = self._csv(login_as("view_alert", "view_costcenter"))

        assert "'=CC738" in content


@pytest.mark.django_db
class TestThePanelRowsSayTheirCostCenter:
    def test_every_source_carries_its_cost_center(self):
        from apps.dashboard.views import upcoming_expirations

        cost_center = CostCenter.objects.create(code="CC738", name="MLP")
        _aircraft("RPA-4025", cost_center, insurance_expiry=TODAY)
        Operator.objects.create(
            employee_id="E-1",
            full_name="Ana Rivas",
            cost_center=cost_center,
            credential_expiry=TODAY,
        )

        items = upcoming_expirations(TODAY, TODAY + timedelta(days=30))

        assert items
        assert {item["cost_center_code"] for item in items} == {"CC738"}

    def test_an_item_with_no_cost_center_is_marked_as_such(self):
        from apps.dashboard.views import upcoming_expirations

        _aircraft("RPA-4025", None, insurance_expiry=TODAY)

        items = upcoming_expirations(TODAY, TODAY + timedelta(days=30))

        assert items[0]["cost_center_code"] == ""

    def test_the_code_reaches_the_page(self):
        cost_center = CostCenter.objects.create(code="CC738", name="MLP")
        _aircraft("RPA-4025", cost_center, insurance_expiry=TODAY)

        content = (
            login_as("view_aircraft", "view_costcenter")
            .get(reverse("dashboard"))
            .content.decode()
        )

        assert "cc-chip" in content
        assert "CC738" in content

    def test_the_chip_comes_before_the_kind_badge(self):
        cost_center = CostCenter.objects.create(code="CC738", name="MLP")
        _aircraft("RPA-4025", cost_center, insurance_expiry=TODAY)

        content = (
            login_as("view_aircraft", "view_costcenter")
            .get(reverse("dashboard"))
            .content.decode()
        )

        # LV-217: se pregunta por **el tono que le toca a esta fila**, no por un
        # color literal. El test usaba `bg-secondary-subtle` como proxy del badge
        # de tipo, y dejó de servir cuando los tipos pasaron a tener color propio:
        # esta fila es de una aeronave, así que su píldora ya no es la gris. Lo
        # que el test comprueba —que el chip de faena va **antes** que el tipo— no
        # cambió; cambió por dónde se localiza el tipo.
        from apps.compliance.digest import SUBJECT_TONE_CSS

        assert content.index("cc-chip") < content.index(SUBJECT_TONE_CSS["aircraft"])

    def test_a_malformed_cost_center_param_does_not_500_the_panel(self):
        response = login_as("view_aircraft").get(
            reverse("dashboard"), {"cost_center": "abc"}
        )

        assert response.status_code == 200

    def test_document_rows_now_respect_the_cost_center_filter(self):
        from apps.dashboard.views import upcoming_expirations

        mine = CostCenter.objects.create(code="CC738", name="MLP")
        other = CostCenter.objects.create(code="CC861", name="Talabre")
        doc_type = DocumentType.objects.create(name="Póliza", code="poliza")
        for cost_center, registration in ((mine, "RPA-1"), (other, "RPA-2")):
            aircraft = _aircraft(registration, cost_center)
            Document.objects.create(
                doc_type=doc_type,
                title=f"Póliza {registration}",
                issue_date=TODAY,
                expiry_date=TODAY,
                content_type=ContentType.objects.get_for_model(Aircraft),
                object_id=aircraft.pk,
            )

        items = upcoming_expirations(TODAY, TODAY + timedelta(days=30), mine)
        titles = {item["label"] for item in items}

        assert "Póliza RPA-1" in titles
        assert "Póliza RPA-2" not in titles
