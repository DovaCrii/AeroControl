"""LV-119: cuando el correo no sale, la app lo dice.

`p340` corrió meses con `EMAIL_HOST` vacío. Django cae entonces al backend de
consola —decisión deliberada de `B2.1`, para que un despliegue mal configurado
imprima el correo en vez de perderlo— y cada trabajo siguió terminando en
`Sent ... to N recipient(s)`. Se descubrió el 2026-08-20 porque el usuario pegó
la salida de `journalctl` y ahí estaba el MIME crudo del informe seguido de la
línea de 79 guiones que escribe `console.EmailBackend`.

Lo que estos tests fijan: que la app **no diga "Sent" cuando imprimió**, que el
resumen del trabajo lo lleve escrito para que el centro de administración no lo
muestre en verde, y —igual de importante— que **calle cuando sí entrega y cuando
no había nada que enviar**. Un aviso que sale todos los días es un aviso que se
aprende a saltar, y este proyecto ya pagó esa lección con las alertas.
"""

import pytest
from django.core.management import call_command
from django.test import override_settings

from apps.core.jobs import record_job_run
from apps.core.mail import (
    UNDELIVERED_SUMMARY_PREFIX,
    mail_is_delivered,
    send_verb,
    undelivered_reason,
)
from apps.core.models import JobRun

CONSOLE = "django.core.mail.backends.console.EmailBackend"
SMTP = "django.core.mail.backends.smtp.EmailBackend"
LOCMEM = "django.core.mail.backends.locmem.EmailBackend"


class TestDetectingTheBackend:
    @override_settings(EMAIL_BACKEND=CONSOLE, EMAIL_HOST="")
    def test_the_console_backend_does_not_deliver(self):
        assert mail_is_delivered() is False

    @override_settings(EMAIL_BACKEND=SMTP, EMAIL_HOST="smtp.example.com")
    def test_smtp_delivers(self):
        assert mail_is_delivered() is True
        assert undelivered_reason() == ""

    @override_settings(EMAIL_BACKEND=LOCMEM, EMAIL_HOST="")
    def test_locmem_counts_as_delivered_on_purpose(self):
        """Django instala `locmem` él mismo durante los tests, donde la entrega
        se verifica con `mail.outbox`. Tratarlo como "no entrega" encendería la
        advertencia en toda la suite, que es la forma más rápida de que un aviso
        deje de significar algo. Este test existe para que nadie lo "arregle"
        agregándolo a la lista."""
        assert mail_is_delivered() is True

    @override_settings(EMAIL_BACKEND=CONSOLE, EMAIL_HOST="")
    def test_the_reason_names_the_missing_variable(self):
        """Quien lee esto en un log necesita saber qué escribir en el entorno,
        no cómo se llama la clase que Django eligió por él."""
        reason = undelivered_reason()
        assert "EMAIL_HOST" in reason
        assert "LV-119" in reason

    @override_settings(EMAIL_BACKEND=CONSOLE, EMAIL_HOST="smtp.example.com")
    def test_a_host_with_a_hand_set_backend_says_so_instead(self):
        """El consejo de "falta EMAIL_HOST" no aplica y repetirlo mandaría a
        revisar una variable que ya está bien."""
        reason = undelivered_reason()
        assert "EMAIL_BACKEND" in reason
        assert "EMAIL_HOST no está configurado" not in reason


class TestTheVerbDoesNotLie:
    @override_settings(EMAIL_BACKEND=SMTP, EMAIL_HOST="smtp.example.com")
    def test_sent_when_it_was_sent(self):
        assert send_verb() == "Sent"

    @override_settings(EMAIL_BACKEND=CONSOLE, EMAIL_HOST="")
    def test_never_the_word_sent_alone_when_it_only_printed(self):
        verb = send_verb()
        assert verb == "PRINTED, NOT SENT:"
        assert not verb.startswith("Sent")

    @override_settings(EMAIL_BACKEND=CONSOLE, EMAIL_HOST="")
    def test_a_dry_run_says_would_send_either_way(self):
        """Un ensayo no envió nada por definición, así que el estado del backend
        no cambia lo que hay que decir -- y decir "no enviado" ahí confundiría
        el ensayo con la falla."""
        assert send_verb(dry_run=True) == "Would send"


class TestTheJobSummaryCarriesIt:
    @pytest.mark.django_db
    @override_settings(EMAIL_BACKEND=CONSOLE, EMAIL_HOST="")
    def test_a_job_that_mailed_is_marked(self):
        with record_job_run("send_alert_digest") as run:
            run["mailed"] = True
            run["summary"] = "1 digests, 3 items, 0 skipped"

        summary = JobRun.objects.get(command="send_alert_digest").summary
        assert summary.startswith(UNDELIVERED_SUMMARY_PREFIX)
        # El resumen original se conserva entero: el prefijo agrega, no tapa.
        assert "1 digests, 3 items, 0 skipped" in summary

    @pytest.mark.django_db
    @override_settings(EMAIL_BACKEND=CONSOLE, EMAIL_HOST="")
    def test_a_job_that_had_nothing_to_send_is_not_marked(self):
        """La mitad que evita el falso positivo: seis de los nueve trabajos
        callan cuando todo está en orden, y marcarlos "no enviado" un día en que
        no había qué enviar sería mentir en la otra dirección."""
        with record_job_run("check_scheduled_jobs") as run:
            run["mailed"] = False
            run["summary"] = "every watched job is current"

        summary = JobRun.objects.get(command="check_scheduled_jobs").summary
        assert not summary.startswith(UNDELIVERED_SUMMARY_PREFIX)
        assert summary == "every watched job is current"

    @pytest.mark.django_db
    @override_settings(EMAIL_BACKEND=SMTP, EMAIL_HOST="smtp.example.com")
    def test_a_delivered_job_is_not_marked(self):
        with record_job_run("send_alert_digest") as run:
            run["mailed"] = True
            run["summary"] = "1 digests"

        assert JobRun.objects.get(command="send_alert_digest").summary == "1 digests"

    @pytest.mark.django_db
    @override_settings(EMAIL_BACKEND=CONSOLE, EMAIL_HOST="")
    def test_a_job_that_does_not_mail_at_all_is_untouched(self):
        """`backup` y `generate_alerts` no mandan correo. Nunca ponen `mailed`,
        así que el estado del backend no puede contaminar su resumen."""
        with record_job_run("backup") as run:
            run["summary"] = "aero_ops_20260820_020000"

        assert (
            JobRun.objects.get(command="backup").summary == "aero_ops_20260820_020000"
        )


class TestEndToEndThroughARealCommand:
    @pytest.mark.django_db
    @override_settings(EMAIL_BACKEND=CONSOLE, EMAIL_HOST="")
    def test_the_executive_report_refuses_to_claim_it_sent(self, capsys):
        """El caso exacto del 2026-08-20: el comando terminaba en `Sent the week
        executive report to 1 recipient(s)` con el correo yendo al journal."""
        call_command("send_executive_report", "--to", "cmunoz@jej.cl")

        captured = capsys.readouterr()
        assert "PRINTED, NOT SENT" in captured.out
        assert "Sent the week executive report" not in captured.out
        assert "CORREO NO ENVIADO" in captured.err
        assert JobRun.objects.get(command="send_executive_report").summary.startswith(
            UNDELIVERED_SUMMARY_PREFIX
        )

    @pytest.mark.django_db
    @override_settings(EMAIL_BACKEND=LOCMEM, EMAIL_HOST="smtp.example.com")
    def test_with_a_working_backend_it_says_sent_and_stays_quiet(self, capsys):
        call_command("send_executive_report", "--to", "cmunoz@jej.cl")

        captured = capsys.readouterr()
        assert "Sent the week executive report to 1 recipient(s)." in captured.out
        assert "PRINTED, NOT SENT" not in captured.out
        assert "CORREO NO ENVIADO" not in captured.err
        assert not JobRun.objects.get(
            command="send_executive_report"
        ).summary.startswith(UNDELIVERED_SUMMARY_PREFIX)

    @pytest.mark.django_db
    @override_settings(EMAIL_BACKEND=CONSOLE, EMAIL_HOST="")
    def test_a_dry_run_does_not_cry_wolf(self, capsys):
        """No compuso correo, así que no hay nada que no se haya enviado."""
        call_command("send_executive_report", "--to", "cmunoz@jej.cl", "--dry-run")

        captured = capsys.readouterr()
        assert "Would send" in captured.out
        assert "CORREO NO ENVIADO" not in captured.err
