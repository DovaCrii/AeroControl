"""LV-267: el escalamiento por carta del mandante llega a alguien.

El informe emitido le dice a la DGAC que *«sin carta, se escala al Gerente de
Operaciones Aéreas»*. `check_client_letters` sólo imprimía, sin timer, sin correo y
sin registro de ejecución: la promesa existía en la salida de un comando que nadie
corría (`p340`, 2026-10-05). Ahora escribe a Dirección **sólo lo que escala** (15
días o menos); los de 45 siguen siendo trabajo del ADC en la bandeja.
"""

from datetime import timedelta
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.core.management import call_command
from django.utils import timezone

from apps.core.groups import REPORT_RECIPIENTS
from apps.core.jobs import WATCHED_JOBS, job_health
from apps.core.models import JobRun
from apps.operations.dossier import PERMIT_LETTER
from apps.operations.test_lv225_lv226_client_letter_chain import (
    _attach,
    _cc,
    _permit,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _outbox(settings):
    settings.MAILERS = {
        "default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}
    }


def _direction(email="gerencia@example.test"):
    user = get_user_model().objects.create_user(email, email=email)
    Group.objects.get_or_create(name=REPORT_RECIPIENTS)[0].user_set.add(user)


def _expiring(days, centre=None):
    today = timezone.localdate()
    return _permit(
        centre or _cc(),
        valid_from=today - timedelta(days=90 - days),
        valid_until=today + timedelta(days=days),
    )


def _run(*args):
    call_command("check_client_letters", *args, stdout=StringIO())


class TestTheMail:
    def test_a_permit_inside_fifteen_days_without_letter_is_mailed(self):
        _direction()
        permit = _expiring(10)

        _run()

        assert [m.to for m in mail.outbox] == [["gerencia@example.test"]]
        assert permit.internal_folio in mail.outbox[0].body

    def test_the_link_opens_the_permit(self):
        _direction()
        permit = _expiring(10)

        _run()

        assert f"/operations/permissions/{permit.pk}/" in mail.outbox[0].body

    def test_forty_days_out_is_the_adc_job_and_is_not_mailed(self):
        _direction()
        _expiring(40)

        _run()

        assert mail.outbox == []

    def test_with_the_letter_nothing_is_mailed(self):
        _direction()
        _attach(_expiring(10), PERMIT_LETTER)

        _run()

        assert mail.outbox == []

    def test_nothing_to_escalate_stays_silent(self):
        _direction()

        _run()

        assert mail.outbox == []

    def test_dry_run_sends_nothing(self):
        _direction()
        _expiring(10)

        _run("--dry-run")

        assert mail.outbox == []

    def test_without_recipients_it_says_so_instead_of_failing(self):
        _expiring(10)
        out = StringIO()

        call_command("check_client_letters", stdout=out)

        assert mail.outbox == []
        assert REPORT_RECIPIENTS in out.getvalue()


class TestTheWatchdogSeesIt:
    def test_a_run_is_recorded(self):
        _direction()
        _expiring(10)

        _run()

        job = JobRun.objects.get(command="check_client_letters")
        assert job.result == JobRun.RESULT_OK
        assert "1 to escalate" in job.summary

    def test_it_is_a_watched_job_and_reads_never_ran_until_it_does(self):
        assert "check_client_letters" in WATCHED_JOBS
        row = next(r for r in job_health() if r["command"] == "check_client_letters")
        assert row["never_ran"]

        _run()

        row = next(r for r in job_health() if r["command"] == "check_client_letters")
        assert not row["never_ran"] and not row["stale"]
