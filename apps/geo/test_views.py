"""GEO-4 import/list/detail shell, GEO-7/8 map island config, GEO-9 workflow."""

import io
import zipfile

import pytest
from django.contrib.auth.models import Permission, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from apps.compliance.models import Document
from apps.geo.models import GeoPlan, GeoPlanHistory, GeoPlanVersion
from apps.geo.test_kml import HAPPY_KML
from apps.registry.models import CostCenter

DOCTYPE_KML = (
    b'<?xml version="1.0"?>\n'
    b'<!DOCTYPE kml [ <!ENTITY lol "lol"> ]>\n'
    b"<kml><Document></Document></kml>"
)


def _client(*codenames):
    user = User.objects.create_user(f"u-{'-'.join(codenames) or 'none'}", password="pw")
    if codenames:
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
    client = Client()
    assert client.login(username=user.username, password="pw")
    return client


def _kml_upload(name="plan.kml", content=None):
    return SimpleUploadedFile(
        name,
        content if content is not None else HAPPY_KML.encode("utf-8"),
        content_type="application/vnd.google-earth.kml+xml",
    )


def _permission(cost_center, **overrides):
    """A minimal active FlightPermission on `cost_center` (LV-60 tests)."""
    from datetime import date

    from apps.operations.models import FlightPermission

    fields = {
        "cost_center": cost_center,
        "purpose": "Survey",
        "valid_from": date(2026, 7, 22),
        "valid_until": date(2026, 7, 22),
        "location": "Santiago",
    }
    fields.update(overrides)
    return FlightPermission.objects.create(**fields)


def _kmz_with_icon():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("doc.kml", HAPPY_KML)
        archive.writestr("files/icon.png", b"\x89PNG\r\n\x1a\nICONBYTES")
    return SimpleUploadedFile(
        "plan.kmz",
        buffer.getvalue(),
        content_type="application/vnd.google-earth.kmz",
    )


class TestEmbeddedResource:
    """GEO-13: serving embedded KMZ icons through the whitelisted endpoint."""

    def _import(self, settings, tmp_path):
        settings.DOCUMENTS_ROOT = str(tmp_path)
        center = CostCenter.objects.create(code="CCK", name="Kmz")
        client = _client("add_geoplan", "view_geoplan")
        response = client.post(
            reverse("geo-plan-import"),
            {"title": "K", "cost_center": center.pk, "file": _kmz_with_icon()},
        )
        assert response.status_code == 302
        return client, GeoPlan.objects.get()

    @pytest.mark.django_db
    def test_serves_a_whitelisted_icon(self, db, settings, tmp_path):
        client, plan = self._import(settings, tmp_path)
        url = reverse("api-v1-geo-plan-resource", args=[plan.pk])
        response = client.get(url, {"name": "files/icon.png"})
        assert response.status_code == 200
        assert response["Content-Type"] == "image/png"
        assert b"ICONBYTES" in response.content

    @pytest.mark.django_db
    def test_unknown_resource_is_not_found(self, db, settings, tmp_path):
        client, plan = self._import(settings, tmp_path)
        url = reverse("api-v1-geo-plan-resource", args=[plan.pk])
        # Not in the version's kmz_resources whitelist -> never opened.
        assert client.get(url, {"name": "files/evil.png"}).status_code == 404

    @pytest.mark.django_db
    def test_requires_view_permission(self, db, settings, tmp_path):
        _client_with, plan = self._import(settings, tmp_path)
        url = reverse("api-v1-geo-plan-resource", args=[plan.pk])
        assert _client().get(url, {"name": "files/icon.png"}).status_code in (401, 403)


class TestImport:
    @pytest.mark.django_db
    def test_import_form_shows_a_loading_indicator_on_submit(self, db):
        """LV-5: the import can take a few seconds on a large KMZ; the form
        carries the progressive-enhancement hook (static/js/app.js) that
        disables the button and shows a progress bar while it waits."""
        client = _client("add_geoplan")

        response = client.get(reverse("geo-plan-import"))

        content = response.content.decode()
        assert "data-loading-label=" in content
        assert "data-loading-progress" in content

    @pytest.mark.django_db
    def test_import_prefills_the_flight_permission_from_the_query_string(self, db):
        """LV-50: "Import plan" from a flight permission's own detail page
        (?flight_permission=<pk>) prefills that field, same pattern as
        maintenance-create?aircraft=."""
        from datetime import date

        from apps.operations.models import FlightPermission
        from apps.registry.models import Aircraft, Operator

        center = CostCenter.objects.create(code="CC1", name="Uno")
        operator = Operator.objects.create(
            employee_id="P1", full_name="Pilot One", cost_center=center
        )
        aircraft = Aircraft.objects.create(
            registration="CC-AAA",
            type="Fixed",
            model="A",
            manufacturer="Maker",
            cost_center=center,
        )
        permission = FlightPermission.objects.create(
            cost_center=center,
            purpose="Survey",
            valid_from=date(2026, 7, 22),
            valid_until=date(2026, 7, 22),
            location="Santiago",
        )
        permission.operators.add(operator)
        permission.aircraft_fleet.add(aircraft)
        client = _client("add_geoplan")

        response = client.get(
            reverse("geo-plan-import"), {"flight_permission": str(permission.pk)}
        )

        assert response.status_code == 200
        assert response.context["form"].initial["flight_permission"] == str(
            permission.pk
        )
        # LV-60: the cost center is the permission's, not a second decision.
        assert response.context["form"].initial["cost_center"] == center.pk

    @pytest.mark.django_db
    def test_import_from_a_malformed_permission_id_does_not_crash(self, db):
        """LV-60 prefills the cost center by looking the permission up; a
        non-UUID in the query string must leave the field empty, not 500
        (same guard as the compliance report's filters, LV-54)."""
        client = _client("add_geoplan")

        response = client.get(reverse("geo-plan-import"), {"flight_permission": "1"})

        assert response.status_code == 200
        assert "cost_center" not in response.context["form"].initial

    @pytest.mark.django_db
    def test_a_plan_linked_to_a_permission_inherits_its_title_and_cost_center(
        self, db, settings, tmp_path
    ):
        """LV-60: importing against a permission is not a separate record --
        posting neither a title nor a cost center still produces a coherent
        plan, both derived from the permission the user already chose."""
        settings.DOCUMENTS_ROOT = str(tmp_path)
        permission = _permission(CostCenter.objects.create(code="CC1", name="Uno"))
        client = _client("add_geoplan")

        response = client.post(
            reverse("geo-plan-import"),
            {
                "flight_permission": permission.pk,
                "file": _kml_upload(name="area-norte.kml"),
            },
        )

        assert response.status_code == 302
        plan = GeoPlan.objects.get()
        assert plan.flight_permission_id == permission.pk
        assert plan.cost_center_id == permission.cost_center_id
        assert plan.title == f"{permission} · area-norte"

    @pytest.mark.django_db
    def test_a_plan_without_a_permission_derives_its_title_from_the_cost_center(
        self, db, settings, tmp_path
    ):
        settings.DOCUMENTS_ROOT = str(tmp_path)
        center = CostCenter.objects.create(code="CC1", name="Uno")
        client = _client("add_geoplan")

        response = client.post(
            reverse("geo-plan-import"),
            {"cost_center": center.pk, "file": _kml_upload(name="area-sur.kml")},
        )

        assert response.status_code == 302
        assert GeoPlan.objects.get().title == f"{center} · area-sur"

    @pytest.mark.django_db
    def test_an_explicit_title_is_kept(self, db, settings, tmp_path):
        settings.DOCUMENTS_ROOT = str(tmp_path)
        permission = _permission(CostCenter.objects.create(code="CC1", name="Uno"))
        client = _client("add_geoplan")

        client.post(
            reverse("geo-plan-import"),
            {
                "title": "Mi propio título",
                "flight_permission": permission.pk,
                "file": _kml_upload(),
            },
        )

        assert GeoPlan.objects.get().title == "Mi propio título"

    @pytest.mark.django_db
    def test_a_cost_center_other_than_the_permissions_is_rejected(
        self, db, settings, tmp_path
    ):
        """LV-60: a plan filed under a different contract than its own
        permission is incoherent; nothing rejected it before."""
        settings.DOCUMENTS_ROOT = str(tmp_path)
        permission = _permission(CostCenter.objects.create(code="CC1", name="Uno"))
        other = CostCenter.objects.create(code="CC2", name="Dos")
        client = _client("add_geoplan")

        response = client.post(
            reverse("geo-plan-import"),
            {
                "flight_permission": permission.pk,
                "cost_center": other.pk,
                "file": _kml_upload(),
            },
        )

        assert response.status_code == 200  # re-rendered with the error
        assert "cost_center" in response.context["form"].errors
        assert GeoPlan.objects.count() == 0

    @pytest.mark.django_db
    def test_neither_a_permission_nor_a_cost_center_is_rejected(self, db):
        """Nothing to inherit from, and GeoPlan.cost_center is not nullable."""
        client = _client("add_geoplan")

        response = client.post(reverse("geo-plan-import"), {"file": _kml_upload()})

        assert response.status_code == 200
        assert "cost_center" in response.context["form"].errors
        assert GeoPlan.objects.count() == 0

    @pytest.mark.django_db
    def test_import_requires_add_permission(self, db, settings, tmp_path):
        settings.DOCUMENTS_ROOT = str(tmp_path)
        center = CostCenter.objects.create(code="CC1", name="Uno")
        client = _client("view_geoplan")  # can view, cannot add

        response = client.post(
            reverse("geo-plan-import"),
            {"title": "Plan", "cost_center": center.pk, "file": _kml_upload()},
        )

        assert response.status_code == 403
        assert GeoPlan.objects.count() == 0

    @pytest.mark.django_db
    def test_successful_import_creates_plan_document_and_version(
        self, db, settings, tmp_path
    ):
        settings.DOCUMENTS_ROOT = str(tmp_path)
        center = CostCenter.objects.create(code="CC1", name="Uno")
        client = _client("add_geoplan")

        response = client.post(
            reverse("geo-plan-import"),
            {"title": "CC716", "cost_center": center.pk, "file": _kml_upload()},
        )

        assert response.status_code == 302
        plan = GeoPlan.objects.get()
        assert plan.status == "draft"
        assert plan.cost_center == center
        assert plan.source_document is not None
        assert plan.source_document.doc_type.code == "GEO_SOURCE"
        version = GeoPlanVersion.objects.get()
        assert plan.current_version_id == version.id
        assert version.version_number == 1
        assert version.source == "import"
        assert version.feature_count == 5
        assert version.content["name"] == "CC716 Planificacion"
        assert Document.objects.filter(pk=plan.source_document_id).exists()

    @pytest.mark.django_db
    def test_malicious_upload_creates_nothing(self, db, settings, tmp_path):
        settings.DOCUMENTS_ROOT = str(tmp_path)
        center = CostCenter.objects.create(code="CC1", name="Uno")
        client = _client("add_geoplan")

        response = client.post(
            reverse("geo-plan-import"),
            {
                "title": "evil",
                "cost_center": center.pk,
                "file": _kml_upload("evil.kml", DOCTYPE_KML),
            },
        )

        # Form re-rendered with an error; the atomic block never ran.
        assert response.status_code == 200
        assert GeoPlan.objects.count() == 0
        assert GeoPlanVersion.objects.count() == 0
        assert Document.objects.count() == 0


class TestListAndDetail:
    @staticmethod
    def _plan(db):
        center = CostCenter.objects.create(code="CC1", name="Uno")
        user = User.objects.create_user("owner", password="pw")
        return GeoPlan.objects.create(
            title="Plan", cost_center=center, created_by=user, status="draft"
        )

    @pytest.mark.django_db
    def test_list_requires_view_permission(self, db):
        assert _client().get(reverse("geo-plan-list")).status_code == 403
        assert _client("view_geoplan").get(reverse("geo-plan-list")).status_code == 200

    @pytest.mark.django_db
    def test_detail_requires_view_permission(self, db):
        plan = self._plan(db)
        url = reverse("geo-plan-detail", args=[plan.pk])
        assert _client().get(url).status_code == 403
        response = _client("view_geoplan").get(url)
        assert response.status_code == 200
        assert "Plan" in response.content.decode()

    @pytest.mark.django_db
    def test_detail_provides_map_island_config_and_assets(self, db):
        plan = self._plan(db)
        version = GeoPlanVersion.objects.create(
            plan=plan,
            version_number=1,
            content={"schema_version": 1, "children": []},
            content_checksum="0" * 64,
            source="import",
            created_by=plan.created_by,
        )
        plan.current_version = version
        plan.save(update_fields=["current_version", "updated_at"])

        response = _client("view_geoplan").get(
            reverse("geo-plan-detail", args=[plan.pk])
        )

        assert response.status_code == 200
        config = response.context["map_config"]
        assert config["planId"] == str(plan.pk)
        assert config["currentVersion"] == 1
        assert config["editable"] is False  # GEO-7 is read-only
        assert config["contentUrl"].endswith("/versions/1/content/")
        assert config["tileProviders"]  # at least one provider
        assert set(config["labels"]) >= {"length", "area", "layers", "empty"}
        # GEO-11 layer-tree labels are wired through to the island.
        assert set(config["labels"]) >= {"visible", "duplicate", "explode", "rootDrop"}
        # GEO-12a: every version and its content URL, for client-side diffing.
        assert isinstance(config["versions"], list) and config["versions"]
        assert set(config["versions"][0]) == {"number", "url"}
        assert set(config["labels"]) >= {"compare", "diffAdded", "diffRemoved"}
        # GEO-13: base URL for serving embedded KMZ icons.
        assert config["resourceUrlBase"].endswith("/resource/")

        content = response.content.decode()
        assert 'id="geo-map-config"' in content  # json_script mount
        assert "js/geo/main.js" in content  # ES module island
        assert "vendor/leaflet/leaflet.js" in content  # vendored, not a CDN
        assert 'integrity="sha384-' in content  # with SRI

    @pytest.mark.django_db
    def test_detail_without_version_has_no_content_url(self, db):
        plan = self._plan(db)  # no current_version
        response = _client("view_geoplan").get(
            reverse("geo-plan-detail", args=[plan.pk])
        )
        assert response.status_code == 200
        config = response.context["map_config"]
        assert config["currentVersion"] is None
        assert config["contentUrl"] is None


class TestEditorConfig:
    @staticmethod
    def _plan(db, status="draft"):
        center = CostCenter.objects.create(code="CC1", name="Uno")
        user = User.objects.create_user("owner", password="pw")
        plan = GeoPlan.objects.create(
            title="Plan", cost_center=center, created_by=user, status=status
        )
        version = GeoPlanVersion.objects.create(
            plan=plan,
            version_number=1,
            content={"schema_version": 1, "children": []},
            content_checksum="0" * 64,
            source="import",
            created_by=user,
        )
        plan.current_version = version
        plan.save(update_fields=["current_version", "updated_at"])
        return plan

    @pytest.mark.django_db
    def test_change_permission_and_editable_status_enables_editor(self, db):
        plan = self._plan(db, status="editing")
        response = _client("view_geoplan", "change_geoplan").get(
            reverse("geo-plan-detail", args=[plan.pk])
        )
        config = response.context["map_config"]
        assert config["editable"] is True
        assert config["commitUrl"].endswith("/versions/")
        assert config["baseVersion"] == 1
        assert config["csrfToken"]  # a token is issued for the write
        content = response.content.decode()
        assert "leaflet-geoman" in content  # editor assets loaded
        assert 'id="geo-save"' in content

    @pytest.mark.django_db
    def test_view_only_user_gets_read_only(self, db):
        plan = self._plan(db, status="editing")
        response = _client("view_geoplan").get(
            reverse("geo-plan-detail", args=[plan.pk])
        )
        config = response.context["map_config"]
        assert config["editable"] is False
        assert config["csrfToken"] == ""
        assert "leaflet-geoman" not in response.content.decode()

    @pytest.mark.django_db
    def test_approved_plan_is_not_editable_even_with_change_permission(self, db):
        plan = self._plan(db, status="approved")
        response = _client("view_geoplan", "change_geoplan").get(
            reverse("geo-plan-detail", args=[plan.pk])
        )
        assert response.context["map_config"]["editable"] is False
        assert "leaflet-geoman" not in response.content.decode()


class TestWorkflow:
    @staticmethod
    def _plan(db, status="draft"):
        center = CostCenter.objects.create(code="CCW", name="W")
        user = User.objects.create_user("wf-owner", password="pw")
        return GeoPlan.objects.create(
            title="WF", cost_center=center, created_by=user, status=status
        )

    @pytest.mark.django_db
    def test_start_editing_requires_change_permission(self, db):
        plan = self._plan(db, status="draft")
        url = reverse("geo-plan-start-editing", args=[plan.pk])
        assert _client("view_geoplan").post(url).status_code == 403
        assert _client("change_geoplan").post(url).status_code == 302
        plan.refresh_from_db()
        assert plan.status == "editing"

    @pytest.mark.django_db
    def test_approve_needs_approve_permission_not_change(self, db):
        plan = self._plan(db, status="in_review")
        url = reverse("geo-plan-approve", args=[plan.pk])
        assert _client("change_geoplan").post(url).status_code == 403
        assert _client("approve_geoplan").post(url).status_code == 302
        plan.refresh_from_db()
        assert plan.status == "approved"

    @pytest.mark.django_db
    def test_reopen_from_approved_needs_approve_permission(self, db):
        plan = self._plan(db, status="approved")
        url = reverse("geo-plan-reopen", args=[plan.pk])
        assert _client("approve_geoplan").post(url).status_code == 302
        plan.refresh_from_db()
        assert plan.status == "editing"

    @pytest.mark.django_db
    def test_invalid_transition_leaves_status_unchanged(self, db):
        plan = self._plan(db, status="draft")  # approve is only valid from in_review
        response = _client("approve_geoplan").post(
            reverse("geo-plan-approve", args=[plan.pk])
        )
        assert response.status_code == 302  # redirected with an error message
        plan.refresh_from_db()
        assert plan.status == "draft"

    @pytest.mark.django_db
    def test_transition_writes_history(self, db):
        plan = self._plan(db, status="editing")
        _client("change_geoplan").post(
            reverse("geo-plan-submit-review", args=[plan.pk])
        )
        plan.refresh_from_db()
        assert plan.status == "in_review"
        assert GeoPlanHistory.objects.filter(
            plan=plan, previous_status="editing", new_status="in_review"
        ).exists()
