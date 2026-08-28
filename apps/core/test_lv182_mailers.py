"""LV-182: la configuración de correo pasa a `MAILERS`, antes de encenderlo.

Django 6.1 deprecó **la familia `EMAIL_*` completa** —once ajustes— en favor de
`MAILERS`, con retiro en 7.0. La migración se hizo **antes** de cargar las
credenciales reales en `p340` y no después, porque configurarlas sobre la API
vieja habría sido hacer el trabajo dos veces.

Tres decisiones que estos tests fijan, y cada una tiene una forma concreta de
fallar si se olvida:

- **Los nombres de las variables de entorno NO cambiaron.** Lo que cambió es
  cómo Django las lee. `/etc/aerocontrol.env` en `p340` es 600 root: un renombre
  habría exigido editarlo a mano en la VM justo cuando se va a encender el
  correo, que es el peor momento para que se pierda una credencial.
- **`OPTIONS` sólo con el backend de SMTP.** `MAILERS` es más estricto que los
  ajustes viejos, que ignoraban en silencio lo que no les correspondía: pasarle
  `host`/`port` al backend de consola levanta `InvalidMailer`. Y el de consola es
  el que corre **hoy** en producción, así que la traducción ingenua habría hecho
  reventar los trabajos nocturnos en vez de imprimir.
- **El diagnóstico lee el entorno, no el mailer.** Con el host vacío el mailer no
  lleva `OPTIONS`, y preguntarle a él diría que la contraseña está vacía aunque
  esté puesta — justo el caso de "la pegué y me olvidé del host", que es el que
  `check_email` existe para distinguir.
"""

import warnings

import pytest
from django.conf import settings
from django.core.mail import mailers
from django.test import override_settings
from django.utils.deprecation import RemovedInDjango70Warning

from apps.core.mail import mail_is_delivered, undelivered_reason

CONSOLE = "django.core.mail.backends.console.EmailBackend"
SMTP = "django.core.mail.backends.smtp.EmailBackend"


def test_the_project_no_longer_defines_the_deprecated_settings():
    """Si vuelven, Django 7.0 se lleva la configuración de correo puesta."""
    from django.conf import DEPRECATED_EMAIL_SETTINGS

    defined = [
        name for name in DEPRECATED_EMAIL_SETTINGS if settings.is_overridden(name)
    ]

    assert defined == [], f"vuelven a definirse ajustes deprecados: {defined}"


def test_the_environment_variable_names_did_not_change():
    """Es lo que deja intacto `/etc/aerocontrol.env` en la VM."""
    from pathlib import Path

    example = (Path(settings.BASE_DIR) / ".env.example").read_text(encoding="utf-8")

    for name in ("EMAIL_HOST", "EMAIL_PORT", "EMAIL_HOST_USER", "EMAIL_HOST_PASSWORD"):
        assert name in example


@override_settings(MAILERS={"default": {"BACKEND": CONSOLE}})
def test_the_console_mailer_can_actually_be_built():
    """El caso de producción hoy. Con `OPTIONS` de SMTP esto sería `InvalidMailer`."""
    # No hace falta vaciar la caché del handler: `override_settings` la reinicia
    # por señal, que es justamente lo que hace fiable escribir estos tests.
    assert type(mailers["default"]).__module__.endswith("console")


@override_settings(
    MAILERS={
        "default": {
            "BACKEND": SMTP,
            "OPTIONS": {"host": "smtp.example.com", "port": 587, "use_tls": True},
        }
    }
)
def test_the_smtp_mailer_takes_its_options():

    connection = mailers["default"]
    assert connection.host == "smtp.example.com"
    assert connection.port == 587


@override_settings(
    MAILERS={"default": {"BACKEND": CONSOLE}},
    MAIL_OPTIONS_FROM_ENV={"host": "", "password": "s3cret", "port": 587},
)
def test_a_password_without_a_host_is_still_reported_as_present():
    """ "La pegué y me olvidé del host": decir que está vacía sería mentir."""
    assert not mail_is_delivered()
    assert "EMAIL_HOST no está configurado" in undelivered_reason()


@override_settings(
    MAILERS={"default": {"BACKEND": CONSOLE}},
    MAIL_OPTIONS_FROM_ENV={"host": "smtp.example.com", "password": "", "port": 587},
)
def test_a_host_with_a_hand_set_backend_gets_the_other_advice():
    """Repetir "falta EMAIL_HOST" mandaría a revisar una variable que ya está bien."""
    reason = undelivered_reason()

    assert "EMAIL_BACKEND" in reason
    assert "EMAIL_HOST no está configurado" not in reason


@pytest.mark.django_db
def test_sending_does_not_raise_a_deprecation_warning():
    """La prueba de que la migración sirvió: el aviso desaparece del camino real."""
    from django.core.mail import EmailMessage

    with warnings.catch_warnings():
        warnings.simplefilter("error", RemovedInDjango70Warning)
        EmailMessage(subject="x", body="y", to=["a@b.cl"]).send()
