"""R4.7: Operator.credential_expiry is a date typed in from the DGAC capture
(LV-29) -- it says nothing about whether the licence PDF itself was ever
uploaded. The operator list showed a clean vigencia badge either way, with no
signal that "information incomplete" actually meant a missing document."""

from datetime import date, timedelta

import pytest
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.compliance.models import Document, DocumentType
from apps.registry.models import Operator


@pytest.fixture
def admin_client(db):
    User.objects.create_superuser("admin", "admin@test.com", "password")
    client = Client()
    assert client.login(username="admin", password="password")
    return client


def _attach_credential_pdf(operator, **overrides):
    doc_type, _ = DocumentType.objects.get_or_create(
        code="dgac-credential", defaults={"name": "Credencial DGAC"}
    )
    defaults = {
        "title": "Credencial DGAC",
        "doc_type": doc_type,
        "content_type": ContentType.objects.get_for_model(Operator),
        "object_id": operator.pk,
        "file_path": "cred.pdf",
        "issue_date": date(2026, 1, 1),
    }
    defaults.update(overrides)
    return Document.objects.create(**defaults)


@pytest.mark.django_db
def test_operator_with_a_date_but_no_pdf_shows_the_missing_flag(admin_client):
    Operator.objects.create(
        employee_id="OP-1",
        full_name="Pilot One",
        credential_expiry=timezone.localdate() + timedelta(days=30),
    )

    response = admin_client.get(reverse("operator-list"))

    assert response.status_code == 200
    row = list(response.context["objects"])[0]
    assert row.has_credential_pdf is False
    # Assert on the same translated string the template resolves, not the
    # English literal -- this runs under LANGUAGE_CODE="es" at runtime.
    assert _("No PDF") in response.content.decode()


@pytest.mark.django_db
def test_operator_with_the_pdf_on_file_shows_no_missing_flag(admin_client):
    operator = Operator.objects.create(
        employee_id="OP-1",
        full_name="Pilot One",
        credential_expiry=timezone.localdate() + timedelta(days=30),
    )
    _attach_credential_pdf(operator)

    response = admin_client.get(reverse("operator-list"))

    row = list(response.context["objects"])[0]
    assert row.has_credential_pdf is True
    assert "No PDF" not in response.content.decode()


@pytest.mark.django_db
def test_a_superseded_pdf_no_longer_counts(admin_client):
    """is_current_version=False (a newer copy replaced it) must not count as
    having the document on file -- same rule the rest of the app uses."""
    operator = Operator.objects.create(employee_id="OP-1", full_name="Pilot One")
    _attach_credential_pdf(operator, is_current_version=False)

    response = admin_client.get(reverse("operator-list"))

    row = list(response.context["objects"])[0]
    assert row.has_credential_pdf is False


@pytest.mark.django_db
def test_a_pdf_attached_to_a_different_document_type_does_not_count(admin_client):
    operator = Operator.objects.create(employee_id="OP-1", full_name="Pilot One")
    other_type, _ = DocumentType.objects.get_or_create(
        code="medical-cert", defaults={"name": "Certificado médico"}
    )
    Document.objects.create(
        title="Certificado médico",
        doc_type=other_type,
        content_type=ContentType.objects.get_for_model(Operator),
        object_id=operator.pk,
        file_path="med.pdf",
        issue_date=date(2026, 1, 1),
    )

    response = admin_client.get(reverse("operator-list"))

    row = list(response.context["objects"])[0]
    assert row.has_credential_pdf is False
