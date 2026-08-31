"""LV-204: toda entidad dice de qué faena es, incluida la que cuelga de otra.

Pedido del usuario mirando la bandeja de alertas: *"la alerta debe mostrar de qué
CC pertenece la entidad, en todo tipo de caso"*. En su captura la fila de la
aeronave llevaba su chip `CC633` y la del documento **no llevaba ninguno**.

La causa no era el chip: era que `ALERT_COST_CENTER_PATHS` no seguía a
`DOCUMENTABLE_MODELS`, la lista que declara a qué puede colgar un documento.
Faltaban tres — `registry.costcenter`, `geo.geoplan` y
`operations.flightrequest`— y los dos últimos son de los más probables en la
etapa temprana: `R10.5` los agregó **precisamente** porque los papeles de una
faena (el KMZ del cliente, el correo que pide el vuelo, la constancia de SIGO)
llegan antes que el permiso, cuando el permiso todavía no existe.

Es la misma forma de defecto que `LV-188`, dos días de trabajo antes: dos listas
que tenían que coincidir y una se quedó atrás. Por eso el test que importa acá no
es ninguno de los casos sino `test_every_documentable_model_can_name_its_cost_center`,
que las cruza y falla cuando se separan.
"""

from datetime import timedelta

import pytest
from django.apps import apps as django_apps
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from apps.compliance.forms import DOCUMENTABLE_MODELS
from apps.compliance.models import Document, DocumentType
from apps.compliance.reports import (
    ALERT_COST_CENTER_PATHS,
    cost_centers_for_refs,
    documents_for_cost_center,
)
from apps.geo.models import GeoPlan
from apps.operations.models import FlightPermission, FlightRequest
from apps.registry.models import CostCenter

TODAY = timezone.localdate()

# La única excepción legítima, declarada en vez de deducida: un documento de
# empresa (el AOC, un procedimiento, un formulario) cuelga del tenant y **no es
# de ninguna faena**. `LV-146` ya decidió que "sin faena" es un caso real que se
# dice, no un hueco que se rellena.
NO_COST_CENTER = {("core", "operationaltenant")}


@pytest.fixture
def center(db):
    return CostCenter.objects.create(code="CC738", name="MLP")


def _plan(center, title):
    """`GeoPlan.created_by` es obligatorio: un plan siempre lo dibujó alguien."""
    from django.contrib.auth.models import User

    author, _created = User.objects.get_or_create(username="autor-204")
    return GeoPlan.objects.create(title=title, cost_center=center, created_by=author)


def _document(subject):
    return Document.objects.create(
        title="Carta Permiso",
        doc_type=DocumentType.objects.get_or_create(
            code="permit-letter", defaults={"name": "Carta"}
        )[0],
        content_type=ContentType.objects.get_for_model(type(subject)),
        object_id=subject.pk,
        issue_date=TODAY - timedelta(days=1),
        expiry_date=TODAY + timedelta(days=10),
        is_current_version=True,
    )


def _ref(record):
    return (ContentType.objects.get_for_model(type(record)).id, record.pk)


def test_every_documentable_model_can_name_its_cost_center():
    """**El test que sostiene la fila.** Todo modelo al que se le puede colgar un
    documento tiene que tener su ruta declarada, o ese documento queda sin faena
    en la bandeja, en el panel, en el filtro y en el informe de cumplimiento.

    Falla si alguien amplía `DOCUMENTABLE_MODELS` y no toca esta tabla — que es
    exactamente lo que había pasado con `geoplan` y `flightrequest`.
    """
    faltan = {
        f"{app_label}.{model_name}"
        for app_label, model_name in DOCUMENTABLE_MODELS - NO_COST_CENTER
        if f"{app_label}.{model_name}" not in ALERT_COST_CENTER_PATHS
    }

    assert not faltan, f"sin ruta a su centro de costo: {sorted(faltan)}"


def test_every_declared_path_resolves():
    """El contrapeso: una ruta escrita con un typo daría el mismo resultado que no
    tenerla —silencio— y este test la delata al recorrerla de verdad."""
    for label, path in ALERT_COST_CENTER_PATHS.items():
        app_label, model_name = label.split(".", 1)
        model = django_apps.get_model(app_label, model_name)

        # `values_list` valida la ruta contra el modelo sin necesidad de filas.
        model.objects.values_list("pk", path).query  # noqa: B018


@pytest.mark.django_db
class TestTheThreeThatWereMissing:
    def test_a_document_on_a_cost_center(self, center):
        """La faena de un centro de costo es él mismo, y ahora entra por la puerta
        normal en vez de un caso especial."""
        document = _document(center)

        assert cost_centers_for_refs([_ref(document)])[_ref(document)] == center

    def test_a_document_on_a_geospatial_plan(self, center):
        plan = _plan(center, "CG-02_circunferencia_grande")
        document = _document(plan)

        assert cost_centers_for_refs([_ref(document)])[_ref(document)] == center

    def test_a_document_on_a_flight_request(self, center):
        request = FlightRequest.objects.create(
            title="Quebrada km 13.760",
            cost_center=center,
            center_lat=-31.7,
            center_lon=-70.6,
        )
        document = _document(request)

        assert cost_centers_for_refs([_ref(document)])[_ref(document)] == center

    def test_they_also_survive_the_cost_center_filter(self, center):
        """`LV-188` unificó filtro y atribución en un solo recorrido de esta
        tabla, así que las tres rutas nuevas **llegan a los dos lados con la misma
        línea** — y eso es lo que esta fila cobra de esa: el filtro por faena y el
        informe de cumplimiento las aprenden sin tocar nada más."""
        plan = _plan(center, "CG-03")
        _document(plan)

        current = Document.objects.filter(is_active=True, is_current_version=True)
        assert documents_for_cost_center(center, current).count() == 1


@pytest.mark.django_db
class TestWhatStaysWithoutOne:
    def test_a_company_document_still_has_no_cost_center(self, center):
        """La excepción declarada: cuelga del tenant y no es de ninguna faena.
        Inventarle una sería peor que el guion — `LV-146`."""
        from apps.core.models import OperationalTenant

        tenant = OperationalTenant.objects.first()
        document = _document(tenant)

        assert cost_centers_for_refs([_ref(document)]) == {}

    def test_the_alert_tray_shows_the_chip_for_a_plan_document(self, center):
        """De punta a punta en la pantalla donde el usuario lo vio."""
        from apps.compliance.models import Alert, AlertRule
        from apps.core.testing import login_as
        from django.urls import reverse

        plan = _plan(center, "CG-04")
        document = _document(plan)
        rule = AlertRule.objects.create(
            name="Documentos por vencer",
            entity_type="compliance.document",
            field_to_watch="expiry_date",
            days_before_expiry=30,
        )
        Alert.objects.create(
            alert_rule=rule,
            content_type=ContentType.objects.get_for_model(Document),
            object_id=document.pk,
            message="vence",
        )

        content = (
            login_as("view_alert", "view_costcenter")
            .get(reverse("alert-list"))
            .content.decode()
        )

        assert "CC738" in content

    @pytest.mark.django_db
    def test_a_permit_document_was_already_working(self, center):
        """No es una regresión disfrazada de arreglo: el permiso ya estaba en la
        tabla, y sigue estando. Lo que faltaba eran los otros tres."""
        permit = FlightPermission.objects.create(
            internal_folio="JEJ-2026-204",
            cost_center=center,
            purpose="patrol",
            valid_from=TODAY,
            valid_until=TODAY + timedelta(days=60),
            location="Quebrada km 13",
            area_type="unpopulated",
        )
        document = _document(permit)

        assert cost_centers_for_refs([_ref(document)])[_ref(document)] == center
