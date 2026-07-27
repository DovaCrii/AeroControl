"""OPS-5: flight permission attachments over the existing Document pipeline."""

from datetime import date

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.test import Client
from django.urls import reverse

from apps.compliance.models import Document, DocumentType
from apps.registry.models import Aircraft, CostCenter, Operator

from .models import FlightPermission


def _client(*codenames):
    user = User.objects.create_user(f"u-{'-'.join(codenames) or 'none'}", password="pw")
    if codenames:
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
    client = Client()
    assert client.login(username=user.username, password="pw")
    return client


def _permission():
    cc = CostCenter.objects.create(code="CC1", name="One")
    operator = Operator.objects.create(employee_id="E1", full_name="Pilot")
    aircraft = Aircraft.objects.create(
        registration="CC-A1", type="RPA", model="M3", manufacturer="DJI"
    )
    permission = FlightPermission.objects.create(
        permission_number="P-1",
        cost_center=cc,
        purpose="Survey",
        valid_from=date(2026, 7, 1),
        valid_until=date(2026, 7, 10),
        location="Site",
    )
    permission.operators.add(operator)
    permission.aircraft_fleet.add(aircraft)
    return permission


class TestDocumentsSection:
    @pytest.mark.django_db
    def test_hidden_without_view_document_permission(self, db):
        permission = _permission()
        response = _client("view_flightpermission").get(
            reverse("permission-detail", args=[permission.pk])
        )
        # The card itself is gated by `{% if documents is not None %}`; the
        # context value is the reliable signal (the sidebar nav always shows
        # an unrelated "Documents" link, so asserting on page text here would
        # be a false negative).
        assert response.context["documents"] is None

    @pytest.mark.django_db
    def test_shows_attached_document(self, db):
        permission = _permission()
        doc_type = DocumentType.objects.create(code="LETTER", name="Letter")
        Document.objects.create(
            content_type=ContentType.objects.get_for_model(FlightPermission),
            object_id=permission.pk,
            doc_type=doc_type,
            title="Authorization letter",
            issue_date=date(2026, 7, 1),
            file_path="x",
        )
        response = _client("view_flightpermission", "view_document").get(
            reverse("permission-detail", args=[permission.pk])
        )
        assert "Authorization letter" in response.content.decode()

    @pytest.mark.django_db
    def test_upload_link_requires_add_document_permission(self, db):
        # {% url %} resolves to the actual path, not the URL name, so assert
        # on the resolved href rather than the literal string "document-create".
        permission = _permission()
        upload_href = reverse("document-create")
        without = _client("view_flightpermission", "view_document").get(
            reverse("permission-detail", args=[permission.pk])
        )
        assert upload_href not in without.content.decode()

        with_add = _client(
            "view_flightpermission", "view_document", "add_document"
        ).get(reverse("permission-detail", args=[permission.pk]))
        assert upload_href in with_add.content.decode()


class TestUploadFormPrefill:
    @pytest.mark.django_db
    def test_get_initial_reads_entity_type_and_object_id_from_query_params(self, db):
        permission = _permission()
        content_type = ContentType.objects.get_for_model(FlightPermission)
        client = _client("add_document")

        response = client.get(
            reverse("document-create"),
            {"entity_type": content_type.pk, "object_id": str(permission.pk)},
        )

        form = response.context["form"]
        assert form.initial["entity_type"] == str(content_type.pk)
        assert form.initial["object_id"] == str(permission.pk)
