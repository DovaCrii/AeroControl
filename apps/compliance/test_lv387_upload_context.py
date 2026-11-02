"""LV-387: the upload form is prefilled by context (PR 4 of 4). Fictional data.

`doc_type` of the query string takes the type's `code` (or, as before, its pk);
the types usual for the record come first as their own group; and the detail
pages carry an "Upload..." menu with one link per usual type.
"""

import re
import pytest
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from apps.compliance.forms import SUGGESTED_GROUP_LABEL
from apps.compliance.models import DocumentType
from apps.compliance.test_lv372_tenant_scope import world  # noqa: F401
from apps.compliance.upload_context import (
    SUGGESTED_TYPE_CODES,
    resolve_doc_type,
)
from apps.core.testing import login_as
from apps.maintenance.models import MaintenanceRecord
from apps.operations.models import FlightPermission
from apps.registry.models import Aircraft


@pytest.fixture
def catalog(db):
    """Every code of the map, created as a fictional type."""
    created = {}
    codes = {code for codes in SUGGESTED_TYPE_CODES.values() for code in codes}
    for code in sorted(codes):
        # Some codes are already seeded by migrations: take what exists.
        created[code], _new = DocumentType.objects.get_or_create(
            code=code,
            defaults={"name": f"Tipo {code}", "category": DocumentType.CATEGORY_DGAC},
        )
        if not created[code].is_active:
            created[code].is_active = True
            created[code].save(update_fields=["is_active"])
    return created


def _client(world, *codenames):  # noqa: F811
    return login_as(*codenames, member_of=world["a"]["tenant"])


def _params(record, **extra):
    return {
        "entity_type": ContentType.objects.get_for_model(record).pk,
        "object_id": str(record.pk),
        **extra,
    }


def _form(client, **params):
    response = client.get(reverse("document-create"), params)
    assert response.status_code == 200
    return response


def _groups(response):
    """[(label, [option values])] of the document-type select, in page order."""
    html = response.content.decode()
    select = re.search(r'<select[^>]*name="doc_type".*?</select>', html, re.S).group(0)
    groups = []
    for label, body in re.findall(
        r'<optgroup label="([^"]*)">(.*?)</optgroup>', select, re.S
    ):
        groups.append((label, re.findall(r'<option value="([^"]+)"', body)))
    return groups, select


@pytest.mark.django_db
class TestTheTypeInTheUrl:
    def test_403_without_add_document_even_with_parameters(self, world, catalog):  # noqa: F811
        client = _client(world, "view_document")
        params = _params(world["a"]["permit"], doc_type="dgac-flight-permit")

        assert client.get(reverse("document-create"), params).status_code == 403

    def test_code_and_pk_are_equivalent(self, world, catalog):  # noqa: F811
        client = _client(world, "add_document", "view_document")
        chosen = catalog["dgac-flight-permit"]
        permit = world["a"]["permit"]

        by_code = _form(client, **_params(permit, doc_type=chosen.code))
        by_pk = _form(client, **_params(permit, doc_type=str(chosen.pk)))

        assert by_code.context["form"].initial["doc_type"] == chosen.pk
        assert by_pk.context["form"].initial["doc_type"] == chosen.pk

    def test_an_unknown_code_is_ignored(self, world, catalog):  # noqa: F811
        client = _client(world, "add_document", "view_document")

        form = _form(
            client, **_params(world["a"]["permit"], doc_type="no-such-code")
        ).context["form"]

        assert "doc_type" not in form.initial

    def test_an_archived_type_by_code_is_ignored(self, world, catalog):  # noqa: F811
        archived = catalog["dgac-flight-permit"]
        archived.is_active = False
        archived.save(update_fields=["is_active"])
        client = _client(world, "add_document", "view_document")

        form = _form(
            client, **_params(world["a"]["permit"], doc_type=archived.code)
        ).context["form"]

        assert "doc_type" not in form.initial
        assert resolve_doc_type(archived.code) is None

    def test_another_companys_record_gets_no_subject_no_suggestions_no_dates(
        self,
        world,  # noqa: F811
        catalog,
    ):
        client = _client(world, "add_document", "view_document")
        response = _form(
            client, **_params(world["b"]["permit"], doc_type="dgac-flight-permit")
        )

        form = response.context["form"]
        for key in ("entity_type", "object_id", "issue_date", "expiry_date"):
            assert key not in form.initial
        labels = [label for label, _values in _groups(response)[0]]
        assert str(SUGGESTED_GROUP_LABEL) not in labels


@pytest.mark.django_db
class TestSuggestedTypesFirst:
    def test_the_group_comes_first_without_repeating_a_value(self, world, catalog):  # noqa: F811
        client = _client(world, "add_document", "view_document")
        response = _form(client, **_params(world["a"]["permit"]))

        groups, select = _groups(response)

        assert groups[0][0] == str(SUGGESTED_GROUP_LABEL)
        expected = [
            str(catalog[code].pk)
            for code in SUGGESTED_TYPE_CODES[("operations", "flightpermission")]
        ]
        assert groups[0][1] == expected
        values = re.findall(r'<option value="([^"]+)"', select)
        assert len(values) == len(set(values))

    def test_the_prefilled_type_leads_the_group(self, world, catalog):  # noqa: F811
        client = _client(world, "add_document", "view_document")
        chosen = catalog["flight-log-txt"]
        response = _form(client, **_params(world["a"]["permit"], doc_type=chosen.code))

        groups, select = _groups(response)

        assert groups[0][1][0] == str(chosen.pk)
        assert re.search(rf'<option value="{chosen.pk}"[^>]*selected', select)

    def test_without_a_subject_there_is_no_group(self, world, catalog):  # noqa: F811
        client = _client(world, "add_document", "view_document")

        groups, _select = _groups(_form(client))

        assert str(SUGGESTED_GROUP_LABEL) not in [label for label, _ in groups]


def _aircraft_page(world, client):  # noqa: F811
    return client.get(reverse("aircraft-detail", args=[world["a"]["aircraft"].pk]))


@pytest.mark.django_db
class TestTheUploadMenu:
    def test_the_aircraft_page_links_each_suggested_type(self, world, catalog):  # noqa: F811
        client = _client(world, "view_aircraft", "view_document", "add_document")
        aircraft = world["a"]["aircraft"]

        html = _aircraft_page(world, client).content.decode()

        base = reverse("document-create")
        ct = ContentType.objects.get_for_model(Aircraft).pk
        for code in SUGGESTED_TYPE_CODES[("registry", "aircraft")]:
            link = f"{base}?entity_type={ct}&amp;object_id={aircraft.pk}&amp;doc_type={code}"
            assert link in html

    def test_the_permit_page_links_its_types(self, world, catalog):  # noqa: F811
        client = _client(
            world, "view_flightpermission", "view_document", "add_document"
        )
        permit = world["a"]["permit"]

        html = client.get(
            reverse("permission-detail", args=[permit.pk])
        ).content.decode()

        ct = ContentType.objects.get_for_model(FlightPermission).pk
        for code in SUGGESTED_TYPE_CODES[("operations", "flightpermission")]:
            assert (
                f"entity_type={ct}&amp;object_id={permit.pk}&amp;doc_type={code}"
                in html
            )

    def test_the_maintenance_page_links_its_types(self, world, catalog):  # noqa: F811
        aircraft = world["a"]["aircraft"]
        record = MaintenanceRecord.objects.create(
            aircraft=aircraft, maintenance_type="preventive", description="Revision"
        )
        client = _client(
            world, "view_maintenancerecord", "view_document", "add_document"
        )

        html = client.get(
            reverse("maintenance-detail", args=[record.pk])
        ).content.decode()

        ct = ContentType.objects.get_for_model(MaintenanceRecord).pk
        for code in SUGGESTED_TYPE_CODES[("maintenance", "maintenancerecord")]:
            assert (
                f"entity_type={ct}&amp;object_id={record.pk}&amp;doc_type={code}"
                in html
            )

    def test_no_menu_without_add_document(self, world, catalog):  # noqa: F811
        client = _client(world, "view_aircraft", "view_document")

        response = _aircraft_page(world, client)

        assert response.context["suggested_upload_types"] == []
        assert "data-upload-menu" not in response.content.decode()

    def test_a_missing_type_is_left_out_of_the_menu(self, world, catalog):  # noqa: F811
        catalog["airworthiness-cert"].delete()
        client = _client(world, "view_aircraft", "view_document", "add_document")

        entries = _aircraft_page(world, client).context["suggested_upload_types"]

        codes = [entry["code"] for entry in entries]
        assert "airworthiness-cert" not in codes
        assert "aircraft-registration" in codes

    def test_the_credential_links_to_its_own_flow(self, world, catalog):  # noqa: F811
        operator = world["a"]["operator"]
        client = _client(
            world,
            "view_operator",
            "change_operator",
            "view_document",
            "add_document",
        )

        html = client.get(
            reverse("operator-detail", args=[operator.pk])
        ).content.decode()

        generic = reverse("document-create")
        assert re.search(
            r'data-upload-type="dgac-credential" href="#credential-upload"', html
        )
        assert f"{generic}?entity_type" in html  # the other type still goes generic
        assert "doc_type=dgac-credential" not in html

    def test_without_change_operator_the_credential_goes_generic(self, world, catalog):  # noqa: F811
        operator = world["a"]["operator"]
        client = _client(world, "view_operator", "view_document", "add_document")

        html = client.get(
            reverse("operator-detail", args=[operator.pk])
        ).content.decode()

        assert "doc_type=dgac-credential" in html
        assert 'href="#credential-upload"' not in html


@pytest.mark.django_db
def test_the_dossier_shortcut_carries_the_code(world, catalog):  # noqa: F811
    from apps.operations.dossier import _upload_action

    user = login_as("add_document").user
    label, url = _upload_action(world["a"]["permit"], "dgac-flight-permit", user)

    assert "doc_type=dgac-flight-permit" in url
    assert label
