"""LV-379: la ficha de la mantencion lista los documentos que se le cuelgan.

`("maintenance", "maintenancerecord")` esta en `DOCUMENTABLE_MODELS`, asi que un
documento se puede subir contra un registro de mantencion, pero la ficha no
llamaba a `attached_documents_context` ni incluia la seccion compartida: el
archivo quedaba guardado y nadie lo veia desde el registro.
"""

from datetime import date

import pytest
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from apps.compliance.models import Document, DocumentType
from apps.core.models import OperationalTenant
from apps.core.testing import login_as
from apps.maintenance.models import MaintenanceRecord
from apps.registry.models import Aircraft


def _record(registration="CC-AAA", tenant=None):
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


def _attach(record, title, **kwargs):
    doc_type, _ = DocumentType.objects.get_or_create(
        code="maint-report", defaults={"name": "Informe"}
    )
    return Document.objects.create(
        content_type=ContentType.objects.get_for_model(record),
        object_id=record.pk,
        doc_type=doc_type,
        title=title,
        issue_date=date(2026, 8, 24),
        file_path="x",
        **kwargs,
    )


def _get(client, record):
    return client.get(reverse("maintenance-detail", args=[record.pk]))


@pytest.mark.django_db
class TestMaintenanceFicheDocuments:
    def test_lists_active_documents_of_this_record_only(self):
        record = _record()
        other = _record(registration="CC-BBB")
        _attach(record, "Informe del taller")
        _attach(other, "Informe de otra mantencion")
        _attach(record, "Informe archivado", is_active=False)

        response = _get(login_as("view_maintenancerecord", "view_document"), record)
        body = response.content.decode()

        assert "Informe del taller" in body
        assert "Informe de otra mantencion" not in body
        assert "Informe archivado" not in body

    def test_section_hidden_without_view_document(self):
        record = _record()
        _attach(record, "Informe reservado")

        response = _get(login_as("view_maintenancerecord"), record)

        assert response.context["documents"] is None
        assert "Informe reservado" not in response.content.decode()

    def test_other_tenant_document_does_not_appear(self):
        a = OperationalTenant.objects.create(name="A", slug="a")
        b = OperationalTenant.objects.create(name="B", slug="b")
        mine = _record(registration="CC-AAA", tenant=a)
        theirs = _record(registration="CC-BBB", tenant=b)
        _attach(mine, "Informe propio")
        _attach(theirs, "Informe de la otra empresa")

        client = login_as("view_maintenancerecord", "view_document", member_of=a)

        body = _get(client, mine).content.decode()
        assert "Informe propio" in body
        assert "Informe de la otra empresa" not in body
        # Y la ficha ajena ni siquiera abre: su nombre no se filtra.
        denied = _get(client, theirs)
        assert denied.status_code == 404
        assert "Informe de la otra empresa" not in denied.content.decode()

    def test_fiche_still_403_without_view_maintenancerecord(self):
        record = _record()
        _attach(record, "Informe del taller")

        response = _get(login_as("view_document"), record)

        assert response.status_code == 403
