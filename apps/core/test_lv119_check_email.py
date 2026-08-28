"""LV-119: `check_email` prueba el envío, no la configuración.

La mitad de detectar la resolvió `apps/core/mail.py` el 2026-08-20 (que la app
no diga "Sent" cuando imprimió). Ésta es la otra mitad, y la que hacía falta
para desbloquear el correo en `p340`: un comando que **abre la conexión** y, si
se le da un destinatario, **envía de verdad**.

Cada camino de error tiene su test, y no por completitud: el mensaje de error es
el producto. Quien lo lee está en una sesión SSH intentando averiguar qué
variable escribir, y "SMTPAuthenticationError" a secas no le dice ninguna.
"""

import smtplib

import pytest
from django.conf import settings
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

CONSOLE = "django.core.mail.backends.console.EmailBackend"
LOCMEM = "django.core.mail.backends.locmem.EmailBackend"
MODULE = "apps.core.management.commands.check_email"


def _mail(backend, *, host="", password="", use_tls=True, use_ssl=False):
    """Los dos ajustes que reemplazan a la familia `EMAIL_*`. LV-182.

    Django 6.1 la deprecó entera en favor de `MAILERS`, así que los tests
    configuran lo mismo que configura `base.py`: el mailer y **la foto del
    entorno**, que son cosas distintas a propósito — con el host vacío el mailer
    no lleva `OPTIONS` ninguna (pasárselas al backend de consola levanta
    `InvalidMailer`) y el informe igual tiene que poder decir que la contraseña
    está puesta. Ése es el caso de "la pegué y me olvidé del host".
    """
    options = {
        "host": host,
        "port": 587,
        "username": "",
        "password": password,
        "use_ssl": use_ssl,
        "use_tls": use_tls,
        "timeout": 20,
    }
    mailer = {"BACKEND": backend}
    if backend == "django.core.mail.backends.smtp.EmailBackend":
        mailer["OPTIONS"] = options
    return {"MAILERS": {"default": mailer}, "MAIL_OPTIONS_FROM_ENV": options}


class _Connection:
    """Un backend de correo que falla al abrir, con la excepción que se le pida."""

    def __init__(self, error):
        self.error = error
        self.closed = False

    def open(self):
        raise self.error

    def close(self):
        self.closed = True


# -- el caso que existe hoy en producción ----------------------------------


@override_settings(**_mail(CONSOLE))
def test_it_refuses_when_the_backend_only_prints(capsys):
    """El estado real de `p340` y la primera corrida esperable del comando.

    Sin esta comprobación el resto "funcionaría": el backend de consola abre y
    envía sin error, y el comando terminaría en verde sobre el tubo cortado --
    que es exactamente el defecto que LV-119 vino a arreglar.
    """
    with pytest.raises(CommandError) as failure:
        call_command("check_email")

    assert "EMAIL_HOST" in str(failure.value)
    assert "LV-119" in str(failure.value)
    # Y aun así alcanzó a informar la configuración: es lo que hay que mirar
    # para arreglarlo.
    assert "EMAIL_BACKEND" in capsys.readouterr().out


@override_settings(**_mail(CONSOLE, password="s3cr3t-de-verdad"))
def test_the_password_is_never_printed(capsys):
    """Un comando de runbook que escupe una contraseña al journal crea un
    problema nuevo mientras diagnostica el viejo. El largo sí se informa: es lo
    que distingue "no la pegué" de "la pegué con un salto de línea de más"."""
    with pytest.raises(CommandError):
        call_command("check_email")

    output = capsys.readouterr().out
    assert "s3cr3t-de-verdad" not in output
    assert "(16 caracteres)" in output


# -- camino feliz ----------------------------------------------------------


@override_settings(**_mail(LOCMEM, host="smtp.example.com"))
def test_without_a_recipient_it_stops_after_the_connection(capsys):
    """Enviar exige un `--to` explícito. Un destinatario por omisión pondría un
    mensaje de prueba delante de Dirección, y no probar el envío en silencio
    dejaría creer que se probó: el comando dice qué quedó sin probar."""
    mail.outbox.clear()

    call_command("check_email")

    output = capsys.readouterr().out
    assert "Conexión abierta" in output
    assert "envío NO probado" in output
    assert mail.outbox == []


@override_settings(**_mail(LOCMEM, host="smtp.example.com"))
def test_with_a_recipient_it_sends_a_real_message(capsys):
    mail.outbox.clear()

    call_command("check_email", "--to", "cmunoz@jej.cl", "--to", "aortega@jej.cl")

    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.to == ["cmunoz@jej.cl", "aortega@jej.cl"]
    assert "prueba de correo saliente" in message.subject
    assert settings.MAIL_OPTIONS_FROM_ENV["host"] in message.body
    assert "Enviado a cmunoz@jej.cl, aortega@jej.cl" in capsys.readouterr().out


@override_settings(**_mail(LOCMEM, host="smtp.example.com"))
def test_a_blank_recipient_is_not_a_recipient(capsys):
    """`--to ""` desde un script mal armado no debe mandar un correo sin
    destinatario, que el backend acepta y nadie recibe."""
    mail.outbox.clear()

    call_command("check_email", "--to", "  ")

    assert mail.outbox == []
    assert "envío NO probado" in capsys.readouterr().out


# -- caminos de error, uno por variable que hay que revisar ----------------


@override_settings(**_mail(LOCMEM, host="smtp.example.com"))
def test_an_authentication_failure_names_the_credentials(monkeypatch):
    error = smtplib.SMTPAuthenticationError(535, b"5.7.139 Authentication failed")
    monkeypatch.setattr(MODULE + ".mailers", {"default": _Connection(error)})

    with pytest.raises(CommandError) as failure:
        call_command("check_email")

    message = str(failure.value)
    assert "EMAIL_HOST_USER" in message
    assert "EMAIL_HOST_PASSWORD" in message
    # El caso real más frecuente en un buzón corporativo con MFA.
    assert "contraseña de aplicación" in message


@override_settings(**_mail(LOCMEM, host="smtp.example.com"))
def test_an_unreachable_host_names_the_network_variables(monkeypatch):
    """Host inexistente, puerto cerrado por el firewall, timeout o TLS mal
    elegido llegan todos como OSError, y todos se arreglan en el entorno."""
    error = TimeoutError("timed out")
    monkeypatch.setattr(MODULE + ".mailers", {"default": _Connection(error)})

    with pytest.raises(CommandError) as failure:
        call_command("check_email")

    message = str(failure.value)
    assert "smtp.example.com:587" in message
    assert "EMAIL_PORT" in message
    assert "firewall" in message


@override_settings(**_mail(LOCMEM, host="smtp.example.com"))
def test_an_smtp_level_refusal_is_reported_with_its_class(monkeypatch):
    error = smtplib.SMTPConnectError(421, b"service not available")
    monkeypatch.setattr(MODULE + ".mailers", {"default": _Connection(error)})

    with pytest.raises(CommandError) as failure:
        call_command("check_email")

    assert "SMTPConnectError" in str(failure.value)


@override_settings(
    **_mail(LOCMEM, host="smtp.example.com"), DEFAULT_FROM_EMAIL="aerocontrol@jej.cl"
)
def test_a_refused_sender_explains_the_relay_case(monkeypatch):
    """La falla típica de un buzón recién creado: autentica y no tiene permiso
    para retransmitir con esa dirección. Abrir la conexión no la detecta, así
    que sólo aparece al enviar -- y por eso el envío es un paso propio."""
    from django.core.mail import EmailMessage

    error = smtplib.SMTPSenderRefused(
        550,
        b"5.7.60 Client does not have permission to send as this sender",
        "aerocontrol@jej.cl",
    )

    def refuse(self, fail_silently=False):
        raise error

    monkeypatch.setattr(EmailMessage, "send", refuse)

    with pytest.raises(CommandError) as failure:
        call_command("check_email", "--to", "cmunoz@jej.cl")

    message = str(failure.value)
    assert "aerocontrol@jej.cl" in message
    assert "DEFAULT_FROM_EMAIL" in message


@override_settings(**_mail(LOCMEM, host="smtp.example.com"))
def test_a_backend_that_accepts_and_discards_is_a_failure(monkeypatch):
    """`send()` devuelve cuántos entregó. Un 0 sin excepción es un backend que
    aceptó y descartó, y terminar en verde ahí sería el mismo error de LV-119
    con otra cara."""
    from django.core.mail import EmailMessage

    monkeypatch.setattr(EmailMessage, "send", lambda self, fail_silently=False: 0)

    with pytest.raises(CommandError) as failure:
        call_command("check_email", "--to", "cmunoz@jej.cl")

    assert "no entregó ningún mensaje" in str(failure.value)


# -- la configuración que hace posible el envío ----------------------------


def test_tls_and_ssl_are_never_both_on():
    """Django las rechaza juntas con un ValueError **al enviar**, o sea en
    producción, de noche, dentro del trabajo programado. `EMAIL_USE_TLS` deja de
    ser el valor por omisión cuando alguien pide SSL, así que un 465 con SSL es
    una configuración legítima que no exige además apagar TLS a mano."""
    options = settings.MAIL_OPTIONS_FROM_ENV
    assert not (options["use_tls"] and options["use_ssl"])


def test_every_mail_variable_is_documented_in_the_env_example():
    """Las credenciales las pega una persona en el entorno del servidor, así que
    la lista de qué pegar tiene que estar donde se busca."""
    from pathlib import Path

    example = (Path(settings.BASE_DIR) / ".env.example").read_text(encoding="utf-8")

    for name in (
        "EMAIL_HOST",
        "EMAIL_PORT",
        "EMAIL_HOST_USER",
        "EMAIL_HOST_PASSWORD",
        "EMAIL_USE_TLS",
        "EMAIL_USE_SSL",
        "DEFAULT_FROM_EMAIL",
    ):
        assert name in example, name
