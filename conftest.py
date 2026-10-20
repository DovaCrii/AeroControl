"""Guardia global de pruebas (LV-353): ninguna prueba sale a Internet.

`WEATHER_ENABLED` está encendido por omisión, así que una prueba que llegue al cliente del
tiempo sin sustituirlo intentaría una llamada real a Open-Meteo. Este fixture hace que
`urlopen` falle fuerte; las pruebas que necesitan un `urlopen` falso lo reemplazan con su
propio `monkeypatch` (corre después de este) y las que usan el fixture del cliente no llegan.
"""

import urllib.request

import pytest


@pytest.fixture(autouse=True)
def _no_outgoing_http(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError(
            "una prueba intentó salir a Internet (urllib.request.urlopen)"
        )

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
