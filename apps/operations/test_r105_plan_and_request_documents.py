"""R10.5: el plan geoespacial y la solicitud SIGO también reciben documentos.

`DOCUMENTABLE_MODELS` no los incluía, así que no se les podía adjuntar nada: el
único colgadero del flujo era `FlightPermission`, que en la etapa del plan
—cuando llegan el KMZ del cliente, el correo que pide el vuelo, la constancia de
lo presentado en SIGO— **todavía no existe**. El archivo terminaba en el disco
de alguien.

La sección es la compartida (`compliance/_documents_section.html` +
`attached_documents_context`), la misma que llevan la aeronave, el operador, el
centro de costo y el permiso; estos tests afirman que ambas fichas la dibujan y
que el formulario de carga acepta los dos tipos nuevos.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from apps.compliance.forms import DOCUMENTABLE_MODEL_LABELS, DOCUMENTABLE_MODELS
from apps.compliance.models import Document, DocumentType
from apps.core.testing import login_as
from apps.geo.models import GeoPlan
from apps.registry.models import CostCenter

from .models import FlightRequest


def _attach(record, title):
    doc_type = DocumentType.objects.create(code=f"T-{title[:8]}", name="Tipo")
    return Document.objects.create(
        content_type=ContentType.objects.get_for_model(record),
        object_id=record.pk,
        doc_type=doc_type,
        title=title,
        issue_date=date(2026, 8, 24),
        file_path="x",
    )


@pytest.fixture
def cost_center(db):
    return CostCenter.objects.create(code="CC738", name="MLP")


@pytest.fixture
def plan(cost_center):
    owner = login_as().user
    return GeoPlan.objects.create(
        title="Circunferencias grandes CG-01..07",
        cost_center=cost_center,
        created_by=owner,
    )


@pytest.fixture
def flight_request(cost_center):
    # El centro y el radio reales de CG-01, que son obligatorios en el modelo:
    # una solicitud SIGO sin punto central no es una solicitud.
    return FlightRequest.objects.create(
        title="CG-01 | Quebrada km 13.760",
        cost_center=cost_center,
        center_lat=Decimal("-31.906392"),
        center_lon=Decimal("-70.717982"),
        radius_m=2018,
    )


class TestTheCatalogOfDocumentableRecords:
    def test_both_records_can_receive_documents(self):
        assert ("geo", "geoplan") in DOCUMENTABLE_MODELS
        assert ("operations", "flightrequest") in DOCUMENTABLE_MODELS

    def test_every_documentable_record_has_a_label(self):
        """El formulario rotula la opción con `DOCUMENTABLE_MODEL_LABELS[clave]`.

        Sin entrada, el selector de "Registro relacionado" muere con `KeyError`
        al dibujarse -- una pantalla en blanco, no un dato en inglés. Se afirma
        sobre el conjunto entero y no sobre los dos nuevos, que es lo que
        convierte este test en un guardián del próximo que se agregue.
        """
        assert not DOCUMENTABLE_MODELS - set(DOCUMENTABLE_MODEL_LABELS)


class TestThePlansFiche:
    @pytest.mark.django_db
    def test_shows_its_attached_documents(self, plan):
        _attach(plan, "Correo que pide el vuelo")

        response = login_as("view_geoplan", "view_document").get(
            reverse("geo-plan-detail", args=[plan.pk])
        )

        assert "Correo que pide el vuelo" in response.content.decode()

    @pytest.mark.django_db
    def test_hidden_without_view_document_permission(self, plan):
        response = login_as("view_geoplan").get(
            reverse("geo-plan-detail", args=[plan.pk])
        )

        # El contexto es la señal fiable: la barra lateral lleva un enlace
        # "Documentos" propio, así que buscar la palabra en la página daría un
        # falso negativo (mismo razonamiento que en OPS-5).
        assert response.context["documents"] is None

    @pytest.mark.django_db
    def test_the_upload_link_needs_add_document(self, plan):
        upload_href = reverse("document-create")

        without = login_as("view_geoplan", "view_document").get(
            reverse("geo-plan-detail", args=[plan.pk])
        )
        with_add = login_as("view_geoplan", "view_document", "add_document").get(
            reverse("geo-plan-detail", args=[plan.pk])
        )

        assert upload_href not in without.content.decode()
        assert upload_href in with_add.content.decode()


class TestTheRequestsFiche:
    @pytest.mark.django_db
    def test_shows_its_attached_documents(self, flight_request):
        _attach(flight_request, "Constancia SIGO")

        response = login_as("view_flightrequest", "view_document").get(
            reverse("flight-request-detail", args=[flight_request.pk])
        )

        assert "Constancia SIGO" in response.content.decode()

    @pytest.mark.django_db
    def test_hidden_without_view_document_permission(self, flight_request):
        response = login_as("view_flightrequest").get(
            reverse("flight-request-detail", args=[flight_request.pk])
        )

        assert response.context["documents"] is None


class TestTheUploadForm:
    @pytest.mark.django_db
    @pytest.mark.parametrize("model_name", ["geoplan", "flightrequest"])
    def test_offers_the_new_types_with_their_records(
        self, model_name, plan, flight_request
    ):
        """Que la ficha dibuje la sección no basta: el formulario tiene que
        aceptar el tipo y ofrecer el registro, que es donde estaba el bloqueo."""
        record = plan if model_name == "geoplan" else flight_request
        content_type = ContentType.objects.get_for_model(record)

        response = login_as("add_document").get(
            reverse("document-create"),
            {"entity_type": content_type.pk, "object_id": str(record.pk)},
        )

        form = response.context["form"]
        assert form.fields["entity_type"].queryset.filter(pk=content_type.pk).exists()
        assert str(record.pk) in [
            value for value, _label in form.fields["object_id"].choices
        ]
