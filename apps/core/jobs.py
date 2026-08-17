"""Execution bookkeeping for scheduled management commands."""

import contextlib
import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger("aerocontrol.jobs")

SUMMARY_MAX_LENGTH = 300

# LV-114: qué trabajos se vigilan y con qué antigüedad se consideran atrasados.
#
# Vivían dentro de `AdministrationView` como atributos de clase. Se extraen acá
# —junto al resto de la contabilidad de trabajos— cuando aparece el segundo
# lector: el vigilante que avisa por correo. El repo extrae **en el segundo
# uso**, y dejarlos en la vista habría significado que un comando importara una
# vista para saber qué vigilar, o peor, que llevara su propia copia de la lista
# y las dos se desincronizaran en silencio.
#
# Las horas son deliberadamente holgadas: 48 para un trabajo diario deja pasar
# una corrida fallida sin gritar, y avisa recién cuando falló dos veces
# seguidas. Un vigilante que avisa al primer tropiezo se termina ignorando, que
# es el modo de fallo que este proyecto ya conoce de las alertas.
DAILY_JOBS = {"generate_alerts": 48, "send_alert_digest": 48, "backup": 48}
WATCHED_JOBS = [
    "generate_alerts",
    "send_alert_digest",
    "backup",
    "send_executive_report",
]


def job_health():
    """[{command, result, when, stale, never_ran}] para cada trabajo vigilado.

    Una sola consulta por comando, que es el mismo costo que tenía dentro de la
    vista. `stale` sólo se calcula para los que tienen antigüedad máxima
    declarada: `send_executive_report` es semanal y medirlo con la vara de un
    diario lo daría por atrasado casi siempre.

    Un trabajo que **nunca corrió** se informa como atrasado y además se marca,
    porque las dos situaciones se arreglan distinto: uno es un timer caído, el
    otro es un timer que nunca se instaló -- y esta app ya pagó esa confusión
    (`AGENTS.md`: "un trabajo programado nunca se registró").
    """
    from apps.core.models import JobRun

    now = timezone.now()
    rows = []
    for command in WATCHED_JOBS:
        run = JobRun.objects.filter(command=command).order_by("-started_at").first()
        max_age = DAILY_JOBS.get(command)
        if run is None:
            rows.append(
                {
                    "command": command,
                    "result": None,
                    "when": None,
                    "stale": True,
                    "never_ran": True,
                }
            )
            continue
        reference = run.finished_at or run.started_at
        rows.append(
            {
                "command": command,
                "result": run.result,
                "when": run.started_at,
                "stale": max_age is not None
                and (now - reference) > timedelta(hours=max_age),
                "never_ran": False,
            }
        )
    return rows


def failing_jobs():
    """Los trabajos vigilados que están atrasados o terminaron en error.

    "Atrasado o en error" es lo que hay que contarle a alguien: un trabajo que
    corrió y falló es tan invisible como uno que no corrió, y hasta ahora los
    dos sólo se veían entrando al centro de administración a mirar.
    """
    from apps.core.models import JobRun

    return [
        row
        for row in job_health()
        if row["stale"] or row["result"] == JobRun.RESULT_ERROR
    ]


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
