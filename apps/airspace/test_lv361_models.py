"""LV-361 fase 1: campos de fuente y de revisión, un snapshot vigente POR FUENTE.

Sin datos reales ni PDF: todo sale de filas inventadas y del KML sintético. Se fija que la
migración deja las filas que ya existen como lo que son (el mapa de Google, publicado y
aprobado), que cada restricción rechaza lo que dice rechazar, que el importador de Google
sigue siendo idempotente aun con una foto AIP vigente al lado, y que el mapa y `data.json`
siguen sirviendo SÓLO las features aprobadas de la foto vigente de Google.
"""

import json
from datetime import date
from pathlib import Path

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
from django.db.models import ProtectedError
from django.db.migrations.executor import MigrationExecutor
from django.urls import reverse
from django.utils import timezone

from apps.airspace import models as m
from apps.airspace import payload
from apps.airspace.models import (
    AirspaceCrossCheck,
    AirspaceFeature,
    AirspaceSnapshot,
)
from apps.core.testing import login_as as _login_as

KML = Path(__file__).parent / "test_data" / "synthetic_airspace.kml"
FIRST = ("airspace", "0001_create_airspace_snapshot_and_feature")
LATEST = ("airspace", "0002_aip_source_and_review_fields")


def login_as(*codenames):
    client = _login_as(*codenames)
    client.defaults["HTTP_ACCEPT_LANGUAGE"] = "en"
    return client


def snapshot(**kwargs):
    data = {
        "source_name": "synthetic",
        "fetched_at": timezone.now(),
        "sha256": "a" * 64,
        "attribution": "synthetic",
    }
    data.update(kwargs)
    return AirspaceSnapshot.objects.create(**data)


def feature(snap, key="k1", **kwargs):
    data = {
        "snapshot": snap,
        "source_key": key,
        "content_hash": "h",
        "kind": "restricted",
        "code": "SC-R1",
        "name": "Synthetic zone",
        "raw_name": "Synthetic zone",
        "geometry": {"type": "Point", "coordinates": [-70.0, -33.0]},
        "min_lat": -33.0,
        "max_lat": -33.0,
        "min_lon": -70.0,
        "max_lon": -70.0,
        "center_lat": -33.0,
        "center_lon": -70.0,
    }
    data.update(kwargs)
    return AirspaceFeature.objects.create(**data)


# ── migración ───────────────────────────────────────────────────────────────


@pytest.mark.django_db(transaction=True)
def test_a_database_with_0001_data_migrates_and_keeps_meaning():
    executor = MigrationExecutor(connection)
    executor.migrate([FIRST])
    old = MigrationExecutor(connection).loader.project_state([FIRST]).apps
    Snap = old.get_model("airspace", "AirspaceSnapshot")
    Feat = old.get_model("airspace", "AirspaceFeature")
    snap = Snap.objects.create(
        source_name="legacy",
        fetched_at=timezone.now(),
        sha256="b" * 64,
        attribution="legacy",
        is_current=True,
    )
    legacy = Feat.objects.create(
        snapshot=snap,
        source_key="legacy-1",
        content_hash="h",
        kind="danger",
        name="Legacy",
        raw_name="Legacy",
        geometry={"type": "Point", "coordinates": [-70.0, -33.0]},
        min_lat=-33.0,
        max_lat=-33.0,
        min_lon=-70.0,
        max_lon=-70.0,
        center_lat=-33.0,
        center_lon=-70.0,
    )
    try:
        MigrationExecutor(connection).migrate([LATEST])
        migrated_snap = AirspaceSnapshot.objects.get(pk=snap.pk)
        migrated = AirspaceFeature.objects.get(pk=legacy.pk)
        assert migrated_snap.source_kind == m.SOURCE_GOOGLE
        assert migrated_snap.status == m.STATUS_PUBLISHED
        assert migrated_snap.is_current is True
        assert migrated_snap.amdt_number == "" and migrated_snap.pdf_sha256 == ""
        assert migrated_snap.effective_date is None
        assert migrated.source_kind == m.SOURCE_GOOGLE
        assert migrated.review_status == m.REVIEW_APPROVED
        assert migrated.lateral_text == "" and migrated.geometry_method == ""
        assert migrated.parse_warnings == []
        assert migrated.reviewed_by is None and migrated.reviewed_at is None
        # Y lo que nazca después de la migración arranca pendiente, no aprobado.
        assert AirspaceFeature._meta.get_field("review_status").default == "pending"
        # La pantalla sigue viendo esa foto.
        assert payload.current_snapshot().pk == snap.pk
        assert list(payload.active_features()) == [migrated]
    finally:
        MigrationExecutor(connection).migrate(
            MigrationExecutor(connection).loader.graph.leaf_nodes()
        )


# ── restricciones: snapshot ─────────────────────────────────────────────────


@pytest.mark.django_db
def test_one_current_snapshot_per_source_not_one_overall():
    snapshot(is_current=True, source_kind=m.SOURCE_GOOGLE)
    snapshot(is_current=True, source_kind=m.SOURCE_AIP_ENR51, sha256="c" * 64)
    snapshot(is_current=True, source_kind=m.SOURCE_AIP_ENR55, sha256="d" * 64)
    assert AirspaceSnapshot.objects.filter(is_current=True).count() == 3


@pytest.mark.django_db
def test_two_current_snapshots_of_the_same_source_are_refused():
    snapshot(is_current=True, source_kind=m.SOURCE_AIP_ENR51)
    with pytest.raises(IntegrityError), transaction.atomic():
        snapshot(is_current=True, source_kind=m.SOURCE_AIP_ENR51, sha256="c" * 64)


@pytest.mark.django_db
def test_older_snapshots_of_a_source_may_pile_up_while_one_is_current():
    snapshot(is_current=False, source_kind=m.SOURCE_AIP_ENR51)
    snapshot(is_current=False, source_kind=m.SOURCE_AIP_ENR51, sha256="c" * 64)
    snapshot(is_current=True, source_kind=m.SOURCE_AIP_ENR51, sha256="d" * 64)


@pytest.mark.django_db
@pytest.mark.parametrize("field", ["source_kind", "status"])
def test_snapshot_values_outside_the_list_are_refused(field):
    with pytest.raises(IntegrityError), transaction.atomic():
        snapshot(**{field: "bogus"})


@pytest.mark.django_db
@pytest.mark.parametrize("status", ["draft", "in_review", "rejected"])
def test_a_snapshot_that_is_not_published_cannot_be_current(status):
    with pytest.raises(IntegrityError), transaction.atomic():
        snapshot(is_current=True, status=status)


@pytest.mark.django_db
def test_a_draft_aip_snapshot_does_not_become_current_by_existing():
    draft = snapshot(
        source_kind=m.SOURCE_AIP_ENR51,
        status=m.STATUS_DRAFT,
        amdt_number="67",
        effective_date=date(2026, 8, 6),
        pdf_sha256="e" * 64,
    )
    assert draft.is_current is False
    assert payload.current_snapshot() is None


# ── restricciones: feature ──────────────────────────────────────────────────


@pytest.mark.django_db
def test_a_feature_defaults_to_pending_unreviewed_google_shape():
    snap = snapshot()
    f = feature(snap)
    assert f.review_status == m.REVIEW_PENDING
    assert f.source_kind == m.SOURCE_GOOGLE
    assert f.parse_warnings == [] and f.lateral_text == "" and f.geometry_method == ""


@pytest.mark.django_db
@pytest.mark.parametrize(
    "field, value",
    [
        ("source_kind", "bogus"),
        ("geometry_method", "blob"),
        ("review_status", "bogus"),
    ],
)
def test_feature_values_outside_the_list_are_refused(field, value):
    with pytest.raises(IntegrityError), transaction.atomic():
        feature(snapshot(), **{field: value})


@pytest.mark.django_db
@pytest.mark.parametrize("method", ["", "polygon", "circle", "arc", "sector"])
def test_every_geometry_method_in_the_design_is_accepted(method):
    feature(snapshot(), geometry_method=method)


@pytest.mark.django_db
def test_the_same_source_key_may_be_active_in_two_sources_but_not_twice_in_one():
    google = snapshot()
    aip = snapshot(source_kind=m.SOURCE_AIP_ENR51, status=m.STATUS_DRAFT)
    feature(google, key="same")
    feature(aip, key="same", source_kind=m.SOURCE_AIP_ENR51)
    with pytest.raises(IntegrityError), transaction.atomic():
        feature(google, key="same")


@pytest.mark.django_db
def test_the_reviewer_is_protected_from_deletion():
    user = get_user_model().objects.create_user("reviewer", password="x")
    f = feature(snapshot(), reviewed_by=user, reviewed_at=timezone.now())
    with pytest.raises(ProtectedError):
        user.delete()
    assert AirspaceFeature.objects.get(pk=f.pk).reviewed_by == user


# ── AirspaceCrossCheck ──────────────────────────────────────────────────────


@pytest.fixture
def pair():
    google = snapshot()
    aip = snapshot(source_kind=m.SOURCE_AIP_ENR51, status=m.STATUS_DRAFT)
    return (
        feature(aip, key="a", source_kind=m.SOURCE_AIP_ENR51),
        feature(google, key="g"),
    )


@pytest.mark.django_db
@pytest.mark.parametrize("result", ["match", "discrepancy"])
def test_compared_results_need_both_sides(pair, result):
    aip, google = pair
    AirspaceCrossCheck.objects.create(
        code="SC-R1",
        aip_feature=aip,
        google_feature=google,
        result=result,
        max_vertex_m=12.5,
        median_m=3.0,
    )
    for sides in ({"aip_feature": aip}, {"google_feature": google}):
        with pytest.raises(IntegrityError), transaction.atomic():
            AirspaceCrossCheck.objects.create(result=result, **sides)


@pytest.mark.django_db
def test_missing_in_google_has_only_the_aip_side(pair):
    aip, google = pair
    AirspaceCrossCheck.objects.create(
        aip_feature=aip, result=AirspaceCrossCheck.RESULT_MISSING_IN_GOOGLE
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        AirspaceCrossCheck.objects.create(
            aip_feature=aip,
            google_feature=google,
            result=AirspaceCrossCheck.RESULT_MISSING_IN_GOOGLE,
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        AirspaceCrossCheck.objects.create(
            google_feature=google, result=AirspaceCrossCheck.RESULT_MISSING_IN_GOOGLE
        )


@pytest.mark.django_db
@pytest.mark.parametrize("result", ["missing_in_aip", "google_only"])
def test_google_side_results_have_only_the_google_side(pair, result):
    aip, google = pair
    AirspaceCrossCheck.objects.create(google_feature=google, result=result)
    with pytest.raises(IntegrityError), transaction.atomic():
        AirspaceCrossCheck.objects.create(
            aip_feature=aip, google_feature=google, result=result
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        AirspaceCrossCheck.objects.create(aip_feature=aip, result=result)


@pytest.mark.django_db
def test_a_cross_check_needs_at_least_one_feature_and_a_known_result(pair):
    aip, _google = pair
    with pytest.raises(IntegrityError), transaction.atomic():
        AirspaceCrossCheck.objects.create(result="match")
    with pytest.raises(IntegrityError), transaction.atomic():
        AirspaceCrossCheck.objects.create(aip_feature=aip, result="bogus")


@pytest.mark.django_db
def test_distances_cannot_be_negative(pair):
    aip, google = pair
    for field in ("max_vertex_m", "median_m"):
        with pytest.raises(IntegrityError), transaction.atomic():
            AirspaceCrossCheck.objects.create(
                aip_feature=aip,
                google_feature=google,
                result="match",
                **{field: -1.0},
            )


@pytest.mark.django_db
def test_a_compared_feature_cannot_be_deleted(pair):
    aip, google = pair
    AirspaceCrossCheck.objects.create(
        aip_feature=aip, google_feature=google, result="match"
    )
    with pytest.raises(ProtectedError):
        aip.delete()
    with pytest.raises(ProtectedError):
        google.delete()


@pytest.mark.django_db
def test_the_admin_of_the_cross_check_is_read_only(rf):
    model_admin = admin.site._registry[AirspaceCrossCheck]
    request = rf.get("/")
    assert not model_admin.has_add_permission(request)
    assert not model_admin.has_change_permission(request)
    assert not model_admin.has_delete_permission(request)


# ── el importador de Google y lo que ve la pantalla ─────────────────────────


@pytest.mark.django_db
def test_the_google_import_is_idempotent_and_marks_what_it_writes():
    call_command("import_airspace_zones", "--file", str(KML))
    first = AirspaceSnapshot.objects.get()
    assert first.is_current and first.source_kind == m.SOURCE_GOOGLE
    assert first.status == m.STATUS_PUBLISHED
    features = AirspaceFeature.objects.filter(is_active=True)
    assert features.count() > 0
    assert set(features.values_list("source_kind", flat=True)) == {m.SOURCE_GOOGLE}
    assert set(features.values_list("review_status", flat=True)) == {m.REVIEW_APPROVED}

    call_command("import_airspace_zones", "--file", str(KML))
    assert AirspaceSnapshot.objects.count() == 1
    assert AirspaceFeature.objects.count() == features.count()


@pytest.mark.django_db
def test_an_aip_snapshot_current_beside_it_does_not_disturb_the_google_import():
    aip = snapshot(
        source_kind=m.SOURCE_AIP_ENR51,
        is_current=True,
        sha256="f" * 64,
        amdt_number="67",
    )
    aip_feature = feature(
        aip, key="aip-1", source_kind=m.SOURCE_AIP_ENR51, review_status="approved"
    )
    call_command("import_airspace_zones", "--file", str(KML))
    call_command("import_airspace_zones", "--file", str(KML))

    aip.refresh_from_db()
    aip_feature.refresh_from_db()
    assert aip.is_current and aip_feature.is_active
    google = AirspaceSnapshot.objects.filter(source_kind=m.SOURCE_GOOGLE)
    assert google.count() == 1 and google.get().is_current


@pytest.mark.django_db
def test_a_changed_google_file_replaces_only_the_google_current(tmp_path):
    call_command("import_airspace_zones", "--file", str(KML))
    aip = snapshot(source_kind=m.SOURCE_AIP_ENR51, is_current=True, sha256="f" * 64)
    changed = tmp_path / "changed.kml"
    changed.write_bytes(KML.read_bytes().replace(b"Limite Norte", b"Limite Norte 2", 1))
    call_command("import_airspace_zones", "--file", str(changed))
    currents = AirspaceSnapshot.objects.filter(is_current=True)
    assert {s.source_kind for s in currents} == {m.SOURCE_GOOGLE, m.SOURCE_AIP_ENR51}
    assert currents.count() == 2
    assert AirspaceSnapshot.objects.filter(source_kind=m.SOURCE_GOOGLE).count() == 2
    aip.refresh_from_db()
    assert aip.is_current


@pytest.mark.django_db
def test_the_screen_serves_only_approved_features_of_the_current_google_snapshot():
    call_command("import_airspace_zones", "--file", str(KML))
    google = AirspaceSnapshot.objects.get(source_kind=m.SOURCE_GOOGLE)
    victim = AirspaceFeature.objects.filter(
        snapshot=google, is_active=True, code__startswith="SC-"
    ).first()
    other = AirspaceFeature.objects.filter(snapshot=google, is_active=True).exclude(
        pk=victim.pk
    )[0]
    # Una zona de Google que alguien rechazó, y una zona AIP aprobada pero de otra fuente.
    AirspaceFeature.objects.filter(pk=victim.pk).update(review_status="rejected")
    aip = snapshot(source_kind=m.SOURCE_AIP_ENR51, is_current=True, sha256="f" * 64)
    feature(
        aip,
        key="aip-1",
        source_kind=m.SOURCE_AIP_ENR51,
        review_status="approved",
        code="SC-R99",
        name="AIP only zone",
    )
    feature(aip, key="aip-2", source_kind=m.SOURCE_AIP_ENR51, name="Pending AIP zone")

    client = login_as("view_airspacefeature")
    response = client.get(reverse("airspace-data"))
    assert response.status_code == 200
    body = json.loads(response.content)
    ids = {f["id"] for f in body["features"]}
    assert str(victim.pk) not in ids
    assert str(other.pk) in ids
    # Phase 5: an approved zone of a PUBLISHED current AIP copy is now served (see
    # `test_lv361_aip_layer.py`); the one still pending is not, and the Google copy keeps its place.
    assert "AIP only zone" in response.content.decode()
    assert "Pending AIP zone" not in response.content.decode()
    assert body["snapshot"]["id"] == str(google.pk)


@pytest.mark.django_db
def test_without_a_google_copy_the_data_answers_404_even_with_an_aip_one():
    aip = snapshot(source_kind=m.SOURCE_AIP_ENR51, is_current=True, sha256="f" * 64)
    feature(aip, source_kind=m.SOURCE_AIP_ENR51, review_status="approved")
    client = login_as("view_airspacefeature")
    assert client.get(reverse("airspace-data")).status_code == 404


@pytest.mark.django_db
def test_the_data_stays_403_without_the_view_permission():
    call_command("import_airspace_zones", "--file", str(KML))
    assert login_as().get(reverse("airspace-data")).status_code == 403
