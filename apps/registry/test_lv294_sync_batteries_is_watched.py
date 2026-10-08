"""LV-294: a failing AeroLink is *seen*, not found eight weeks later.

On 2026-08-26 AeroLink's `?kind=battery` started answering 500 on `p340` and nobody
knew until 2026-10-08. Two things made that possible, and this closes both:

* `sync_batteries` loaded the payload *before* opening its job record, so when
  AeroLink was down -- the one failure the job exists to survive -- the
  `CommandError` escaped leaving **no `JobRun` at all**. The watchdog could only
  notice by age, and without the reason.
* the watchdog did not list `sync_batteries` in the first place.

The first test is the regression: it fails on the code before this change, because
there is no run to find.
"""

import json
from datetime import timedelta

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from apps.core.jobs import DAILY_JOBS, WATCHED_JOBS, failing_jobs, job_health
from apps.core.models import JobRun
from apps.registry.aerolink import AeroLinkUnavailable

pytestmark = pytest.mark.django_db

COMMAND = "sync_batteries"
GATEWAY = "apps.registry.management.commands.sync_batteries.fetch_batteries"


def _gateway_down(monkeypatch, reason="HTTP 500"):
    def boom():
        raise AeroLinkUnavailable(reason)

    monkeypatch.setattr(GATEWAY, boom)


def _good_file(tmp_path):
    path = tmp_path / "batteries.json"
    path.write_text(
        json.dumps({"results": [{"serial_number": "BAT-001"}], "count": 1}),
        encoding="utf-8",
    )
    return str(path)


def _row():
    return next(r for r in job_health() if r["command"] == COMMAND)


class TestAFailingAeroLinkLeavesARecord:
    def test_an_unreachable_aerolink_records_an_error_with_the_reason(
        self, monkeypatch
    ):
        _gateway_down(monkeypatch, "HTTP 500")

        with pytest.raises(CommandError, match="AeroLink unavailable"):
            call_command(COMMAND)

        run = JobRun.objects.get(command=COMMAND)
        assert run.result == JobRun.RESULT_ERROR
        assert "AeroLink unavailable" in run.summary
        assert "HTTP 500" in run.summary

    def test_the_command_still_fails_loudly_for_the_scheduler(self, monkeypatch):
        """Recording it must not swallow it: systemd has to see a non-zero exit."""
        _gateway_down(monkeypatch)

        with pytest.raises(CommandError):
            call_command(COMMAND)

    def test_no_url_configured_is_recorded_too(self, settings):
        """The other way to be down: the timer exists and the setting does not."""
        settings.AEROLINK_API_URL = ""

        with pytest.raises(CommandError):
            call_command(COMMAND)

        assert JobRun.objects.get(command=COMMAND).result == JobRun.RESULT_ERROR

    def test_a_missing_file_is_recorded_too(self, tmp_path):
        with pytest.raises(CommandError, match="No such file"):
            call_command(COMMAND, "--from-file", str(tmp_path / "nope.json"))

        assert JobRun.objects.get(command=COMMAND).result == JobRun.RESULT_ERROR

    def test_a_good_run_is_still_recorded_ok(self, tmp_path):
        call_command(COMMAND, "--from-file", _good_file(tmp_path))

        run = JobRun.objects.get(command=COMMAND)
        assert run.result == JobRun.RESULT_OK
        assert "1 created" in run.summary


class TestTheWatchdogSeesIt:
    def test_it_is_a_watched_job_with_a_48_hour_allowance(self):
        assert COMMAND in WATCHED_JOBS
        # 48 h like the other daily jobs: one failed run does not shout, a
        # sustained outage does -- a watchdog that shouts at the first stumble
        # ends up ignored.
        assert DAILY_JOBS[COMMAND] == 48

    def test_it_reads_never_ran_until_it_does(self, tmp_path):
        assert _row()["never_ran"]

        call_command(COMMAND, "--from-file", _good_file(tmp_path))

        assert not _row()["never_ran"] and not _row()["stale"]

    def test_a_failure_is_reported_on_the_next_pass_not_after_two_days(
        self, monkeypatch
    ):
        """What would have exposed the eight-week 500 on its first day."""
        _gateway_down(monkeypatch)
        with pytest.raises(CommandError):
            call_command(COMMAND)

        failing = {row["command"]: row for row in failing_jobs()}

        assert COMMAND in failing
        assert failing[COMMAND]["result"] == JobRun.RESULT_ERROR
        assert not failing[COMMAND]["stale"], "reported for the error, not for age"

    def test_a_success_older_than_48_hours_is_stale(self):
        long_ago = timezone.now() - timedelta(hours=72)
        JobRun.objects.create(
            command=COMMAND,
            started_at=long_ago,
            finished_at=long_ago,
            result=JobRun.RESULT_OK,
            summary="0 created, 0 updated, 0 skipped",
        )

        assert _row()["stale"]
        assert COMMAND in {row["command"] for row in failing_jobs()}

    def test_a_recent_success_is_not_reported(self, tmp_path):
        call_command(COMMAND, "--from-file", _good_file(tmp_path))

        assert COMMAND not in {row["command"] for row in failing_jobs()}
