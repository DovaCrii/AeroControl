"""Execution bookkeeping for scheduled management commands."""

import contextlib
import logging

from django.db import transaction
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

    The row is created as "running" and only flipped to ok/error at the end: a
    process that dies without raising (scheduler kill, power loss) leaves a row
    stuck in "running" with no finished_at, which is detectable, instead of a
    permanent false success.
    """
    from apps.core.models import JobRun

    started = timezone.now()
    state = {"summary": ""}
    job = JobRun.objects.create(
        command=command, started_at=started, result=JobRun.RESULT_RUNNING
    )
    try:
        yield state
    except Exception as exc:
        logger.exception(
            "job_failed", extra={"job_command": command, "job_result": "error"}
        )
        # If the failure was a database error inside an atomic block, that
        # transaction is doomed: saving through it raises
        # TransactionManagementError, which would mask the real exception -
        # and the write would be rolled back with the transaction anyway.
        # The log line above is the durable trace in that case.
        connection = transaction.get_connection()
        if not (connection.in_atomic_block and connection.needs_rollback):
            job.result = JobRun.RESULT_ERROR
            job.summary = f"{type(exc).__name__}: {exc}"[:SUMMARY_MAX_LENGTH]
            job.finished_at = timezone.now()
            job.save(update_fields=["result", "summary", "finished_at", "updated_at"])
        raise
    job.result = JobRun.RESULT_OK
    job.summary = str(state.get("summary", ""))[:SUMMARY_MAX_LENGTH]
    job.finished_at = timezone.now()
    job.save(update_fields=["result", "summary", "finished_at", "updated_at"])
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
