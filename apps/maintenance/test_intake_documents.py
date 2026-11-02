"""LV-388: los documentos del ingreso cuelgan de la aeronave, no de la mantención.

Datos ficticios solamente; el almacenamiento apunta a un `tmp_path`.
"""

import importlib
from datetime import date

import pytest
from django.apps import apps as global_apps
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from apps.compliance.models import Document, DocumentType
from apps.core.models import OperationalTenant
from apps.core.testing import login_as
from apps.maintenance.models import MaintenanceRecord, WorkshopIntake
from apps.maintenance.test_intake_views import (
    aircraft,
    operator_client,
    reception_pdf,
    register,
)

pytestmark = pytest.mark.django_db

migration = importlib.import_module(
    "apps.maintenance.migrations.0012_move_intake_documents_to_aircraft"
)


@pytest.fixture(autouse=True)
def documents_root(settings, tmp_path):
    settings.DOCUMENTS_ROOT = tmp_path
    return tmp_path


def _document(subject, title="Doc", tenant=None):
    doc_type, _created = DocumentType.objects.get_or_create(
        code="lv388-type", defaults={"name": "Tipo"}
    )
    extra = {"tenant": tenant} if tenant else {}
    return Document.objects.create(
        content_type=ContentType.objects.get_for_model(subject),
        object_id=subject.pk,
        doc_type=doc_type,
        title=title,
        issue_date=date(2026, 1, 1),
        file_path="x",
        **extra,
    )


def _legacy_intake(plane, order, tenant=None):
    """Un ingreso al estilo antiguo: el documento cuelga de la mantención."""
    record = MaintenanceRecord.objects.create(
        aircraft=plane, maintenance_type="unscheduled", description="x"
    )
    document = _document(record, f"Ingreso {order}", tenant=tenant)
    WorkshopIntake.objects.create(
        record=record,
        workshop_name="Geocom",
        workshop_order=order,
        source_document=document,
    )
    return record, document


class TestNewIntakeHangsFromTheAircraft:
    def test_the_document_is_on_the_aircraft_and_the_record_still_points_at_it(self):
        plane = aircraft()
        client = operator_client()
        response = register(client, reception_pdf(), plane)
        assert response.status_code == 302

        document = Document.objects.get()
        assert document.content_type == ContentType.objects.get_for_model(plane)
        assert document.object_id == plane.pk
        assert document.tenant_id == plane.tenant_id
        intake = WorkshopIntake.objects.get()
        assert intake.source_document == document

    def test_the_aircraft_fiche_lists_it(self):
        plane = aircraft()
        register(operator_client(), reception_pdf(), plane)
        viewer = login_as("view_aircraft", "view_document")
        body = viewer.get(reverse("aircraft-detail", args=[plane.pk])).content.decode()
        assert Document.objects.get().title in body

    def test_the_maintenance_fiche_still_shows_the_intake_document(self):
        plane = aircraft()
        register(operator_client(), reception_pdf(), plane)
        record = MaintenanceRecord.objects.get()
        viewer = login_as("view_maintenancerecord", "view_document")
        response = viewer.get(reverse("maintenance-detail", args=[record.pk]))
        assert Document.objects.get().title in response.content.decode()

    def test_another_aircrafts_intake_document_is_not_listed_on_this_record(self):
        mine = aircraft("TST-1", "TESTSERIAL00000003")
        other = aircraft("TST-2", "TESTSERIAL00000004")
        _record, _doc = _legacy_intake(mine, "TEST-1")
        _other_record, other_doc = _legacy_intake(other, "TEST-2")
        record = MaintenanceRecord.objects.get(aircraft=mine)
        viewer = login_as("view_maintenancerecord", "view_document")
        body = viewer.get(
            reverse("maintenance-detail", args=[record.pk])
        ).content.decode()
        assert other_doc.title not in body


class TestMigration:
    def _run(self):
        migration.move_intake_documents_to_aircraft(global_apps, None)

    def test_it_moves_only_the_intake_documents_to_the_aircraft(self):
        plane = aircraft()
        record, intake_doc = _legacy_intake(plane, "TEST-1")
        # Un documento cualquiera de la misma mantención: no es del ingreso.
        stray = _document(record, "Informe aparte")
        # Uno ya en la aeronave: no se toca.
        on_aircraft = _document(plane, "Seguro")

        self._run()

        aircraft_ct = ContentType.objects.get_for_model(plane)
        record_ct = ContentType.objects.get_for_model(record)
        for doc in (intake_doc, on_aircraft):
            doc.refresh_from_db()
            assert (doc.content_type, doc.object_id) == (aircraft_ct, plane.pk)
        stray.refresh_from_db()
        assert (stray.content_type, stray.object_id) == (record_ct, record.pk)

    def test_it_is_idempotent(self):
        plane = aircraft()
        _record, intake_doc = _legacy_intake(plane, "TEST-1")
        self._run()
        self._run()
        intake_doc.refresh_from_db()
        assert intake_doc.object_id == plane.pk
        assert Document.objects.count() == 1

    def test_the_quote_document_moves_too(self):
        plane = aircraft()
        record, source = _legacy_intake(plane, "TEST-1")
        quote = _document(record, "Cotizacion")
        intake = WorkshopIntake.objects.get(record=record)
        intake.quote_document = quote
        intake.save()
        self._run()
        quote.refresh_from_db()
        assert quote.object_id == plane.pk

    def test_each_document_goes_to_its_own_aircraft_and_tenant(self):
        a = OperationalTenant.objects.create(name="A", slug="a")
        b = OperationalTenant.objects.create(name="B", slug="b")
        plane_a = aircraft("TST-1", "TESTSERIAL00000003", tenant=a)
        plane_b = aircraft("TST-2", "TESTSERIAL00000004", tenant=b)
        # El documento nace con otra empresa: la migración la alinea con la aeronave.
        _record_a, doc_a = _legacy_intake(plane_a, "TEST-1", tenant=b)
        _record_b, doc_b = _legacy_intake(plane_b, "TEST-2", tenant=b)
        self._run()
        doc_a.refresh_from_db()
        doc_b.refresh_from_db()
        assert (doc_a.object_id, doc_a.tenant_id) == (plane_a.pk, a.pk)
        assert (doc_b.object_id, doc_b.tenant_id) == (plane_b.pk, b.pk)

    def test_an_intake_without_documents_is_skipped(self):
        plane = aircraft()
        record = MaintenanceRecord.objects.create(
            aircraft=plane, maintenance_type="unscheduled", description="x"
        )
        WorkshopIntake.objects.create(
            record=record, workshop_name="Geocom", workshop_order="TEST-9"
        )
        self._run()  # no falla
        assert not Document.objects.exists()
