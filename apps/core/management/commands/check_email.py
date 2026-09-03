"""LV-119: probar que el correo sale de la máquina, no suponerlo.

`p340` corrió meses con `EMAIL_HOST` vacío y **nada lo dijo**: `manage.py check`
pasaba, `check_digest_recipients` respondía razonable —pregunta por los
destinatarios, no por el transporte— y los nueve trabajos de notificación
terminaban en `Sent ... to N recipient(s)` mientras el correo se imprimía en el
journal. `apps/core/mail.py` cerró la mitad de detectar; ésta es la otra mitad:
un comando que **abre la conexión** en vez de leer la configuración.

Los tres niveles de prueba, en orden, porque cada uno puede fallar solo:

1. **La configuración se lee.** Es lo único que probaba `manage.py check`, y es
   lo que menos dice: con las variables vacías Django elige el backend de
   consola y todo parece bien.
2. **La conexión se abre y las credenciales se aceptan.** Acá se cae un host
   equivocado, un puerto cerrado por el firewall, un TLS mal elegido o una
   contraseña vencida. Es lo que el comando hace siempre.
3. **El servidor acepta un mensaje real.** Un servidor puede autenticar y aun
   así negarse a *retransmitir* con esa dirección de remitente, que es la falla
   típica de un buzón corporativo recién creado. Esto sólo se prueba enviando,
   así que exige un `--to` explícito.

La salida va en español y sin `gettext`, como el resto de `apps/core/mail.py`:
la lee un operador en una sesión SSH, no un usuario en la interfaz.
"""

import smtplib

from django.conf import settings
from django.core.mail import EmailMessage, mailers
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.core.mail import mail_is_delivered, undelivered_reason


class Command(BaseCommand):
    help = (
        "Report the mail configuration and prove that sending actually works "
        "(opens the SMTP connection; with --to, sends a real test message)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--to",
            action="append",
            default=[],
            metavar="ADDRESS",
            help=(
                "Send a test message to this address (repeatable). Without it "
                "the command stops after the connection test."
            ),
        )

    def handle(self, *args, **options):
        self._report_configuration()

        # Sin esto el resto del comando "funcionaría": el backend de consola
        # abre y envía sin error, y el comando terminaría en verde sobre el
        # tubo cortado -- exactamente el defecto que LV-119 vino a arreglar.
        if not mail_is_delivered():
            raise CommandError(undelivered_reason())

        self._open_connection()
        recipients = [address for address in options["to"] if address.strip()]
        if not recipients:
            self.stdout.write(
                self.style.WARNING(
                    "Conexión probada, envío NO probado. Un servidor puede "
                    "aceptar las credenciales y negarse a retransmitir con "
                    f"remitente {settings.DEFAULT_FROM_EMAIL}; para probarlo "
                    "hace falta enviar de verdad:\n"
                    "  python manage.py check_email --to alguien@jej.cl"
                )
            )
            return
        self._send(recipients)

    # -- 1. la configuración ------------------------------------------------

    def _report_configuration(self):
        # LV-182: los ajustes `EMAIL_*` ya no existen — Django 6.1 los deprecó y
        # 7.0 los elimina. **Los rótulos siguen diciendo `EMAIL_HOST` y compañía
        # a propósito**: son los nombres de las **variables de entorno**, que no
        # cambiaron, y este comando existe para que alguien frente al servidor
        # sepa qué variable tocar. Rotularlo "host" a secas lo dejaría buscando
        # en `/etc/aerocontrol.env` una clave que no existe.
        #
        # **Se informa lo que hay en el entorno, no lo que Django armó**, y la
        # diferencia importa: con `EMAIL_HOST` vacío el backend es el de consola
        # y `MAILERS` no lleva `OPTIONS` ninguna, así que leer de ahí diría que
        # la contraseña está vacía **aunque esté puesta** — justo el caso de "la
        # pegué y me olvidé del host", que este informe existe para distinguir.
        # El backend sí sale de `MAILERS`, porque es lo que Django resolvió.
        options = settings.MAIL_OPTIONS_FROM_ENV
        password = options["password"]
        rows = [
            ("EMAIL_BACKEND", settings.MAILERS["default"]["BACKEND"]),
            ("EMAIL_HOST", options["host"] or "(vacío)"),
            ("EMAIL_PORT", options["port"]),
            ("EMAIL_HOST_USER", options["username"] or "(vacío)"),
            # **Nunca el valor.** Un comando de runbook que escupe una
            # contraseña al journal crea un problema nuevo mientras diagnostica
            # el viejo. El largo alcanza para distinguir "no la pegué" de "la
            # pegué con un salto de línea de más".
            (
                "EMAIL_HOST_PASSWORD",
                f"({len(password)} caracteres)" if password else "(vacío)",
            ),
            ("EMAIL_USE_TLS", options["use_tls"]),
            ("EMAIL_USE_SSL", options["use_ssl"]),
            ("EMAIL_TIMEOUT", options["timeout"]),
            ("DEFAULT_FROM_EMAIL", settings.DEFAULT_FROM_EMAIL),
        ]
        width = max(len(name) for name, _value in rows)
        self.stdout.write("Configuración de correo:")
        for name, value in rows:
            self.stdout.write(f"  {name.ljust(width)}  {value}")

    # -- 2. la conexión -----------------------------------------------------

    def _smtp_target(self):
        """`host:puerto`, o el aviso de que no hay SMTP configurado.

        LV-182: con `MAILERS`, un backend que no es el de SMTP **no tiene**
        `host` ni `port` — antes existían igual como ajustes globales aunque no
        se usaran. Devolver aquí un `:None` sería peor que decirlo.
        """
        options = settings.MAIL_OPTIONS_FROM_ENV
        if not options["host"]:
            return "(sin SMTP configurado)"
        return f"{options['host']}:{options['port']}"

    def _open_connection(self):
        # LV-182: `mailers["default"]` en vez de `get_connection()`, que Django
        # 6.1 deprecó. Es el mismo objeto de backend; lo que cambia es de dónde
        # sale su configuración.
        connection = mailers["default"]
        try:
            connection.open()
        except smtplib.SMTPAuthenticationError as error:
            raise CommandError(
                "El servidor aceptó la conexión y **rechazó las credenciales**: "
                f"{error.smtp_code} {error.smtp_error!r}. Revisá "
                "EMAIL_HOST_USER / EMAIL_HOST_PASSWORD en el entorno del "
                "servicio; si el buzón usa MFA hace falta una contraseña de "
                "aplicación, no la del usuario."
            ) from error
        except smtplib.SMTPException as error:
            raise CommandError(
                f"El servidor SMTP rechazó la conexión: {type(error).__name__}: {error}"
            ) from error
        except OSError as error:
            # Host inexistente, puerto cerrado por el firewall, timeout, TLS
            # mal elegido: todos llegan por acá y todos se arreglan en el
            # entorno, así que el mensaje nombra las variables.
            raise CommandError(
                f"No se pudo llegar a {self._smtp_target()} "
                f"-- {type(error).__name__}: {error}. Revisá EMAIL_HOST, "
                "EMAIL_PORT y EMAIL_USE_TLS / EMAIL_USE_SSL, y que el firewall "
                "del servidor deje salir ese puerto."
            ) from error
        else:
            connection.close()
        self.stdout.write(
            self.style.SUCCESS(
                f"Conexión abierta con {self._smtp_target()} y credenciales aceptadas."
            )
        )

    # -- 3. el envío --------------------------------------------------------

    def _send(self, recipients):
        stamp = timezone.localtime().strftime("%Y-%m-%d %H:%M:%S")
        message = EmailMessage(
            subject=f"AeroControl: prueba de correo saliente ({stamp})",
            body=(
                "Este mensaje lo envió `manage.py check_email` para comprobar "
                "que el correo saliente de AeroControl funciona.\n\n"
                f"Servidor: {self._smtp_target()}\n"
                f"Remitente: {settings.DEFAULT_FROM_EMAIL}\n"
                f"Fecha: {stamp}\n\n"
                "Si recibiste esto, las nueve notificaciones de la aplicación "
                "pueden llegar por el mismo camino."
            ),
            to=recipients,
        )
        try:
            delivered = message.send(fail_silently=False)
        except smtplib.SMTPRecipientsRefused as error:
            raise CommandError(
                f"El servidor rechazó los destinatarios: {error.recipients}."
            ) from error
        except smtplib.SMTPSenderRefused as error:
            raise CommandError(
                f"El servidor rechazó el remitente {settings.DEFAULT_FROM_EMAIL}: "
                f"{error.smtp_code} {error.smtp_error!r}. Es la falla típica de "
                "un buzón que autentica pero no tiene permiso para retransmitir "
                "con esa dirección; suele arreglarse poniendo DEFAULT_FROM_EMAIL "
                "igual a EMAIL_HOST_USER."
            ) from error
        except (smtplib.SMTPException, OSError) as error:
            raise CommandError(
                f"El envío falló: {type(error).__name__}: {error}"
            ) from error

        # `send()` devuelve cuántos mensajes entregó. Un 0 sin excepción es un
        # backend que aceptó y descartó, y terminar en verde ahí sería el mismo
        # error de LV-119 con otra cara.
        if not delivered:
            raise CommandError(
                "El backend no entregó ningún mensaje y tampoco falló. "
                f"Revisá EMAIL_BACKEND={settings.MAILERS['default']['BACKEND']}."
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"Enviado a {', '.join(recipients)}. Confirmá que llegó a la "
                "bandeja (y revise la carpeta de correo no deseado): el "
                "servidor lo aceptó, que no es lo mismo que entregado."
            )
        )
