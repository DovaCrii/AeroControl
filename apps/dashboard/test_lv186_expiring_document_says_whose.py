"""LV-186: el vencimiento de un documento dice de qué cuelga.

Pedido del usuario mirando los vencimientos del panel: *"mencionar el CC del
permiso, en este caso el que está por vencer, a cuál es"*. La fila decía
**"Documento · Carta Permiso"** y nada más — y hay una carta por permiso, así que
para saber a cuál se refiere había que abrirla. Eso es exactamente lo que una
lista de vencimientos existe para evitar: se mira para decidir qué atender
primero, no para empezar a navegar.

**Es el único de los cinco orígenes con este problema**, y por eso el arreglo va
sólo ahí: en un seguro la etiqueta es la matrícula, en una credencial el nombre
de la persona. El documento es el único que cuelga de otra cosa y se nombra por
su tipo.

Con el sujeto a la vista, además, el chip de faena deja de ser el único camino
para ubicarlo — que era el pedido literal: un documento de empresa no tiene
faena, y aun así ahora se sabe de qué habla.

Las propiedades que estos tests sostienen:

- **Una consulta por tipo de sujeto, ninguna por fila.** Esto se dibuja en el
  panel, que se abre en cada inicio de sesión.
- **Sin sujeto no se inventa nada**: un documento de empresa cuelga del tenant,
  no de un registro, y ahí la fila queda como estaba.
"""

from datetime import timedelta

import pytest
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import timezone

from apps.compliance.models import Document, DocumentType
from apps.compliance.reports import document_subjects
from apps.operations.models import FlightPermission
from apps.registry.models import Aircraft, CostCenter

TODAY = timezone.localdate()


@pytest.fixture
def permit(db):
    center = CostCenter.objects.create(code="CC738", name="MLP")
    return FlightPermission.objects.create(
        internal_folio="JEJ-2026-004",
        cost_center=center,
        purpose="survey",
        valid_from=TODAY,
        valid_until=TODAY + timedelta(days=90),
        location="Quebrada km 13",
        area_type="dan_91",
    )


def _document(subject, title, days):
    return Document.objects.create(
        title=title,
        doc_type=DocumentType.objects.get_or_create(
            code="permit-letter", defaults={"name": "Carta Permiso"}
        )[0],
        content_type=ContentType.objects.get_for_model(type(subject)),
        object_id=subject.pk,
        issue_date=TODAY - timedelta(days=1),
        expiry_date=TODAY + timedelta(days=days),
        # El panel sólo lista la versión vigente de cada documento: una versión
        # superada no vence, la reemplazó otra.
        is_current_version=True,
    )


@pytest.mark.django_db
def test_it_says_which_permit_the_letter_belongs_to(permit):
    document = _document(permit, "Carta Permiso", 30)

    labels = document_subjects([document])

    assert labels[document.pk] == str(permit)


@pytest.mark.django_db
def test_a_company_document_has_no_subject_and_that_is_honest(permit):
    """Cuelga del tenant, no de un registro: inventarle uno sería peor."""
    document = Document.objects.create(
        title="Manual de operaciones",
        doc_type=DocumentType.objects.create(code="manual", name="Manual"),
        content_type=ContentType.objects.get_for_model(CostCenter),
        object_id="00000000-0000-0000-0000-000000000000",
        issue_date=TODAY - timedelta(days=1),
        expiry_date=TODAY + timedelta(days=30),
    )

    assert document_subjects([document]) == {}


@pytest.mark.django_db
def test_it_does_not_query_once_per_row(permit, django_assert_num_queries):
    """El panel se abre en cada inicio de sesión."""
    aircraft = Aircraft.objects.create(registration="RPA-4401", serial_number="S1")
    documents = [
        _document(permit, "Carta Permiso", 10),
        _document(permit, "Otra carta", 20),
        _document(aircraft, "Seguro", 25),
    ]

    # Dos tipos de sujeto presentes: dos consultas, no tres.
    with django_assert_num_queries(2):
        labels = document_subjects(documents)

    assert len(labels) == 3


@pytest.mark.django_db
def test_the_subject_reaches_the_drawn_row(permit, client, django_user_model):
    """De punta a punta: el sujeto llega a la fila **dibujada**, no sólo al
    contexto. Que `document_subjects` resuelva el sujeto no sirve de nada si la
    plantilla no lo imprime.

    **La aeronave no es decoración del fixture.** El panel envuelve todo su
    contenido —vencimientos incluidos— en un `{% if %}` de primera pantalla que
    se cumple cuando no hay aeronaves activas ni operadores ni alertas: con la
    base vacía se dibuja la tarjeta "Comienza tu operación" y esta lista no
    existe en el HTML. Ese guard **esconde vencimientos reales cuando se filtra
    por una faena sin flota ni padrón** — ver `LV-187`; acá se le da a la
    operación lo mínimo para que el panel sea el panel.
    """
    Aircraft.objects.create(
        registration="RPA-4401", serial_number="S1", status="active"
    )
    _document(permit, "Carta Permiso", 10)
    django_user_model.objects.create_superuser("admin", "a@test.com", "password")
    assert client.login(username="admin", password="password")

    response = client.get(reverse("dashboard"))
    html = response.content.decode()

    assert [item["label"] for item in response.context["expirations"]] == [
        "Carta Permiso"
    ]
    # La fila dice de qué cuelga: "Documento · Carta Permiso · JEJ-2026-004".
    assert f"· {permit.internal_folio}" in html
