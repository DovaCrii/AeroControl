"""LV-114: alguien se entera cuando un trabajo programado deja de correr.

El centro de administración ya **detectaba** el atraso: lo dibuja en su panel de
situación. Pero hay que entrar a mirarlo, y nadie entra cuando todo parece bien
-- que es justo cuando un timer lleva tres días caído.

`AGENTS.md` lo tiene escrito como lección propia: *"el gate verifica código,
nadie verifica el cableado de producción"*. Detectar estaba resuelto; **contar**
no.

Lo que estos tests fijan, más que el correo: **el silencio también es una
decisión**. Un vigilante que escribe todos los días enseña a archivarlo sin
leerlo, y ahí deja de vigilar.
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import Group, User
from django.core import mail
from django.core.management import call_command
from django.utils import timezone

from apps.core.groups import REPORT_RECIPIENTS
from apps.core.jobs import failing_jobs
from apps.core.models import JobRun

NOW = timezone.now()


@pytest.fixture
def direccion(db):
    group = Group.objects.create(name=REPORT_RECIPIENTS)
    user = User.objects.create_user("jefa", email="jefa@jej.cl", password="pw")
    user.groups.add(group)
    return group


def _run(command, *, when, result=JobRun.RESULT_OK):
    job = JobRun.objects.create(
        command=command, started_at=when, result=result, finished_at=when
    )
    # `started_at` no es auto_now_add en el modelo, pero por las dudas se fija
    # explícitamente: un test que dependa de la hora de creación mediría otra
    # cosa que la que dice medir.
    JobRun.objects.filter(pk=job.pk).update(started_at=when, finished_at=when)
    return job


def _all_current():
    for command in ("generate_alerts", "send_alert_digest", "backup"):
        _run(command, when=NOW - timedelta(hours=2))
    _run("send_executive_report", when=NOW - timedelta(days=6))


@pytest.mark.django_db
class TestWhatCountsAsNeedingAttention:
    def test_a_job_that_never_ran_is_reported_as_such(self):
        """Un timer que nunca se instaló y uno que se cayó se arreglan distinto,
        así que se informan distinto."""
        rows = {row["command"]: row for row in failing_jobs()}

        assert rows["backup"]["never_ran"] is True

    def test_a_stale_job_is_reported(self):
        _all_current()
        JobRun.objects.filter(command="backup").update(
            started_at=NOW - timedelta(days=5), finished_at=NOW - timedelta(days=5)
        )

        assert [row["command"] for row in failing_jobs()] == ["backup"]

    def test_a_job_that_ran_and_failed_is_reported_too(self):
        """Tan invisible como uno que no corrió: termina, deja su rastro de
        error, y nadie lo mira."""
        _all_current()
        JobRun.objects.filter(command="generate_alerts").update(
            result=JobRun.RESULT_ERROR
        )

        assert [row["command"] for row in failing_jobs()] == ["generate_alerts"]

    def test_a_weekly_job_is_not_measured_with_a_daily_yardstick(self):
        """`send_executive_report` corre los lunes: medirlo con las 48 horas de
        un diario lo daría por atrasado casi toda la semana."""
        _all_current()

        assert failing_jobs() == []


@pytest.mark.django_db
class TestWhoFindsOut:
    def test_it_mails_direccion_when_something_needs_attention(self, direccion):
        _all_current()
        JobRun.objects.filter(command="backup").update(
            started_at=NOW - timedelta(days=5), finished_at=NOW - timedelta(days=5)
        )

        call_command("check_scheduled_jobs")

        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == ["jefa@jej.cl"]
        assert "backup" in mail.outbox[0].body

    def test_silence_when_everything_is_current(self, direccion):
        """La mitad que hace que el aviso siga significando algo."""
        _all_current()

        call_command("check_scheduled_jobs")

        assert mail.outbox == []

    def test_dry_run_reports_without_mailing(self, direccion):
        call_command("check_scheduled_jobs", "--dry-run")

        assert mail.outbox == []

    def test_no_recipients_is_said_out_loud_not_counted_as_sent(self, db):
        """El caso exacto que AGENTS.md nombra: la función existía y no llegaba
        a nadie porque el grupo no tenía correos."""
        call_command("check_scheduled_jobs")

        assert mail.outbox == []
        run = JobRun.objects.filter(command="check_scheduled_jobs").first()
        assert run is not None
        assert "mailed" not in run.summary

    def test_it_records_its_own_run(self, direccion):
        _all_current()

        call_command("check_scheduled_jobs")

        run = JobRun.objects.filter(command="check_scheduled_jobs").first()
        assert run.result == JobRun.RESULT_OK
        assert "current" in run.summary


@pytest.mark.django_db
def test_the_admin_panel_and_the_watchdog_read_the_same_source(direccion, client):
    """Extraído de la vista a `core.jobs` justo para esto: dos copias de "qué se
    vigila" se desincronizan en silencio, y así es como un trabajo deja de estar
    vigilado sin que nadie lo note."""
    from apps.core.jobs import WATCHED_JOBS
    from apps.core.views import AdministrationCenterView

    assert not hasattr(AdministrationCenterView, "WATCHED_JOBS")
    assert "generate_alerts" in WATCHED_JOBS
