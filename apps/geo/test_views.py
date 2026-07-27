"""GEO-4: import view, list and detail shell."""

import pytest
from django.contrib.auth.models import Permission, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from apps.compliance.models import Document
from apps.geo.models import GeoPlan, GeoPlanVersion
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


class TestImport:
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
