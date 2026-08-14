"""LV-92: seeing a document without leaving the record you are reading.

`LV-85` put the viewer on the document's own page, so checking a folder before an
audit was N round trips: enter, look, go back, enter the next one. This wraps the
**same** preview response in the generic modal.

The interesting part is not the iframe, it is that wrapping a protected resource
must not become a way around its protection: the fragment answers with the same
`view_document` permission and the same tenant scope as the download it shows.
"""

from datetime import date

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.test import Client
from django.urls import reverse

from apps.compliance.models import Document, DocumentType
from apps.registry.models import Aircraft

TODAY = date(2026, 8, 14)


def _client(*codenames):
    user = User.objects.create_user(f"u-{'-'.join(codenames) or 'none'}", password="pw")
    if codenames:
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
    client = Client()
    assert client.login(username=user.username, password="pw")
    return client


@pytest.fixture
def aircraft(db):
    return Aircraft.objects.create(
        registration="RPA-92", type="RPA", model="M3", manufacturer="DJI"
    )


@pytest.fixture
def doc_type(db):
    return DocumentType.objects.create(
        name="Póliza", code="policy-92", requires_expiry=False
    )


def _document(aircraft, doc_type, file_path):
    return Document.objects.create(
        title="Póliza JAC",
        doc_type=doc_type,
        content_type=ContentType.objects.get_for_model(Aircraft),
        object_id=aircraft.pk,
        issue_date=TODAY,
        file_path=file_path,
    )


@pytest.mark.django_db
class TestTheFragment:
    def test_a_pdf_comes_back_as_a_viewer(self, aircraft, doc_type):
        document = _document(aircraft, doc_type, "policy/aircraft/x/policy.pdf")

        html = (
            _client("view_document")
            .get(reverse("document-preview-frame", args=[document.pk]))
            .content.decode()
        )

        assert "<iframe" in html
        assert reverse("document-preview", args=[document.pk]) in html

    def test_an_image_comes_back_as_an_image(self, aircraft, doc_type):
        document = _document(aircraft, doc_type, "policy/aircraft/x/scan.png")

        html = (
            _client("view_document")
            .get(reverse("document-preview-frame", args=[document.pk]))
            .content.decode()
        )

        assert "<img" in html
        assert "<iframe" not in html

    def test_a_type_that_is_never_shown_inline_offers_the_download(
        self, aircraft, doc_type
    ):
        """Not a broken frame: KML is XML and DOCX is a ZIP, so LV-85 keeps them
        as attachments on purpose. An empty viewer would read as a broken file."""
        document = _document(aircraft, doc_type, "plan/aircraft/x/area.kml")

        html = (
            _client("view_document")
            .get(reverse("document-preview-frame", args=[document.pk]))
            .content.decode()
        )

        assert "<iframe" not in html
        assert "<img" not in html
        assert reverse("document-download", args=[document.pk]) in html

    def test_it_always_offers_the_way_out_to_the_full_page(self, aircraft, doc_type):
        """Previous versions and Replace do not fit in a viewer."""
        document = _document(aircraft, doc_type, "policy/aircraft/x/policy.pdf")

        html = (
            _client("view_document")
            .get(reverse("document-preview-frame", args=[document.pk]))
            .content.decode()
        )

        assert reverse("document-detail", args=[document.pk]) in html


@pytest.mark.django_db
class TestItIsNotAWayAroundTheGuards:
    def test_without_view_permission_it_is_403(self, aircraft, doc_type):
        document = _document(aircraft, doc_type, "policy/aircraft/x/policy.pdf")

        response = _client().get(reverse("document-preview-frame", args=[document.pk]))

        assert response.status_code == 403

    def test_an_archived_document_is_404(self, aircraft, doc_type):
        document = _document(aircraft, doc_type, "policy/aircraft/x/policy.pdf")
        document.is_active = False
        document.save(update_fields=["is_active"])

        response = _client("view_document").get(
            reverse("document-preview-frame", args=[document.pk])
        )

        assert response.status_code == 404


@pytest.mark.django_db
def test_the_record_page_opens_it_over_the_list(aircraft, doc_type):
    """The button has to point at the fragment, or the feature is a dead link."""
    _document(aircraft, doc_type, "policy/aircraft/x/policy.pdf")

    html = (
        _client("view_document", "view_aircraft")
        .get(reverse("aircraft-detail", args=[aircraft.pk]))
        .content.decode()
    )

    assert 'hx-target="#modal-content"' in html
    assert "preview-frame" in html
