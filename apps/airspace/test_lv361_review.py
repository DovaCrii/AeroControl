"""LV-361 phase 4: the human review of a draft AIP snapshot, in the administration.

Everything is synthetic (see `test_lv361_importer`): the draft is built by the real command from
invented words, so the review is exercised on exactly what the importer writes. What is fixed here:
403 without the specific permission, a zone with a warning is never approved in bulk, publishing
needs every zone resolved and leaves the Google snapshot alone, an audit entry that carries codes and
statuses but no text, edits validated (ranges, a simple polygon) and scrubbed, and that only what is
approved AND published is what `active_aip_features()` returns.
"""

import pytest
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.urls import reverse

from apps.airspace import aip_import, aip_review, payload
from apps.airspace.models import AirspaceFeature, AirspaceSnapshot
from apps.airspace.test_lv361_importer import (  # noqa: F401 - `words` is a fixture
    BASE_ZONES,
    SENTINELS,
    ZONE_P901,
    ZONE_P902,
    ZONE_R903,
    make_pages,
    pdf_file,
    run,
    seed_google,
    words,
)
from apps.core.models import AuditEvent
from apps.core.testing import login_as as _login_as

pytestmark = pytest.mark.django_db

PERM = "review_airspacesnapshot"


def login_as(*codenames):
    client = _login_as(*codenames)
    client.defaults["HTTP_ACCEPT_LANGUAGE"] = "en"
    return client


@pytest.fixture
def reviewer():
    return login_as(PERM)


@pytest.fixture
def draft(tmp_path, words):  # noqa: F811
    run(file=str(pdf_file(tmp_path, "a")))
    return AirspaceSnapshot.objects.get(source_kind="aip_enr51")


def zone(code, snapshot=None):
    queryset = AirspaceFeature.objects.filter(source_kind="aip_enr51", code=code)
    if snapshot is not None:
        queryset = queryset.filter(snapshot=snapshot)
    return queryset.get()


def url(name, *args):
    return reverse(f"airspace-review-{name}", args=args)


def zone_url(snapshot, code):
    return url("zone", snapshot.pk, zone(code, snapshot).pk)


def post(client, address, **data):
    return client.post(address, data)


def messages_of(response):
    return [str(m) for m in response.context["messages"]] if response.context else []


def follow_messages(client, response):
    page = client.get(response["Location"])
    return [str(m) for m in page.context["messages"]]


# ── permissions ─────────────────────────────────────────────────────────────


def all_review_urls(snapshot):
    feature = zone("SC-P901", snapshot)
    return [
        url("list"),
        url("snapshot", snapshot.pk),
        url("zone", snapshot.pk, feature.pk),
        url("bulk", snapshot.pk),
        url("publish", snapshot.pk),
    ]


def test_every_review_route_answers_403_without_the_permission(draft):
    for who in (
        login_as(),
        login_as("view_airspacefeature"),
        login_as("change_airspacefeature"),
    ):
        for address in all_review_urls(draft):
            assert who.get(address).status_code == 403, address
        feature = zone("SC-P901", draft)
        for address, data in (
            (url("zone", draft.pk, feature.pk), {"action": "approve"}),
            (url("bulk", draft.pk), {"confirm": "yes"}),
            (url("publish", draft.pk), {"confirm": "yes"}),
        ):
            assert who.post(address, data).status_code == 403
    feature.refresh_from_db()
    assert feature.review_status == "pending"
    draft.refresh_from_db()
    assert draft.status == "draft" and not draft.is_current


def test_anonymous_visitors_get_no_access(draft):
    from django.test import Client

    for address in all_review_urls(draft):
        response = Client().get(address)
        assert response.status_code == 403


def test_the_permission_belongs_to_administrator_only_by_default(db):
    call_command("bootstrap_roles", stdout=__import__("io").StringIO())
    holders = [
        g.name
        for g in Group.objects.all()
        if g.permissions.filter(codename=PERM).exists()
    ]
    assert holders == ["Administrator"]


def test_the_guardian_of_permissions_sees_the_review_views_as_protected():
    from apps.core import test_lv268_permission_contract as contract

    routes = contract._routes()
    names = (
        "ReviewList",
        "ReviewSnapshot",
        "ReviewZone",
        "ReviewBulk",
        "ReviewPublish",
    )
    found = {
        k.rsplit(".", 1)[1]: v
        for k, v in routes.items()
        if k.startswith("apps.airspace.review_views")
    }
    assert set(names) <= set(found)
    for name in names:
        assert contract._has_model_permission(found[name])
        assert f"apps.airspace.review_views.{name}" not in contract.EXEMPT
        assert found[name].permission_required == "airspace.review_airspacesnapshot"


def test_the_administration_centre_links_the_review_only_for_who_may_use_it(draft):
    link = url("list")
    assert link in login_as(PERM).get(reverse("administration")).content.decode()
    assert (
        link
        not in login_as("view_airspacefeature")
        .get(reverse("administration"))
        .content.decode()
    )


# ── list and detail ─────────────────────────────────────────────────────────


def test_the_list_shows_snapshots_waiting_for_review_only(draft, reviewer):
    page = reviewer.get(url("list")).content.decode()
    assert "AMDT 67" in page and url("snapshot", draft.pk) in page
    AirspaceSnapshot.objects.filter(pk=draft.pk).update(status="rejected")
    assert url("snapshot", draft.pk) not in reviewer.get(url("list")).content.decode()


def test_the_snapshot_page_lists_zones_and_filters(draft, reviewer):
    page = reviewer.get(url("snapshot", draft.pk)).content.decode()
    for code in ("SC-P901", "SC-P902", "SC-R903", "SC-R904"):
        assert code in page
    flagged = reviewer.get(url("snapshot", draft.pk) + "?show=flagged").content.decode()
    assert "SC-P902" in flagged and "SC-R904" in flagged and "SC-P901" not in flagged
    clean = reviewer.get(url("snapshot", draft.pk) + "?show=clean").content.decode()
    assert "SC-P901" in clean and "SC-R903" in clean and "SC-P902" not in clean
    assert reviewer.get(url("snapshot", draft.pk) + "?show=nonsense").status_code == 200


def test_the_snapshot_page_shows_the_cross_check_without_a_verdict(
    tmp_path,
    words,  # noqa: F811
    reviewer,
    settings,  # noqa: F811
):  # noqa: F811
    settings.AIRSPACE_CROSSCHECK_THRESHOLD_M = None
    seed_google()
    run(file=str(pdf_file(tmp_path, "g")))
    snapshot = AirspaceSnapshot.objects.get(source_kind="aip_enr51")
    page = reviewer.get(url("snapshot", snapshot.pk)).content.decode()
    assert "No discrepancy threshold has been set" in page
    assert "Only in the Google map" in page and "SC-P977" in page
    assert "Discrepancy" not in page.split("<tbody>")[1].split("</tbody>")[0]
    zone_page = reviewer.get(zone_url(snapshot, "SC-P901")).content.decode()
    assert "no verdict" in zone_page and "m from the Google outline" in zone_page


def test_the_zone_page_shows_text_page_warnings_and_map_data(draft, reviewer):
    page = reviewer.get(zone_url(draft, "SC-P902")).content.decode()
    assert "ENR 5.1-1" in page and "SC-P902" in page
    assert "The vertex order crosses the polygon" in page
    assert 'id="air-review-data"' in page and "airspace-review-map.js" in page
    assert "crosses itself: correct the vertex order before approving" in page
    arc = reviewer.get(zone_url(draft, "SC-R904")).content.decode()
    assert "No geometry was proposed" in arc and "Approve as text only" in arc
    assert "airspace-review-map.js" not in arc


def test_the_zone_page_is_translated_and_carries_no_contact(draft):
    client = _login_as(PERM)
    client.defaults["HTTP_ACCEPT_LANGUAGE"] = "es"
    page = client.get(zone_url(draft, "SC-P901")).content.decode()
    assert "Texto leído del PDF" in page and "Aprobar" in page
    assert (
        "Página ENR 5.1-1 del AIP" in page
    )  # a blocktranslate, matched by its exact msgid
    assert aip_import.aip_parser.CONTACT_PLACEHOLDER in page
    for needle in SENTINELS:
        assert needle not in page


# ── single decisions and the audit trail ────────────────────────────────────


def test_approving_a_zone_records_who_when_and_audits_without_text(draft, reviewer):
    response = post(reviewer, zone_url(draft, "SC-P901"), action="approve")
    assert response.status_code == 302
    feature = zone("SC-P901", draft)
    assert feature.review_status == "approved" and feature.reviewed_by == reviewer.user
    assert feature.reviewed_at is not None
    draft.refresh_from_db()
    assert draft.status == "in_review"
    event = AuditEvent.objects.get(action="airspace_zone_approve")
    assert (
        event.object_id == str(feature.pk)
        and event.model_label == "airspace.AirspaceFeature"
    )
    assert event.actor == reviewer.user and event.status_code == 302
    assert event.metadata["code"] == "SC-P901" and event.metadata["to"] == "approved"
    blob = str(event.metadata) + event.path
    for needle in (*SENTINELS, feature.lateral_text, feature.schedule_text):
        assert needle not in blob


def test_rejecting_a_zone_keeps_the_row(draft, reviewer):
    post(reviewer, zone_url(draft, "SC-R903"), action="reject")
    feature = zone("SC-R903", draft)
    assert feature.review_status == "rejected" and feature.reviewed_by == reviewer.user
    assert AuditEvent.objects.filter(action="airspace_zone_reject").exists()


def test_a_polygon_that_crosses_itself_cannot_be_approved(draft, reviewer):
    response = post(reviewer, zone_url(draft, "SC-P902"), action="approve")
    assert "crosses itself" in " ".join(follow_messages(reviewer, response))
    feature = zone("SC-P902", draft)
    assert feature.review_status == "needs_review" and feature.reviewed_by is None
    assert not AuditEvent.objects.filter(action="airspace_zone_approve").exists()


def test_a_zone_without_geometry_can_be_approved_as_text_only(draft, reviewer):
    post(reviewer, zone_url(draft, "SC-R904"), action="approve")
    assert zone("SC-R904", draft).review_status == "approved"


def test_an_unknown_action_is_a_404(draft, reviewer):
    assert (
        post(reviewer, zone_url(draft, "SC-P901"), action="teleport").status_code == 404
    )


def test_a_zone_of_another_snapshot_is_not_reachable(draft, reviewer, tmp_path, words):  # noqa: F811
    words["pages"] = make_pages([ZONE_P901], amdt=68, date="26 NOV 2026")
    run(file=str(pdf_file(tmp_path, "b")))
    other = AirspaceSnapshot.objects.exclude(pk=draft.pk).get(source_kind="aip_enr51")
    mine = zone("SC-P901", other)
    assert reviewer.get(url("zone", draft.pk, mine.pk)).status_code == 404


# ── bulk approval ───────────────────────────────────────────────────────────


def test_bulk_approval_takes_only_the_clean_zones(draft, reviewer):
    page = reviewer.get(url("bulk", draft.pk)).content.decode()
    assert "SC-P901" in page and "SC-R903" in page
    assert "SC-P902" not in page.split("font-monospace")[1].split("</p>")[0]
    response = post(reviewer, url("bulk", draft.pk), confirm="yes")
    assert response.status_code == 302
    states = {
        f.code: f.review_status for f in AirspaceFeature.objects.filter(snapshot=draft)
    }
    assert states == {
        "SC-P901": "approved",
        "SC-R903": "approved",
        "SC-P902": "needs_review",  # crossing vertex order
        "SC-R904": "needs_review",  # arc: no geometry
    }
    event = AuditEvent.objects.get(action="airspace_bulk_approve")
    assert sorted(event.metadata["codes"]) == ["SC-P901", "SC-R903"]
    assert AuditEvent.objects.filter(action="airspace_zone_approve").count() == 2
    assert set(
        AuditEvent.objects.filter(action="airspace_zone_approve").values_list(
            "request_id", flat=True
        )
    ) == {event.request_id}


def test_bulk_approval_needs_the_confirmation(draft, reviewer):
    post(reviewer, url("bulk", draft.pk))
    post(reviewer, url("bulk", draft.pk), confirm="maybe")
    assert not AirspaceFeature.objects.filter(
        snapshot=draft, review_status="approved"
    ).exists()


def test_a_corrected_zone_is_not_bulk_approved_even_without_warnings(draft, reviewer):
    zone_p901 = zone("SC-P901", draft)
    post(
        reviewer,
        zone_url(draft, "SC-P901"),
        action="correct",
        vertices="-30.0, -70.0\n-30.0, -69.0\n-31.0, -69.0\n-31.0, -70.5",
        lateral_text=zone_p901.lateral_text,
        vertical_limits_text="UNL / GND",
        schedule_text="H24",
    )
    post(reviewer, url("bulk", draft.pk), confirm="yes")
    assert zone("SC-P901", draft).review_status == "needs_review"
    assert zone("SC-R903", draft).review_status == "approved"


def test_a_zone_with_a_warning_is_never_bulk_approved_whatever_its_status(
    draft, reviewer
):
    feature = zone("SC-P902", draft)
    AirspaceFeature.objects.filter(pk=feature.pk).update(review_status="pending")
    post(reviewer, url("bulk", draft.pk), confirm="yes")
    assert zone("SC-P902", draft).review_status == "pending"


def test_a_pending_zone_with_a_proposed_typo_fix_is_not_bulk_approved(draft, reviewer):
    # Not a crossing polygon (the bulk path skips those by itself): a plain parser warning.
    AirspaceFeature.objects.filter(pk=zone("SC-P901", draft).pk).update(
        parse_warnings=["space_in_decimal: vertex 2: stray space inside a decimal"]
    )
    # An arc left `pending`: no geometry, so it is not clean either.
    AirspaceFeature.objects.filter(pk=zone("SC-R904", draft).pk).update(
        review_status="pending"
    )
    post(reviewer, url("bulk", draft.pk), confirm="yes")
    assert zone("SC-P901", draft).review_status == "pending"
    assert zone("SC-R904", draft).review_status == "pending"
    assert zone("SC-R903", draft).review_status == "approved"


# ── publishing ──────────────────────────────────────────────────────────────


def resolve_everything(client, snapshot):
    post(client, url("bulk", snapshot.pk), confirm="yes")
    bowtie = zone("SC-P902", snapshot)
    post(
        client,
        url("zone", snapshot.pk, bowtie.pk),
        action="correct",
        vertices="-30.0, -70.0\n-30.0, -69.0\n-31.0, -69.0\n-31.0, -70.0",
        lateral_text=bowtie.lateral_text,
        vertical_limits_text=bowtie.vertical_limits_text,
        schedule_text=bowtie.schedule_text,
    )
    post(client, url("zone", snapshot.pk, bowtie.pk), action="approve")
    post(client, zone_url(snapshot, "SC-R904"), action="reject")


def test_publishing_with_unresolved_zones_is_refused_and_changes_nothing(
    draft, reviewer
):
    post(reviewer, url("bulk", draft.pk), confirm="yes")
    response = post(reviewer, url("publish", draft.pk), confirm="yes")
    assert "still unresolved" in " ".join(follow_messages(reviewer, response))
    draft.refresh_from_db()
    assert draft.status == "in_review" and not draft.is_current
    assert not AirspaceFeature.objects.filter(snapshot=draft, is_active=True).exists()
    page = reviewer.get(url("publish", draft.pk)).content.decode()
    assert "still unresolved" in page and "Confirm: publish" not in page
    assert not AuditEvent.objects.filter(action="airspace_publish").exists()


def test_publishing_needs_the_confirmation(draft, reviewer):
    resolve_everything(reviewer, draft)
    post(reviewer, url("publish", draft.pk))
    draft.refresh_from_db()
    assert draft.status == "in_review"


def test_publishing_makes_it_the_current_aip_copy_and_leaves_google_alone(
    draft, reviewer
):
    google = seed_google()
    before = [f.pk for f in payload.active_features()]
    resolve_everything(reviewer, draft)
    response = post(reviewer, url("publish", draft.pk), confirm="yes")
    assert response.status_code == 302
    draft.refresh_from_db()
    assert draft.status == "published" and draft.is_current
    assert AirspaceFeature.objects.filter(snapshot=draft, is_active=True).count() == 4
    google.refresh_from_db()
    assert google.is_current and google.status == "published"
    assert [
        f.pk for f in payload.active_features()
    ] == before  # the screen is unchanged
    assert payload.current_snapshot() == google
    event = AuditEvent.objects.get(action="airspace_publish")
    assert event.metadata["approved"] == 3 and event.metadata["rejected"] == 1
    assert event.object_id == str(draft.pk)


def test_only_what_is_approved_and_published_is_served(draft, reviewer):
    assert not aip_review.active_aip_features().exists()
    resolve_everything(reviewer, draft)
    assert not aip_review.active_aip_features().exists()  # approved but still a draft
    post(reviewer, url("publish", draft.pk), confirm="yes")
    served = set(aip_review.active_aip_features().values_list("code", flat=True))
    assert served == {"SC-P901", "SC-P902", "SC-R903"}  # SC-R904 was rejected
    rejected = zone("SC-R904", draft)
    assert rejected.is_active and rejected.review_status == "rejected"
    # The Google endpoint's queryset never includes AIP rows.
    assert not payload.active_features().filter(source_kind="aip_enr51").exists()


def test_a_second_publication_archives_the_previous_one_without_deleting(
    draft,
    reviewer,
    tmp_path,
    words,  # noqa: F811
):  # noqa: F811
    resolve_everything(reviewer, draft)
    post(reviewer, url("publish", draft.pk), confirm="yes")
    words["pages"] = make_pages(
        [ZONE_P901, ZONE_P902, ZONE_R903], amdt=68, date="26 NOV 2026"
    )
    run(file=str(pdf_file(tmp_path, "b")))
    second = AirspaceSnapshot.objects.exclude(pk=draft.pk).get(source_kind="aip_enr51")
    # Every unchanged zone kept its decision; only the arc that left the source is gone.
    assert second.archived == 1 and second.changed == 0
    assert aip_review.counts(second)["unresolved"] == 0
    post(reviewer, url("publish", second.pk), confirm="yes")
    draft.refresh_from_db()
    second.refresh_from_db()
    assert second.is_current and second.status == "published" and not draft.is_current
    assert AirspaceFeature.objects.filter(snapshot=draft).count() == 4
    old = AirspaceFeature.objects.filter(snapshot=draft)
    assert not old.filter(is_active=True).exists() and all(
        f.archived_in == second for f in old
    )
    assert set(aip_review.active_aip_features().values_list("snapshot", flat=True)) == {
        second.pk
    }


def test_all_rejected_is_not_publishable(draft, reviewer):
    for feature in AirspaceFeature.objects.filter(snapshot=draft):
        post(reviewer, url("zone", draft.pk, feature.pk), action="reject")
    page = reviewer.get(url("publish", draft.pk)).content.decode()
    assert "There is no approved zone to publish" in page
    post(reviewer, url("publish", draft.pk), confirm="yes")
    draft.refresh_from_db()
    assert draft.status == "in_review"


def test_a_published_snapshot_cannot_be_reviewed_again(draft, reviewer):
    resolve_everything(reviewer, draft)
    post(reviewer, url("publish", draft.pk), confirm="yes")
    response = post(reviewer, zone_url(draft, "SC-P901"), action="reject")
    assert "no longer open" in " ".join(follow_messages(reviewer, response))
    assert zone("SC-P901", draft).review_status == "approved"
    assert reviewer.get(url("bulk", draft.pk)).status_code == 200
    assert reviewer.get(zone_url(draft, "SC-P901")).status_code == 200


# ── corrections ─────────────────────────────────────────────────────────────

SQUARE_TEXT = "-30.0, -70.0\n-30.0, -69.0\n-31.0, -69.0\n-31.0, -70.0"


def correct(client, snapshot, code, **fields):
    feature = zone(code, snapshot)
    data = {
        "action": "correct",
        "vertices": aip_review.vertices_text(feature),
        "lateral_text": feature.lateral_text,
        "vertical_limits_text": feature.vertical_limits_text,
        "schedule_text": feature.schedule_text,
    }
    data.update(fields)
    return client.post(url("zone", snapshot.pk, feature.pk), data)


def test_a_valid_correction_replaces_the_outline_and_asks_for_a_new_approval(
    draft, reviewer
):
    feature = zone("SC-P902", draft)
    hash_before = feature.content_hash
    response = correct(reviewer, draft, "SC-P902", vertices=SQUARE_TEXT)
    assert response.status_code == 302
    feature = zone("SC-P902", draft)
    assert feature.geometry["coordinates"][0][0] == [-70.0, -30.0]
    assert feature.geometry["coordinates"][0][-1] == [-70.0, -30.0]
    assert (feature.min_lat, feature.max_lat, feature.min_lon, feature.max_lon) == (
        -31.0,
        -30.0,
        -70.0,
        -69.0,
    )
    assert feature.review_status == "needs_review" and feature.reviewed_by is None
    assert aip_review.MANUAL_EDIT_WARNING in feature.parse_warnings
    assert (
        feature.content_hash == hash_before
    )  # it still identifies what the SOURCE said
    assert not aip_review.crosses_itself(feature)
    event = AuditEvent.objects.get(action="airspace_zone_correct")
    assert event.metadata == {
        "query_keys": [],
        "code": "SC-P902",
        "fields": ["geometry"],
    }


def test_an_approved_zone_that_is_corrected_goes_back_to_review(draft, reviewer):
    post(reviewer, zone_url(draft, "SC-P901"), action="approve")
    correct(
        reviewer,
        draft,
        "SC-P901",
        vertices="-30.0, -70.0\n-30.0, -69.0\n-31.0, -69.0\n-31.0, -70.5",
    )
    feature = zone("SC-P901", draft)
    assert feature.review_status == "needs_review" and feature.reviewed_by is None


def test_a_correction_that_changes_nothing_says_so(draft, reviewer):
    response = correct(reviewer, draft, "SC-P901")
    assert "Nothing was changed" in " ".join(follow_messages(reviewer, response))
    assert not AuditEvent.objects.filter(action="airspace_zone_correct").exists()
    assert zone("SC-P901", draft).review_status == "pending"


@pytest.mark.parametrize(
    "vertices, message",
    [
        ("-10.0, -70.0\n-30.0, -69.0\n-31.0, -69.0", "latitude"),
        ("-30.0, -50.0\n-30.0, -69.0\n-31.0, -69.0", "longitude"),
        ("-30.0, -70.0\n-30.0, -69.0", "at least three"),
        ("-30.0, -70.0\n-30.0, -70.0\n-30.0, -70.0", "at least three"),
        ("-30.0, -70.0\n-31.0, -69.0\n-30.0, -69.0\n-31.0, -70.0", "crosses itself"),
        ("-30.0, -70.0\n-30.0, -70.0\n-31.0, -69.0\n-31.0, -70.0", "consecutive"),
        ("treinta sur\n-30.0, -69.0\n-31.0, -69.0", "not a coordinate"),
        ("-30.0 -70.0 -5\n-30.0, -69.0\n-31.0, -69.0", "not a coordinate"),
    ],
)
def test_a_bad_outline_is_refused_with_a_reason_and_saves_nothing(
    draft, reviewer, vertices, message
):
    before = zone("SC-P901", draft)
    response = correct(reviewer, draft, "SC-P901", vertices=vertices)
    assert response.status_code == 400
    assert message in response.content.decode()
    after = zone("SC-P901", draft)
    assert after.geometry == before.geometry and after.review_status == "pending"
    assert not AuditEvent.objects.filter(action="airspace_zone_correct").exists()


def test_too_many_vertices_are_refused(draft, reviewer):
    many = "\n".join(f"-30.{i:04d}, -70.0" for i in range(aip_review.MAX_VERTICES + 1))
    assert correct(reviewer, draft, "SC-P901", vertices=many).status_code == 400


def test_degrees_minutes_seconds_are_accepted(draft, reviewer):
    vertices = "30 00 00 S 70 00 00 W\n30 00 00 S 69 00 00 W\n31 00 00 S 69 00 00 W\n31 00 00 S 70 30 00 W"
    assert correct(reviewer, draft, "SC-P901", vertices=vertices).status_code == 302
    ring = zone("SC-P901", draft).geometry["coordinates"][0]
    assert ring[3] == [-70.5, -31.0]


def test_a_closing_vertex_equal_to_the_first_is_accepted():
    vertices = aip_review.parse_vertices(SQUARE_TEXT + "\n-30.0, -70.0")
    assert len(vertices) == 4


def test_a_load_by_hand_gives_a_geometry_to_a_zone_that_had_none(draft, reviewer):
    arc = zone("SC-R904", draft)
    assert not aip_review.has_geometry(arc)
    assert correct(reviewer, draft, "SC-R904", vertices=SQUARE_TEXT).status_code == 302
    arc = zone("SC-R904", draft)
    assert aip_review.has_geometry(arc) and arc.geometry_method == "polygon"
    post(reviewer, zone_url(draft, "SC-R904"), action="approve")
    assert zone("SC-R904", draft).review_status == "approved"


def test_typed_contacts_are_scrubbed_and_never_reach_the_audit(draft, reviewer):
    typed = "H24. Llamar a centinela.tres@test.com o al 29222117."
    correct(reviewer, draft, "SC-P901", schedule_text=typed)
    feature = zone("SC-P901", draft)
    assert (
        "centinela.tres" not in feature.schedule_text
        and "29222117" not in feature.schedule_text
    )
    assert "H24" in feature.schedule_text
    event = AuditEvent.objects.get(action="airspace_zone_correct")
    assert event.metadata["fields"] == ["schedule_text"]
    assert "centinela" not in str(event.metadata)


def test_a_corrected_zone_keeps_its_correction_in_the_next_amendment(
    draft,
    reviewer,
    tmp_path,
    words,  # noqa: F811
):  # noqa: F811
    correct(reviewer, draft, "SC-P902", vertices=SQUARE_TEXT)
    post(reviewer, zone_url(draft, "SC-P902"), action="approve")
    words["pages"] = make_pages(BASE_ZONES, amdt=68, date="26 NOV 2026")
    run(file=str(pdf_file(tmp_path, "c")))
    second = AirspaceSnapshot.objects.exclude(pk=draft.pk).get(source_kind="aip_enr51")
    carried = zone("SC-P902", second)
    assert carried.review_status == "approved" and carried.geometry["coordinates"][0][
        0
    ] == [-70.0, -30.0]


# ── what a reviewer sees of the PDF ─────────────────────────────────────────


def test_the_screen_does_not_pretend_to_show_the_pdf_page(draft, reviewer):
    page = reviewer.get(zone_url(draft, "SC-P901")).content.decode()
    body = page.split('class="page-header"')[1]
    assert "<img" not in body and "<canvas" not in body and "<iframe" not in body
    assert "open the AIP page to compare" in page
