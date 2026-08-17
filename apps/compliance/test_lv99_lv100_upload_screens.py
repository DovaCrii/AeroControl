"""LV-99/LV-100: two dead ends on the document screens.

LV-99: "Cancel" on the upload form went to the general document list -- a screen
LV-40 deliberately took off the menu -- so cancelling left the person somewhere
they could not navigate back from, while *saving* landed on the record's own
file. The two answers to "where was I?" have to agree.

LV-100: the replace screen offered "Entity type" and "Related record" as
editable pickers, but `DocumentReplace.form_valid` forces both from the original
document. Changing them did nothing, silently -- a control that lies about what
it does is worse than no control.
"""

from datetime import date

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.core.testing import login_as
from apps.compliance.models import Document, DocumentType
from apps.registry.models import Aircraft, CostCenter

PDF_BYTES = b"%PDF-1.4\nfor tests\n"
TODAY = date(2026, 8, 14)


@pytest.fixture
def aircraft(db):
    return Aircraft.objects.create(
        registration="RPA-99", type="RPA", model="M3", manufacturer="DJI"
    )


@pytest.fixture
def doc_type(db):
    return DocumentType.objects.create(
        name="Póliza", code="policy-99", requires_expiry=False
    )


@pytest.fixture
def document(aircraft, doc_type):
    return Document.objects.create(
        title="Póliza",
        doc_type=doc_type,
        content_type=ContentType.objects.get_for_model(Aircraft),
        object_id=aircraft.pk,
        issue_date=TODAY,
        file_path="policy/aircraft/x/policy.pdf",
    )


@pytest.mark.django_db
class TestCancelGoesBackWhereSavingWould:
    def test_it_returns_to_the_record_the_upload_was_started_from(self, aircraft):
        content_type = ContentType.objects.get_for_model(Aircraft)

        html = (
            login_as("add_document")
            .get(
                reverse("document-create"),
                {"entity_type": content_type.pk, "object_id": str(aircraft.pk)},
            )
            .content.decode()
        )

        assert reverse("aircraft-detail", args=[aircraft.pk]) in html
        assert f'href="{reverse("document-list")}"' not in html

    def test_without_a_record_it_falls_back_to_the_company_repository(self):
        """Not the unlisted general list: somewhere with a way out."""
        html = login_as("add_document").get(reverse("document-create")).content.decode()

        assert reverse("company-documents") in html
        assert f'href="{reverse("document-list")}"' not in html

    def test_a_junk_record_in_the_url_does_not_break_the_page(self):
        """The parameters are untrusted -- they come from a URL."""
        response = login_as("add_document").get(
            reverse("document-create"),
            {"entity_type": "999999", "object_id": "not-a-uuid"},
        )

        assert response.status_code == 200
        assert reverse("company-documents") in response.content.decode()


@pytest.mark.django_db
class TestReplaceShowsTheRecordInsteadOfPretendingToOfferIt:
    def test_the_pickers_are_not_offered(self, document):
        html = (
            login_as("change_document")
            .get(reverse("document-replace", args=[document.pk]))
            .content.decode()
        )

        # The value still travels (hidden), but not as something to choose.
        assert 'id="document-object-field"' not in html
        assert '<select name="entity_type"' not in html

    def test_the_record_is_still_named_on_screen(self, document, aircraft):
        html = (
            login_as("change_document")
            .get(reverse("document-replace", args=[document.pk]))
            .content.decode()
        )

        assert aircraft.registration in html

    def test_replacing_still_works_with_the_fields_hidden(self, document, aircraft):
        """The whole risk of hiding them: the form must still validate."""
        client = login_as("change_document", "view_document", "add_document")
        content_type = ContentType.objects.get_for_model(Aircraft)

        response = client.post(
            reverse("document-replace", args=[document.pk]),
            {
                "title": "Póliza nueva",
                "doc_type": str(document.doc_type_id),
                "entity_type": str(content_type.pk),
                "object_id": str(aircraft.pk),
                "file": SimpleUploadedFile("nueva.pdf", PDF_BYTES),
                "issue_date": TODAY.isoformat(),
                "notes": "",
            },
        )

        assert response.status_code == 302
        document.refresh_from_db()
        assert document.is_current_version is False
        assert Document.objects.filter(
            title="Póliza nueva", is_current_version=True
        ).exists()

    def test_a_tampered_record_cannot_move_the_document(self, document, aircraft):
        """Hidden is not a guard -- the view forcing the values is."""
        other = CostCenter.objects.create(code="CC99", name="Otro")
        client = login_as("change_document", "view_document", "add_document")

        client.post(
            reverse("document-replace", args=[document.pk]),
            {
                "title": "Póliza movida",
                "doc_type": str(document.doc_type_id),
                "entity_type": str(ContentType.objects.get_for_model(CostCenter).pk),
                "object_id": str(other.pk),
                "file": SimpleUploadedFile("nueva.pdf", PDF_BYTES),
                "issue_date": TODAY.isoformat(),
                "notes": "",
            },
        )

        moved = Document.objects.filter(title="Póliza movida").first()
        assert moved is not None
        assert moved.object_id == aircraft.pk
        assert moved.content_type == ContentType.objects.get_for_model(Aircraft)
