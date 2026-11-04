"""LV-418: un fallo SMTP en un centro no corta el resumen de los demás.

`message.send()` corría dentro del ciclo por centro de costo sin manejar errores:
el primer error de SMTP abortaba el comando y el resto de los centros se quedaba
sin aviso. Ahora cada fallo se registra, el ciclo sigue, y al final el comando
falla (el `JobRun` queda en error y lo ve el vigilante). Sin registro de
«enviado»: reintentar puede duplicar, decisión tomada.
"""

import smtplib

import pytest
from django.core import mail
from django.core.mail import EmailMultiAlternatives
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.compliance.test_alert_digest import _qualification, cost_center  # noqa: F401
from apps.core.models import JobRun
from apps.registry.models import CostCenter

pytestmark = pytest.mark.django_db

BAD = "caido@example.test"


@pytest.fixture(autouse=True)
def _outbox(settings):
    settings.MAILERS = {
        "default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}
    }


@pytest.fixture
def two_centers(cost_center):  # noqa: F811
    cost_center.responsible_operator = None
    cost_center.responsible_contact_email = BAD
    cost_center.save(
        update_fields=["responsible_operator", "responsible_contact_email"]
    )
    other = CostCenter.objects.create(
        code="FAENA-02",
        name="Faena Sur",
        responsible_contact_email="sur@example.test",
    )
    _qualification(cost_center, 3, "Norte")
    _qualification(other, 3, "Sur")
    return cost_center, other


def _fail_for_bad_address(monkeypatch):
    real_send = EmailMultiAlternatives.send

    def send(self, *args, **kwargs):
        if BAD in self.to:
            raise smtplib.SMTPException("boom")
        return real_send(self, *args, **kwargs)

    monkeypatch.setattr(EmailMultiAlternatives, "send", send)


def test_one_failing_center_does_not_cut_the_others(two_centers, monkeypatch):
    _fail_for_bad_address(monkeypatch)

    with pytest.raises(CommandError, match="FAENA-01"):
        call_command("send_alert_digest")

    assert [m.to for m in mail.outbox] == [["sur@example.test"]]
    job = JobRun.objects.get(command="send_alert_digest")
    assert job.result == JobRun.RESULT_ERROR


def test_an_os_error_is_handled_the_same_way(two_centers, monkeypatch):
    def send(self, *args, **kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr(EmailMultiAlternatives, "send", send)

    with pytest.raises(CommandError, match="2 digest"):
        call_command("send_alert_digest")


def test_without_failures_the_job_ends_ok(two_centers):
    call_command("send_alert_digest")

    assert len(mail.outbox) == 2
    job = JobRun.objects.get(command="send_alert_digest")
    assert job.result == JobRun.RESULT_OK


def test_credential_notices_survive_one_failure(monkeypatch):
    from datetime import timedelta

    from django.core.mail import EmailMessage
    from django.utils import timezone

    from apps.registry.models import Operator

    soon = timezone.localdate() + timedelta(days=5)
    for n, email in enumerate([BAD, "bueno@example.test"]):
        Operator.objects.create(
            employee_id=f"OP-LV418-{n}",
            full_name=f"Operador {n}",
            email=email,
            credential_expiry=soon,
        )
    real_send = EmailMessage.send

    def send(self, *args, **kwargs):
        if BAD in self.to:
            raise smtplib.SMTPException("boom")
        return real_send(self, *args, **kwargs)

    monkeypatch.setattr(EmailMessage, "send", send)

    with pytest.raises(CommandError, match="1 notice"):
        call_command("notify_expiring_credentials")

    assert [m.to for m in mail.outbox] == [["bueno@example.test"]]
    job = JobRun.objects.get(command="notify_expiring_credentials")
    assert job.result == JobRun.RESULT_ERROR
