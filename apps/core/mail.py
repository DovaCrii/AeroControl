"""¿El correo de esta app sale de la máquina, o sólo se imprime?

LV-119 (2026-08-20). Durante meses `p340` corrió con `EMAIL_HOST` vacío. Django
cae entonces al backend de consola —decisión deliberada de `B2.1`, para que un
despliegue mal configurado imprima el correo en vez de perderlo en silencio— y
cada trabajo de notificación siguió terminando en `Sent ... to N recipient(s)`.
O sea que **la app afirmaba haber enviado lo que solamente imprimió**, y el
informe ejecutivo completo, con su XLSX en base64, quedaba escrito en el journal
de systemd.

Se descubrió porque el usuario pegó la salida de
`journalctl -u aerocontrol-executive.service` y ahí estaba el MIME crudo seguido
de la línea de 79 guiones que escribe `console.EmailBackend`. Nada en la app lo
decía: `check_digest_recipients` (que existe justo para adelantarse a un
destinatario inalcanzable) responde sobre **los destinatarios** y no sobre el
transporte, así que salía razonable con el tubo cortado.

Este módulo es la respuesta a "quién avisa que nadie está avisando".
"""

from django.conf import settings

# Los backends que **no entregan**: consola imprime, filebased escribe a disco,
# dummy descarta. Los tres son legítimos en desarrollo y ninguno sirve en
# producción.
#
# `locmem` queda deliberadamente **fuera** de la lista, y no por descuido:
# Django lo instala él mismo durante los tests (`setup_test_environment`), donde
# la entrega se verifica con `mail.outbox`. Incluirlo haría que toda la suite
# corriera con la advertencia encendida, que es la forma más rápida de que un
# aviso deje de significar algo.
UNDELIVERED_BACKENDS = (
    "django.core.mail.backends.console.EmailBackend",
    "django.core.mail.backends.filebased.EmailBackend",
    "django.core.mail.backends.dummy.EmailBackend",
)

# Prefijo del resumen de `JobRun`, que es lo que muestran el centro de
# administración y el historial de trabajos. Va **adelante** para que se lea en
# una columna angosta sin abrir la fila.
UNDELIVERED_SUMMARY_PREFIX = "NO ENVIADO (correo sin configurar) · "


def mail_is_delivered():
    """True si el backend configurado entrega de verdad."""
    return settings.EMAIL_BACKEND not in UNDELIVERED_BACKENDS


def undelivered_reason():
    """Por qué no se entrega, en una línea, o `""` si sí se entrega.

    Nombra **la variable que falta**, no el backend: quien lee esto en un log a
    las 3 AM necesita saber qué escribir en `/etc/aerocontrol.env`, no cómo se
    llama la clase de Python que Django eligió por él.
    """
    if mail_is_delivered():
        return ""
    if not settings.EMAIL_HOST:
        return (
            "EMAIL_HOST no está configurado, así que el correo se imprime en el "
            "log en vez de enviarse (LV-119). Falta EMAIL_HOST / EMAIL_PORT / "
            "EMAIL_HOST_USER / EMAIL_HOST_PASSWORD / DEFAULT_FROM_EMAIL en el "
            "entorno."
        )
    # EMAIL_HOST puesto y aun así un backend que no entrega: alguien fijó
    # EMAIL_BACKEND a mano. Decirlo tal cual, porque el consejo de arriba no
    # aplica y repetirlo mandaría a revisar una variable que ya está bien.
    return (
        f"EMAIL_BACKEND={settings.EMAIL_BACKEND} no entrega correo: se imprime o "
        "se descarta (LV-119), aunque EMAIL_HOST esté configurado."
    )


def warn_undelivered_mail(command):
    """Avisar en la salida del comando que lo que sigue no se va a enviar.

    Se llama al principio de un trabajo que manda correo, **antes** de mandarlo:
    puesto al final quedaría debajo del volcado del propio correo, que en el
    informe ejecutivo son cientos de líneas de base64 — o sea, invisible justo
    en el caso que más importa.

    **Avisa una sola vez por comando**, aunque se llame en un bucle: el digest
    recorre catorce centros de costo, y catorce copias del mismo párrafo son
    ruido que enseña a saltarse el bloque entero. La marca vive en el propio
    objeto del comando, así que no hay estado global que se filtre entre tests.

    Devuelve True si avisó ahora, False si ya había avisado o si sí se entrega.
    """
    if getattr(command, "_undelivered_mail_warned", False):
        return False
    reason = undelivered_reason()
    if not reason:
        return False
    command._undelivered_mail_warned = True
    command.stderr.write(command.style.ERROR(f"CORREO NO ENVIADO: {reason}"))
    return True


def send_verb(dry_run=False):
    """El verbo con que un trabajo cuenta lo que hizo, sin mentir.

    Reemplaza al idioma `'Would send' if dry_run else 'Sent'` que los nueve
    trabajos de notificación repetían: era correcto en la mitad seca y falso en
    la otra, porque "Sent" se imprimía igual con el backend de consola.
    """
    if dry_run:
        return "Would send"
    return "Sent" if mail_is_delivered() else "PRINTED, NOT SENT:"
