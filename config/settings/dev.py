from .base import *

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]
# Off in development: AxesStandaloneBackend rejects Client.login() (it has no
# request), which would break the test suite and the local login loop. The
# lockout behaviour is covered by a test that re-enables it explicitly.
AXES_ENABLED = False

# LV-182: Django 6.1 agregó `mail.E001` — un **error** de `check --deploy` cuando
# el mailer por defecto usa un backend de desarrollo. Tiene toda la razón, y en
# producción **se deja encendido a propósito**: es exactamente el defecto que
# `LV-119` documentó, `p340` corriendo meses con el backend de consola mientras
# la app decía "Sent". Que ese chequeo grite ahí es la función, no el estorbo.
#
# Acá se silencia porque en desarrollo el backend de consola **es** la
# configuración correcta —imprimir el digest en la terminal es lo que se quiere—
# y el gate corre `check --deploy` con estos ajustes. Silenciarlo en `base.py`
# habría apagado también la única alarma que avisa del correo mudo en la VM.
SILENCED_SYSTEM_CHECKS = SILENCED_SYSTEM_CHECKS + ["mail.E001"]
