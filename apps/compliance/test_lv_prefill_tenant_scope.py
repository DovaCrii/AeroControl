"""The upload form's query-string prefill respects the user's company and the type catalog.

Two defects, both reachable by editing the URL of `document-create`:

- `object_id` of a record from **another company** prefilled the subject and the
  dates the record holds, so the form leaked data the user cannot see;
- an **archived** document type in `doc_type` stayed selectable, because the URL
  value was treated as "the type the document already carries".

Fictional data.
"""

import pytest
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from apps.compliance.models import Document, DocumentType
from apps.compliance.test_lv372_tenant_scope import world  # noqa: F401
from apps.core.testing import login_as
from apps.operations.models import FlightPermission


def _client(world, *codenames, tenant="a"):  # noqa: F811
    return login_as(*codenames, member_of=world[tenant]["tenant"])


def _get(client, url_name="document-create", pk=None, **params):
    url = reverse(url_name, kwargs={"pk": pk} if pk else None)
    response = client.get(url, params)
    assert response.status_code == 200
    return response


def _permit_params(permit):
    return {
        "entity_type": ContentType.objects.get_for_model(FlightPermission).pk,
        "object_id": str(permit.pk),
    }


@pytest.mark.django_db
class TestSubjectIsScopedToTheUsersCompany:
    def test_a_record_of_another_company_prefills_nothing(self, world):  # noqa: F811
        client = _client(world, "add_document", "view_document")

        form = _get(client, **_permit_params(world["b"]["permit"])).context["form"]

        for key in ("entity_type", "object_id", "issue_date", "expiry_date"):
            assert key not in form.initial

    def test_the_bulk_form_ignores_it_too(self, world):  # noqa: F811
        client = _client(world, "add_document", "view_document")

        form = _get(
            client, "document-bulk-upload", **_permit_params(world["b"]["permit"])
        ).context["form"]

        assert "entity_type" not in form.initial
        assert "object_id" not in form.initial

    def test_a_record_of_the_own_company_still_prefills(self, world):  # noqa: F811
        client = _client(world, "add_document", "view_document")
        permit = world["a"]["permit"]

        form = _get(client, **_permit_params(permit)).context["form"]

        assert str(form.initial["object_id"]) == str(permit.pk)
        assert form.initial["issue_date"] == permit.valid_from
        assert form.initial["expiry_date"] == permit.valid_until

    def test_the_bulk_form_keeps_an_own_record(self, world):  # noqa: F811
        client = _client(world, "add_document", "view_document")
        permit = world["a"]["permit"]

        form = _get(client, "document-bulk-upload", **_permit_params(permit)).context[
            "form"
        ]

        assert str(form.initial["object_id"]) == str(permit.pk)

    def test_a_malformed_object_id_is_ignored_not_a_500(self, world):  # noqa: F811
        client = _client(world, "add_document", "view_document")
        params = _permit_params(world["a"]["permit"]) | {"object_id": "not-a-uuid"}

        form = _get(client, **params).context["form"]

        assert "object_id" not in form.initial


@pytest.mark.django_db
class TestArchivedTypeInTheUrl:
    def test_an_archived_type_is_neither_selected_nor_offered(self, world):  # noqa: F811
        archived = DocumentType.objects.create(code="OLD", name="Retirado")
        archived.is_active = False
        archived.save(update_fields=["is_active"])
        client = _client(world, "add_document", "view_document")

        form = _get(client, doc_type=str(archived.pk)).context["form"]

        assert "doc_type" not in form.initial
        assert archived not in form.fields["doc_type"].queryset

    def test_an_active_type_is_still_preselected(self, world):  # noqa: F811
        active = DocumentType.objects.create(code="NEW", name="Vigente")
        client = _client(world, "add_document", "view_document")

        form = _get(client, doc_type=str(active.pk)).context["form"]

        assert str(form.initial["doc_type"]) == str(active.pk)
        assert active in form.fields["doc_type"].queryset

    def test_replacing_keeps_the_type_archived_since(self, world):  # noqa: F811
        """What the URL must not do, the document being replaced still may."""
        document = world["a"]["document"]
        old_type = document.doc_type
        old_type.is_active = False
        old_type.save(update_fields=["is_active"])
        client = _client(world, "change_document", "view_document")

        form = _get(client, "document-replace", pk=document.pk).context["form"]

        assert old_type in form.fields["doc_type"].queryset

    def test_a_url_type_cannot_widen_the_replace_form(self, world):  # noqa: F811
        """Same guard on the other screen: the query string is not the document."""
        document = world["a"]["document"]
        other = DocumentType.objects.create(code="OTH", name="Otro", is_active=False)
        client = _client(world, "change_document", "view_document")

        form = _get(
            client, "document-replace", pk=document.pk, doc_type=str(other.pk)
        ).context["form"]

        assert other not in form.fields["doc_type"].queryset


@pytest.mark.django_db
class TestPermission:
    def test_the_form_is_403_without_add_document_whatever_the_url_says(
        self,
        world,  # noqa: F811
    ):
        client = _client(world, "view_document")

        response = client.get(
            reverse("document-create"),
            _permit_params(world["a"]["permit"])
            | {"doc_type": str(world["a"]["document"].doc_type.pk)},
        )

        assert response.status_code == 403
        assert Document.objects.filter(pk=world["a"]["document"].pk).exists()
