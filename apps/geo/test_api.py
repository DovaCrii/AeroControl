"""GEO-5: read-only API (plan meta, version list, version content + ETag)."""

import pytest
from django.contrib.auth.models import Permission, User
from django.test import Client
from django.urls import reverse

from apps.geo.kml import canonical
from apps.geo.models import GeoPlan, GeoPlanVersion
from apps.registry.models import CostCenter


def _client(*codenames):
    user = User.objects.create_user(f"u-{'-'.join(codenames) or 'none'}", password="pw")
    if codenames:
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
    client = Client()
    assert client.login(username=user.username, password="pw")
    return client


def _doc(name):
    document = canonical.empty_document()
    document["name"] = name
    return document


def _plan_with_versions(count=2):
    center = CostCenter.objects.create(code="CC1", name="Uno")
    owner = User.objects.create_user("owner", password="pw")
    plan = GeoPlan.objects.create(
        title="Plan", cost_center=center, created_by=owner, status="draft"
    )
    latest = None
    for number in range(1, count + 1):
        document = _doc(f"v{number}")
        latest = GeoPlanVersion.objects.create(
            plan=plan,
            version_number=number,
            parent_version=latest,
            content=document,
            content_checksum=canonical.canonical_checksum(document),
            source="import" if number == 1 else "editor",
            summary=f"commit {number}",
            feature_count=canonical.count_features(document),
            size_bytes=canonical.size_bytes(document),
            created_by=owner,
        )
    plan.current_version = latest
    plan.save(update_fields=["current_version", "updated_at"])
    return plan


class TestPlanMeta:
    @pytest.mark.django_db
    def test_requires_auth(self, db):
        plan = _plan_with_versions()
        response = Client().get(reverse("api-v1-geo-plan", args=[plan.pk]))
        assert response.status_code == 401

    @pytest.mark.django_db
    def test_requires_view_permission(self, db):
        plan = _plan_with_versions()
        url = reverse("api-v1-geo-plan", args=[plan.pk])
        assert _client().get(url).status_code == 403

    @pytest.mark.django_db
    def test_returns_meta_with_current_version(self, db):
        plan = _plan_with_versions(count=2)
        url = reverse("api-v1-geo-plan", args=[plan.pk])

        response = _client("view_geoplan").get(url)

        assert response.status_code == 200
        payload = response.json()
        assert payload["id"] == str(plan.pk)
        assert payload["status"] == "draft"
        assert payload["cost_center"]["name"] == "CC1 - Uno"
        assert payload["flight_permission"] is None
        assert payload["current_version"]["version_number"] == 2
        assert payload["current_version"]["checksum"]
        assert "created_at" in payload and "updated_at" in payload

    @pytest.mark.django_db
    def test_unknown_plan_is_404(self, db):
        import uuid

        url = reverse("api-v1-geo-plan", args=[uuid.uuid4()])
        assert _client("view_geoplan").get(url).status_code == 404

    @pytest.mark.django_db
    def test_archived_plan_is_404(self, db):
        plan = _plan_with_versions()
        GeoPlan.objects.filter(pk=plan.pk).update(is_active=False)
        url = reverse("api-v1-geo-plan", args=[plan.pk])
        assert _client("view_geoplan").get(url).status_code == 404


class TestVersionList:
    @pytest.mark.django_db
    def test_requires_view_permission(self, db):
        plan = _plan_with_versions()
        url = reverse("api-v1-geo-plan-versions", args=[plan.pk])
        assert Client().get(url).status_code == 401
        assert _client().get(url).status_code == 403

    @pytest.mark.django_db
    def test_lists_versions_newest_first_without_content(self, db):
        plan = _plan_with_versions(count=3)
        url = reverse("api-v1-geo-plan-versions", args=[plan.pk])

        response = _client("view_geoplan").get(url)

        assert response.status_code == 200
        payload = response.json()
        assert payload["current_version"] == 3
        numbers = [v["version_number"] for v in payload["results"]]
        assert numbers == [3, 2, 1]
        # The heavy canonical blob must never ride along in the listing.
        assert all("content" not in v for v in payload["results"])
        assert payload["results"][0]["summary"] == "commit 3"


class TestVersionContent:
    @pytest.mark.django_db
    def test_requires_view_permission(self, db):
        plan = _plan_with_versions()
        url = reverse("api-v1-geo-plan-version-content", args=[plan.pk, 1])
        assert _client().get(url).status_code == 403

    @pytest.mark.django_db
    def test_returns_canonical_and_etag(self, db):
        plan = _plan_with_versions(count=2)
        version = plan.versions.get(version_number=1)
        url = reverse("api-v1-geo-plan-version-content", args=[plan.pk, 1])

        response = _client("view_geoplan").get(url)

        assert response.status_code == 200
        assert response.json() == version.content
        assert response["ETag"] == f'"{version.content_checksum}"'

    @pytest.mark.django_db
    def test_matching_if_none_match_returns_304(self, db):
        plan = _plan_with_versions()
        version = plan.versions.get(version_number=1)
        url = reverse("api-v1-geo-plan-version-content", args=[plan.pk, 1])
        etag = f'"{version.content_checksum}"'

        response = _client("view_geoplan").get(url, HTTP_IF_NONE_MATCH=etag)

        assert response.status_code == 304
        assert response["ETag"] == etag
        assert response.content == b""

    @pytest.mark.django_db
    def test_unknown_version_number_is_404(self, db):
        plan = _plan_with_versions(count=1)
        url = reverse("api-v1-geo-plan-version-content", args=[plan.pk, 99])
        assert _client("view_geoplan").get(url).status_code == 404
