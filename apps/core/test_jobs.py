import pytest
from django.conf import settings
from django.core.management import call_command

from apps.core.jobs import record_job_run
from apps.core.models import JobRun


@pytest.mark.django_db
def test_record_job_run_stores_success_with_summary():
    with record_job_run("demo_job") as run:
        run["summary"] = "3 things done"

    job = JobRun.objects.get()
    assert job.command == "demo_job"
    assert job.result == JobRun.RESULT_OK
    assert job.summary == "3 things done"
    assert job.finished_at is not None
    assert job.duration_seconds is not None


@pytest.mark.django_db
def test_record_job_run_records_failure_and_reraises():
    with pytest.raises(ValueError):
        with record_job_run("failing_job"):
            raise ValueError("boom")

    job = JobRun.objects.get()
    assert job.result == JobRun.RESULT_ERROR
    assert "ValueError: boom" in job.summary
    assert job.finished_at is not None


@pytest.mark.django_db
def test_summary_is_truncated_to_field_length():
    with record_job_run("chatty_job") as run:
        run["summary"] = "x" * 500

    assert len(JobRun.objects.get().summary) == 300


@pytest.mark.django_db
def test_generate_alerts_records_a_job_run():
    call_command("generate_alerts")

    job = JobRun.objects.get(command="generate_alerts")
    assert job.result == JobRun.RESULT_OK
    assert "alerts" in job.summary


@pytest.mark.django_db
def test_backup_records_a_job_run(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKUPS_DIR", str(tmp_path))
    source = tmp_path / "source.sqlite3"
    source.write_bytes(b"sqlite test database")
    monkeypatch.setitem(settings.DATABASES["default"], "NAME", str(source))

    call_command("backup")

    job = JobRun.objects.get(command="backup")
    assert job.result == JobRun.RESULT_OK
    assert job.summary.endswith("bytes)")


@pytest.mark.django_db
def test_backup_failure_is_recorded_as_error(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKUPS_DIR", str(tmp_path))
    monkeypatch.setitem(
        settings.DATABASES["default"], "NAME", str(tmp_path / "missing.sqlite3")
    )

    with pytest.raises(FileNotFoundError):
        call_command("backup")

    job = JobRun.objects.get(command="backup")
    assert job.result == JobRun.RESULT_ERROR
    assert "FileNotFoundError" in job.summary


@pytest.mark.django_db
def test_a_job_is_running_until_it_finishes():
    """V.7: the row used to be created with result="ok" before executing, so a
    killed process left a permanent false success."""
    with record_job_run("observable_job") as run:
        mid_flight = JobRun.objects.get()
        assert mid_flight.result == JobRun.RESULT_RUNNING
        assert mid_flight.finished_at is None
        run["summary"] = "done"

    assert JobRun.objects.get().result == JobRun.RESULT_OK


@pytest.mark.django_db
def test_a_dead_job_stays_detectable():
    """Simulate the process dying without a Python exception: nothing after
    the create runs. What remains must not read as success."""
    try:
        with record_job_run("killed_job"):
            raise KeyboardInterrupt  # closest simulation of an external kill
    except KeyboardInterrupt:
        pass

    job = JobRun.objects.get()
    # KeyboardInterrupt is not an Exception, so neither branch ran: the row
    # keeps the state it had when the process vanished.
    assert job.result == JobRun.RESULT_RUNNING
    assert job.finished_at is None
