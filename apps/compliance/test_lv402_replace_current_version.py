"""LV-402: reemplazar un documento deja exactamente una versión vigente.

`DocumentReplace` no exigía `is_current_version=True`: reemplazar una versión ya
reemplazada (pestaña vieja, doble clic) dejaba dos vigentes, y el documento nuevo
no heredaba la empresa del reemplazado. Datos ficticios.
"""

from datetime import date

import pytest
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from apps.compliance.models import Document, DocumentType
from apps.core.models import OperationalTenant
from apps.registry.models import Aircraft, CostCenter


@pytest.fixture
def setup(db, settings, tmp_path):
    settings.DOCUMENTS_ROOT = str(tmp_path)
    center = CostCenter.objects.create(code="OPS", name="Operations")
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Fixed",
        model="A",
        manufacturer="Maker",
        cost_center=center,
    )
    doc_type = DocumentType.objects.create(
        code="cert402", name="Certificate", requires_expiry=False
    )
    other = OperationalTenant.objects.create(name="Otra", slug="otra-402")
    old = Document.objects.create(
        title="Cert",
        doc_type=doc_type,
        content_type=ContentType.objects.get_for_model(Aircraft),
        object_id=aircraft.pk,
        file_path="cert/aircraft/old.pdf",
        issue_date=date(2026, 1, 1),
        tenant=other,
    )
    User.objects.create_superuser("admin402", "a402@test.com", "password")
    client = Client()
    assert client.login(username="admin402", password="password")
    return client, old, aircraft, doc_type, other


def _post(client, old, aircraft, doc_type):
    return client.post(
        reverse("document-replace", args=[old.pk]),
        {
            "title": "Cert",
            "doc_type": doc_type.pk,
            "entity_type": ContentType.objects.get_for_model(Aircraft).pk,
            "object_id": str(aircraft.pk),
            "issue_date": date(2026, 6, 1),
            "file": SimpleUploadedFile(
                "new.pdf", b"%PDF-1.4\n%%EOF\n", content_type="application/pdf"
            ),
        },
    )


@pytest.mark.django_db
def test_replacing_a_non_current_version_is_404(setup):
    client, old, aircraft, doc_type, _ = setup
    Document.objects.filter(pk=old.pk).update(is_current_version=False)

    assert client.get(reverse("document-replace", args=[old.pk])).status_code == 404
    assert _post(client, old, aircraft, doc_type).status_code == 404
    assert Document.objects.filter(is_current_version=True).count() == 0


@pytest.mark.django_db
def test_two_replacements_in_a_row_leave_exactly_one_current(setup):
    client, old, aircraft, doc_type, _ = setup

    assert _post(client, old, aircraft, doc_type).status_code == 302
    # Stale tab: the old page is submitted again.
    assert _post(client, old, aircraft, doc_type).status_code == 404

    assert Document.objects.filter(is_current_version=True).count() == 1
    assert Document.objects.count() == 2


@pytest.mark.django_db
def test_losing_the_race_cancels_without_creating_or_orphaning(setup, monkeypatch):
    """The page loaded while current, then another request replaced it first."""
    client, old, aircraft, doc_type, _ = setup
    from apps.compliance import views

    # Simulate the other request landing between dispatch and form_valid.
    original_form_valid = views.DocumentReplace.form_valid

    def form_valid(self, form):
        Document.objects.filter(pk=self.document.pk).update(is_current_version=False)
        return original_form_valid(self, form)

    monkeypatch.setattr(views.DocumentReplace, "form_valid", form_valid)

    response = _post(client, old, aircraft, doc_type)

    assert response.status_code == 302
    assert Document.objects.count() == 1
    assert Document.objects.filter(is_current_version=True).count() == 0


@pytest.mark.django_db
def test_the_new_document_inherits_the_tenant(setup):
    client, old, aircraft, doc_type, other = setup

    assert _post(client, old, aircraft, doc_type).status_code == 302

    new = Document.objects.get(is_current_version=True)
    assert new.tenant_id == other.pk
