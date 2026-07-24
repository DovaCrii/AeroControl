"""Execution bookkeeping for scheduled management commands."""

import contextlib
import logging

from django.utils import timezone

logger = logging.getLogger("aerocontrol.jobs")

SUMMARY_MAX_LENGTH = 300


@contextlib.contextmanager
def record_job_run(command):
    """Record a JobRun around a command, capturing failures.

    Yields a mutable dict; set `summary` on it to describe the outcome, e.g.

        with record_job_run("generate_alerts") as run:
            run["summary"] = f"{created} alerts"

    A raised exception is recorded as result="error" (with the exception text as
    the summary) and then re-raised, so the command still fails loudly for the
    scheduler while leaving a durable trace.
    """
    from apps.core.models import JobRun

    started = timezone.now()
    state = {"summary": ""}
    job = JobRun.objects.create(
        command=command, started_at=started, result=JobRun.RESULT_OK
    )
    try:
        yield state
    except Exception as exc:
        job.result = JobRun.RESULT_ERROR
        job.summary = f"{type(exc).__name__}: {exc}"[:SUMMARY_MAX_LENGTH]
        job.finished_at = timezone.now()
        job.save(update_fields=["result", "summary", "finished_at", "updated_at"])
        logger.exception(
            "job_failed", extra={"job_command": command, "job_result": "error"}
        )
        raise
    job.summary = str(state.get("summary", ""))[:SUMMARY_MAX_LENGTH]
    job.finished_at = timezone.now()
    job.save(update_fields=["summary", "finished_at", "updated_at"])
    logger.info(
        "job_completed",
        extra={
            "job_command": command,
            "job_result": "ok",
            "job_duration_ms": round(
                (job.finished_at - started).total_seconds() * 1000, 2
            ),
        },
    )
    return
