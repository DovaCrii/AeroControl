"""Guardia global de pruebas (LV-353): ninguna prueba sale a Internet.

`WEATHER_ENABLED` está encendido por omisión, así que una prueba que llegue al cliente del
tiempo sin sustituirlo intentaría una llamada real a Open-Meteo. Este fixture hace que
`urlopen` falle fuerte; las pruebas que necesitan un `urlopen` falso lo reemplazan con su
propio `monkeypatch` (corre después de este) y las que usan el fixture del cliente no llegan.
"""

import urllib.request

import pytest
from django.utils import translation


@pytest.fixture(autouse=True)
def _reset_active_language():
    """Cada prueba parte (y termina) con el idioma por omisión del proyecto.

    `LocaleMiddleware` activa el idioma de la petición en el hilo y nadie lo desactiva, así que
    una prueba con `Accept-Language: en` dejaba el hilo en inglés para la siguiente del mismo
    worker. Con `-n auto` el orden cambia entre corridas: la prueba que afirma texto en español
    sin cliente (LV-287, «día anterior») fallaba sólo a veces (LV-414).
    """
    translation.deactivate()
    yield
    translation.deactivate()


@pytest.fixture(autouse=True)
def _no_outgoing_http(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError(
            "una prueba intentó salir a Internet (urllib.request.urlopen)"
        )

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
