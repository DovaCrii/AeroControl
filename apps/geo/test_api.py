"""Geo JSON API tests.

GEO-5: read-only (plan meta, version list, version content + ETag).
GEO-6: commit + restore (concurrency, plan_locked, validation, no_change).
"""

import json

import pytest
from django.contrib.auth.models import Permission, User
from django.test import Client
from django.urls import reverse

from apps.core.models import AuditEvent
from apps.geo.kml import canonical
from apps.geo.models import GeoPlan, GeoPlanVersion
from apps.registry.models import CostCenter


def _doc_with_features(name, n):
    """A valid canonical document with n point placemarks."""
    document = canonical.empty_document()
    document["name"] = name
    document["children"] = [
        {
            "kind": "placemark",
            "uid": f"p-{i}",
            "name": f"pm{i}",
            "geometry": {"type": "Point", "coordinates": [i * 0.1, 0.0]},
        }
        for i in range(n)
    ]
    return document


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


def _post(client, url, body, **extra):
    return client.post(
        url, data=json.dumps(body), content_type="application/json", **extra
    )


class TestCommit:
    @staticmethod
    def _url(plan):
        return reverse("api-v1-geo-plan-versions", args=[plan.pk])

    @pytest.mark.django_db
    def test_requires_auth_and_change_permission(self, db):
        plan = _plan_with_versions(count=1)
        url = self._url(plan)
        body = {"base_version": 1, "content": _doc("x")}
        assert _post(Client(), url, body).status_code == 401
        # view_geoplan is not enough to write.
        assert _post(_client("view_geoplan"), url, body).status_code == 403

    @pytest.mark.django_db
    def test_commit_appends_version_and_recomputes_derived_fields(self, db):
        plan = _plan_with_versions(count=1)
        content = _doc_with_features("edited", 2)
        # The server must ignore client-supplied derived fields.
        body = {
            "base_version": 1,
            "summary": "moved a point",
            "content": content,
            "feature_count": 999,
        }

        response = _post(_client("change_geoplan"), self._url(plan), body)

        assert response.status_code == 201
        payload = response.json()
        assert payload["version_number"] == 2
        assert payload["feature_count"] == 2  # recomputed, not the 999 sent
        plan.refresh_from_db()
        assert plan.current_version.version_number == 2
        version = plan.versions.get(version_number=2)
        assert version.source == "editor"
        assert version.parent_version.version_number == 1
        assert version.summary == "moved a point"
        assert AuditEvent.objects.filter(
            action="geo_plan_committed", object_id=str(plan.pk)
        ).exists()

    @pytest.mark.django_db
    def test_stale_base_version_conflicts(self, db):
        plan = _plan_with_versions(count=1)
        body = {"base_version": 0, "content": _doc("x")}
        response = _post(_client("change_geoplan"), self._url(plan), body)
        assert response.status_code == 409
        assert response.json()["code"] == "conflict"
        assert plan.versions.count() == 1

    @pytest.mark.django_db
    def test_if_unmodified_since_conflicts(self, db):
        plan = _plan_with_versions(count=1)
        from datetime import timedelta

        stale = (plan.updated_at - timedelta(seconds=1)).isoformat()
        body = {"base_version": 1, "content": _doc("x")}
        response = _post(
            _client("change_geoplan"),
            self._url(plan),
            body,
            HTTP_IF_UNMODIFIED_SINCE=stale,
        )
        assert response.status_code == 409
        assert response.json()["code"] == "conflict"

    @pytest.mark.django_db
    def test_locked_plan_rejects_commit(self, db):
        plan = _plan_with_versions(count=1)
        GeoPlan.objects.filter(pk=plan.pk).update(status="approved")
        body = {"base_version": 1, "content": _doc("x")}
        response = _post(_client("change_geoplan"), self._url(plan), body)
        assert response.status_code == 409
        assert response.json()["code"] == "plan_locked"

    @pytest.mark.django_db
    def test_identical_content_is_no_change(self, db):
        plan = _plan_with_versions(count=1)
        # V1 content is _doc("v1"); re-sending it must not create a version.
        body = {"base_version": 1, "content": _doc("v1")}
        response = _post(_client("change_geoplan"), self._url(plan), body)
        assert response.status_code == 200
        assert response.json()["code"] == "no_change"
        assert plan.versions.count() == 1

    @pytest.mark.django_db
    @pytest.mark.parametrize(
        "content",
        [
            {**canonical.empty_document(), "schema_version": 99},
            {
                **canonical.empty_document(),
                "children": [
                    {
                        "kind": "placemark",
                        "uid": "p",
                        "geometry": {"type": "Point", "coordinates": [200.0, 0.0]},
                    }
                ],
            },
            {
                **canonical.empty_document(),
                "children": [{"kind": "raw", "raw_xml": "<!DOCTYPE x><x/>"}],
            },
        ],
    )
    def test_invalid_documents_are_rejected(self, db, content):
        plan = _plan_with_versions(count=1)
        body = {"base_version": 1, "content": content}
        response = _post(_client("change_geoplan"), self._url(plan), body)
        assert response.status_code == 400
        assert plan.versions.count() == 1

    @pytest.mark.django_db
    def test_malformed_json_is_400(self, db):
        plan = _plan_with_versions(count=1)
        response = _client("change_geoplan").post(
            self._url(plan), data="{bad", content_type="application/json"
        )
        assert response.status_code == 400


class TestRestore:
    @staticmethod
    def _url(plan, number):
        return reverse("api-v1-geo-plan-version-restore", args=[plan.pk, number])

    @pytest.mark.django_db
    def test_requires_auth_and_change_permission(self, db):
        plan = _plan_with_versions(count=2)
        url = self._url(plan, 1)
        assert _post(Client(), url, {}).status_code == 401
        assert _post(_client("view_geoplan"), url, {}).status_code == 403

    @pytest.mark.django_db
    def test_restore_copies_version_forward(self, db):
        plan = _plan_with_versions(count=2)  # v1="v1", v2="v2"; latest=2
        response = _post(_client("change_geoplan"), self._url(plan, 1), {})
        assert response.status_code == 201
        payload = response.json()
        assert payload["version_number"] == 3
        assert payload["restored_from"] == 1
        version = plan.versions.get(version_number=3)
        assert version.source == "restore"
        assert version.restored_from.version_number == 1
        assert version.content == _doc("v1")
        plan.refresh_from_db()
        assert plan.current_version.version_number == 3
        assert AuditEvent.objects.filter(
            action="geo_plan_restored", object_id=str(plan.pk)
        ).exists()

    @pytest.mark.django_db
    def test_restore_of_current_is_no_change(self, db):
        plan = _plan_with_versions(count=2)  # latest is v2
        response = _post(_client("change_geoplan"), self._url(plan, 2), {})
        assert response.status_code == 200
        assert response.json()["code"] == "no_change"
        assert plan.versions.count() == 2

    @pytest.mark.django_db
    def test_restore_on_locked_plan_is_409(self, db):
        plan = _plan_with_versions(count=2)
        GeoPlan.objects.filter(pk=plan.pk).update(status="approved")
        response = _post(_client("change_geoplan"), self._url(plan, 1), {})
        assert response.status_code == 409
        assert response.json()["code"] == "plan_locked"

    @pytest.mark.django_db
    def test_restore_unknown_version_is_404(self, db):
        plan = _plan_with_versions(count=1)
        response = _post(_client("change_geoplan"), self._url(plan, 99), {})
        assert response.status_code == 404
