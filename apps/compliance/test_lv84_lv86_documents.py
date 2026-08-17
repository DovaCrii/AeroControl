"""LV-84/LV-85/LV-86: the documents list, the in-page preview and batch upload.

The security half is the interesting one. A preview is the *same bytes* as the
download, so it obeys the same permission and tenant scope -- a viewer that
skipped them would be the F-05 finding in a new wrapper -- and it is served
inline only for types that cannot be talked into executing in this app's origin.
"""

from datetime import date, timedelta

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.core.testing import login_as
from apps.compliance.models import Document, DocumentType
from apps.registry.models import Aircraft

PDF_BYTES = b"%PDF-1.4\n%fake pdf for tests\n"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 32
TODAY = date(2026, 8, 13)


@pytest.fixture
def aircraft(db):
    return Aircraft.objects.create(
        registration="CC-DOC", type="RPA", model="M3", manufacturer="DJI"
    )


@pytest.fixture
def doc_type(db):
    # requires_expiry defaults to True; the batch's own enforcement of that rule
    # has its own test below.
    return DocumentType.objects.create(
        name="Póliza", code="policy", requires_expiry=False
    )


def _csp(response):
    """The policy, whichever of the two headers is in force."""
    return response.get(
        "Content-Security-Policy",
        response.get("Content-Security-Policy-Report-Only", ""),
    )


def _upload(name="policy.pdf", content=PDF_BYTES):
    return SimpleUploadedFile(name, content, content_type="application/pdf")


def _document(aircraft, doc_type, *, name="policy.pdf", content=PDF_BYTES, **kwargs):
    """A document with its bytes actually in storage, so the views can open it."""
    from apps.compliance.views import save_uploaded_file

    document = Document.objects.create(
        title=kwargs.pop("title", "Póliza JAC"),
        doc_type=doc_type,
        content_type=ContentType.objects.get_for_model(Aircraft),
        object_id=aircraft.pk,
        issue_date=kwargs.pop("issue_date", TODAY),
        file_path="",
        **kwargs,
    )
    save_uploaded_file(document, SimpleUploadedFile(name, content))
    return document


@pytest.mark.django_db
class TestPreview:
    def test_a_pdf_is_served_inline(self, aircraft, doc_type):
        document = _document(aircraft, doc_type)

        response = login_as("view_document").get(
            reverse("document-preview", args=[document.pk])
        )

        assert response.status_code == 200
        assert response["Content-Type"] == "application/pdf"
        assert response["Content-Disposition"].startswith("inline")

    def test_an_image_is_served_inline(self, aircraft, doc_type):
        document = _document(aircraft, doc_type, name="scan.png", content=PNG_BYTES)

        response = login_as("view_document").get(
            reverse("document-preview", args=[document.pk])
        )

        assert response["Content-Type"] == "image/png"

    def test_the_type_cannot_be_sniffed_into_something_else(self, aircraft, doc_type):
        """This response hands a user-supplied file to the browser with
        `Content-Disposition: inline`, so the type it is served as has to be the
        type it is treated as."""
        document = _document(aircraft, doc_type)

        response = login_as("view_document").get(
            reverse("document-preview", args=[document.pk])
        )

        assert response["X-Content-Type-Options"] == "nosniff"

    def test_only_this_response_may_be_framed_and_only_by_us(self, aircraft, doc_type):
        """The fiche embeds the file in an <iframe> of its own, so the file has
        to allow same-origin framing -- while every other page keeps refusing to
        be framed at all, which is the clickjacking protection. Both headers,
        because either one alone still blocks the load."""
        document = _document(aircraft, doc_type)
        client = login_as("view_document")

        preview = client.get(reverse("document-preview", args=[document.pk]))
        page = client.get(reverse("document-detail", args=[document.pk]))

        assert preview["X-Frame-Options"] == "SAMEORIGIN"
        assert "frame-ancestors 'self'" in _csp(preview)
        assert page["X-Frame-Options"] == "DENY"
        assert "frame-ancestors 'none'" in _csp(page)

    @pytest.mark.parametrize(
        ("name", "content"),
        [("area.kml", b"<?xml version='1.0'?><kml/>"), ("report.docx", b"PK\x03\x04x")],
    )
    def test_anything_outside_the_allowlist_falls_back_to_the_download(
        self, aircraft, doc_type, name, content
    ):
        """KML is XML and DOCX is a ZIP: neither is refused, but neither is
        rendered in this app's origin either."""
        document = _document(aircraft, doc_type, name=name, content=content)

        response = login_as("view_document").get(
            reverse("document-preview", args=[document.pk])
        )

        assert response.status_code == 302
        assert response["Location"] == reverse("document-download", args=[document.pk])

    def test_it_requires_view_document(self, aircraft, doc_type):
        document = _document(aircraft, doc_type)

        response = login_as().get(reverse("document-preview", args=[document.pk]))

        assert response.status_code == 403

    def test_a_missing_file_is_a_404_not_a_500(self, aircraft, doc_type):
        document = _document(aircraft, doc_type)
        Document.objects.filter(pk=document.pk).update(file_path="gone/nothing.pdf")

        response = login_as("view_document").get(
            reverse("document-preview", args=[document.pk])
        )

        assert response.status_code == 404

    def test_the_fiche_embeds_a_viewer_only_for_previewable_types(
        self, aircraft, doc_type
    ):
        pdf = _document(aircraft, doc_type)
        kml = _document(aircraft, doc_type, name="area.kml", content=b"<kml/>")
        client = login_as("view_document")

        assert (
            client.get(reverse("document-detail", args=[pdf.pk])).context[
                "preview_kind"
            ]
            == "pdf"
        )
        assert (
            client.get(reverse("document-detail", args=[kml.pk])).context[
                "preview_kind"
            ]
            is None
        )


@pytest.mark.django_db
class TestTheList:
    def test_each_row_offers_view_and_download(self, aircraft, doc_type):
        document = _document(aircraft, doc_type)

        content = (
            login_as("view_aircraft", "view_document")
            .get(reverse("aircraft-detail", args=[aircraft.pk]))
            .content.decode()
        )

        assert reverse("document-preview", args=[document.pk]) in content
        assert reverse("document-download", args=[document.pk]) in content

    def test_an_expired_document_is_flagged(self, aircraft, doc_type):
        from django.utils import timezone

        _document(
            aircraft, doc_type, expiry_date=timezone.localdate() - timedelta(days=1)
        )

        content = (
            login_as("view_aircraft", "view_document")
            .get(reverse("aircraft-detail", args=[aircraft.pk]))
            .content.decode()
        )

        assert "Vencido" in content or "Expired" in content

    def test_a_document_without_an_expiry_is_not_expired(self, aircraft, doc_type):
        """A procedure or a manual does not lapse; a null is "does not apply"."""
        assert _document(aircraft, doc_type, expiry_date=None).is_expired is False


@pytest.mark.django_db
class TestBulkUpload:
    def _url(self):
        return reverse("document-bulk-upload")

    def _payload(self, aircraft, doc_type, files):
        return {
            "entity_type": ContentType.objects.get_for_model(Aircraft).pk,
            "object_id": str(aircraft.pk),
            "doc_type": doc_type.pk,
            "issue_date": "2026-08-04",
            "files": files,
        }

    def test_several_files_become_several_documents(self, aircraft, doc_type):
        response = login_as("add_document", "view_document").post(
            self._url(),
            self._payload(
                aircraft,
                doc_type,
                [_upload("cert-136.pdf"), _upload("cert-137.pdf")],
            ),
        )

        assert response.status_code == 302, response.context["form"].errors
        assert Document.objects.count() == 2
        assert {
            document.file_path.endswith(".pdf") for document in Document.objects.all()
        } == {True}

    def test_each_document_keeps_its_own_file_name_in_the_title(
        self, aircraft, doc_type
    ):
        """Twelve documents all called "Póliza · CC-DOC · 2026-08-04" would be
        worse than none."""
        login_as("add_document", "view_document").post(
            self._url(),
            self._payload(
                aircraft, doc_type, [_upload("cert-136.pdf"), _upload("cert-137.pdf")]
            ),
        )

        titles = set(Document.objects.values_list("title", flat=True))
        assert len(titles) == 2
        assert any("cert-136" in title for title in titles)

    def test_a_rejected_file_names_itself_and_nothing_is_saved(
        self, aircraft, doc_type
    ):
        """The batch fails as a whole rather than half-loading, and the message
        says *which* file -- a batch that silently drops one is worse than one
        that refuses."""
        response = login_as("add_document", "view_document").post(
            self._url(),
            self._payload(
                aircraft,
                doc_type,
                [_upload("good.pdf"), _upload("bad.exe", b"MZ\x90\x00")],
            ),
        )

        assert response.status_code == 200
        assert not Document.objects.exists()
        assert "bad.exe" in response.content.decode()

    def test_a_file_whose_bytes_contradict_its_name_is_refused(
        self, aircraft, doc_type
    ):
        response = login_as("add_document", "view_document").post(
            self._url(),
            self._payload(
                aircraft, doc_type, [_upload("renamed.pdf", b"MZ\x90\x00not a pdf")]
            ),
        )

        assert response.status_code == 200
        assert not Document.objects.exists()

    def test_it_requires_add_document(self, aircraft, doc_type):
        response = login_as("view_document").post(
            self._url(), self._payload(aircraft, doc_type, [_upload()])
        )

        assert response.status_code == 403
        assert not Document.objects.exists()

    def test_an_expiry_required_type_is_enforced_for_the_whole_batch(self, aircraft):
        doc_type = DocumentType.objects.create(
            name="Seguro", code="ins", requires_expiry=True
        )

        response = login_as("add_document", "view_document").post(
            self._url(), self._payload(aircraft, doc_type, [_upload()])
        )

        assert response.status_code == 200
        assert not Document.objects.exists()

    def test_cancel_points_at_our_own_page_not_at_a_header(self, aircraft, doc_type):
        """`HTTP_REFERER` is untrusted input; a link built from it puts somebody
        else's URL inside our page."""
        url = (
            f"{self._url()}?entity_type="
            f"{ContentType.objects.get_for_model(Aircraft).pk}&object_id={aircraft.pk}"
        )

        response = login_as("add_document", "view_document").get(
            url, HTTP_REFERER="https://evil.example/phish"
        )

        assert response.context["cancel_url"].startswith(
            reverse("aircraft-detail", args=[aircraft.pk])
        )
        assert "evil.example" not in response.content.decode()

    def test_the_dates_apply_to_every_file(self, aircraft, doc_type):
        payload = self._payload(
            aircraft, doc_type, [_upload("a.pdf"), _upload("b.pdf")]
        )
        payload["expiry_date"] = "2027-08-04"

        login_as("add_document", "view_document").post(self._url(), payload)

        assert set(Document.objects.values_list("expiry_date", flat=True)) == {
            date(2027, 8, 4)
        }
