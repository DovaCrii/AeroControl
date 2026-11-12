"""LV-437: archivar (y restaurar) un log de vuelo subido mal o que falló.

Datos sintéticos. Archivar no borra: el `Document` del `.TXT` se archiva con la fila, el detalle
y las descargas siguen abriendo, y el comando de reanálisis no toca lo archivado.
"""

# ruff: noqa: F811 - las fixtures se importan de otras pruebas
import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.urls import reverse

from apps.core.models import AuditEvent
from apps.core.testing import login_as
from apps.operations.models import FlightLogAnalysis

from .test_lv427_flight_log_analysis import centre, isolated_storage, permit  # noqa: F401
from .test_lv429_dji_adapter import fake  # noqa: F401
from .test_lv431_flight_logs_section import (  # noqa: F401
    ADD,
    VIEW,
    _row,
    drone,
    foreign,
)

REASON = "Uploaded against the wrong aircraft."


def _archive_url(row):
    return reverse("flight-log-archive", args=[row.pk])


def _restore_url(row):
    return reverse("flight-log-restore", args=[row.pk])


def _archive(client, row, reason=REASON):
    return client.post(_archive_url(row), {"reason": reason})


@pytest.fixture
def row(centre, drone):
    return _row(centre, drone)


class TestArchiveModel:
    def test_archive_needs_a_written_reason(self, row):
        for blank in ("", "   ", None):
            with pytest.raises(ValidationError) as caught:
                row.archive(None, blank)
            assert "archive_reason" in caught.value.message_dict
        row.refresh_from_db()
        assert row.is_active

    def test_archive_and_restore_keep_the_log_and_its_document(self, row):
        row.archive(None, f"  {REASON} ")
        row.refresh_from_db()
        row.document.refresh_from_db()
        assert not row.is_active
        assert row.archive_reason == REASON
        assert row.archived_at is not None
        assert not row.document.is_active

        row.restore()
        row.refresh_from_db()
        row.document.refresh_from_db()
        assert row.is_active
        assert row.archive_reason == ""
        assert row.archived_at is None
        assert row.document.is_active
        # La señal de `Document` no rehizo ni duplicó el análisis.
        assert FlightLogAnalysis.objects.count() == 1


class TestArchiveView:
    def test_archives_with_a_reason_and_audits_it(self, row, centre):
        client = login_as(ADD, VIEW, member_of=centre.tenant)

        response = _archive(client, row)

        assert response.status_code == 302
        row.refresh_from_db()
        assert not row.is_active
        assert row.archive_reason == REASON
        assert row.archived_by_id == client.user.pk
        event = AuditEvent.objects.get(action="flight_log_archived")
        assert event.object_id == str(row.pk)
        assert REASON not in str(event.__dict__)

    def test_without_a_reason_the_form_refuses_and_nothing_changes(self, row, centre):
        client = login_as(ADD, VIEW, member_of=centre.tenant)

        response = _archive(client, row, reason="  ")

        assert response.status_code == 400
        assert b"is-invalid" in response.content
        row.refresh_from_db()
        assert row.is_active
        assert not AuditEvent.objects.filter(action="flight_log_archived").exists()

    def test_confirmation_screen_opens_on_get(self, row, centre):
        client = login_as(ADD, VIEW, member_of=centre.tenant)

        response = client.get(_archive_url(row))

        assert response.status_code == 200
        assert b'name="reason"' in response.content
        row.refresh_from_db()
        assert row.is_active

    def test_403_without_add_permission(self, row, centre):
        client = login_as(VIEW, "change_flightloganalysis", member_of=centre.tenant)

        assert client.get(_archive_url(row)).status_code == 403
        assert _archive(client, row).status_code == 403
        assert client.post(_restore_url(row)).status_code == 403
        row.refresh_from_db()
        assert row.is_active

    def test_404_for_another_tenant(self, row, foreign):
        client = login_as(ADD, VIEW, member_of=foreign[0])

        assert client.get(_archive_url(row)).status_code == 404
        assert _archive(client, row).status_code == 404
        row.refresh_from_db()
        assert row.is_active

    def test_cannot_archive_twice(self, row, centre):
        client = login_as(ADD, VIEW, member_of=centre.tenant)
        _archive(client, row)

        assert _archive(client, row).status_code == 404


class TestListAndDetail:
    def test_archived_leaves_the_list_and_shows_with_the_filter(self, row, centre):
        client = login_as(ADD, VIEW, member_of=centre.tenant)
        _archive(client, row)
        url = reverse("flight-log-list")

        default = client.get(url)
        archived = client.get(url, {"is_active": "archived"})

        assert list(default.context["objects"]) == []
        assert list(archived.context["objects"]) == [row]
        assert "id-chip--neutral" in archived.content.decode()
        assert "id-chip--neutral" not in default.content.decode()

    def test_detail_and_downloads_still_open_with_a_notice(self, row, centre):
        client = login_as(ADD, VIEW, member_of=centre.tenant)
        _archive(client, row)

        detail = client.get(reverse("flight-analysis", args=[row.pk]))
        html = detail.content.decode()

        assert detail.status_code == 200
        assert 'id="fa-archived"' in html
        assert REASON in html
        assert 'id="fa-restore-btn"' in html
        assert 'id="fa-archive-link"' not in html
        for name in (
            "flight-analysis-report",
            "flight-analysis-kml",
            "flight-analysis-csv",
        ):
            assert client.get(reverse(name, args=[row.pk])).status_code == 200

    def test_active_detail_offers_archive_only_with_permission(self, row, centre):
        url = reverse("flight-analysis", args=[row.pk])
        with_perm = login_as(ADD, VIEW, member_of=centre.tenant).get(url)
        without = login_as(VIEW, member_of=centre.tenant).get(url)

        assert b'id="fa-archive-link"' in with_perm.content
        assert b'id="fa-archive-link"' not in without.content

    def test_an_archived_log_cannot_be_edited(self, row, centre):
        client = login_as(
            ADD,
            VIEW,
            "view_flightrecord",
            "change_flightrecord",
            member_of=centre.tenant,
        )
        _archive(client, row)

        response = client.post(
            reverse("flight-analysis", args=[row.pk]), {"flight_record": ""}
        )

        assert response.status_code == 403


class TestRestore:
    def test_restore_brings_it_back_and_audits(self, row, centre):
        client = login_as(ADD, VIEW, member_of=centre.tenant)
        _archive(client, row)

        response = client.post(_restore_url(row))

        assert response.status_code == 302
        row.refresh_from_db()
        assert row.is_active
        assert row.archive_reason == ""
        assert AuditEvent.objects.filter(action="flight_log_restored").exists()
        assert list(client.get(reverse("flight-log-list")).context["objects"]) == [row]

    def test_restore_of_another_tenant_is_404(self, row, centre, foreign):
        row.archive(None, REASON)

        response = login_as(ADD, VIEW, member_of=foreign[0]).post(_restore_url(row))

        assert response.status_code == 404
        row.refresh_from_db()
        assert not row.is_active


class TestCommand:
    def test_analyze_command_never_touches_an_archived_log(
        self, centre, drone, monkeypatch
    ):
        pending = _row(centre, drone, status="pending")
        pending.archive(None, REASON)
        calls = []
        monkeypatch.setattr(
            "apps.operations.management.commands.analyze_flight_logs.analyze_document",
            lambda document, analysis=None: calls.append(document.pk),
        )

        call_command("analyze_flight_logs", "--retry-errors", "--outdated")

        assert calls == []
