"""LV-215: la pantalla del fallo de CSRF.

El usuario se encontró el 403 crudo de Django en producción: dejó la página de
entrada abierta de un día para otro, la envió, y recibió *"La verificación CSRF ha
fallado. Solicitud abortada."* — correcto y sin salida.

**Lo que estos tests protegen es la doble condición**: que la respuesta siga
rechazando el envío (403, nada guardado) *y* que además se pueda leer. Es fácil
arreglar lo segundo aflojando lo primero, y ese sería un retroceso de seguridad
disfrazado de mejora de usabilidad — así que el 403 se afirma explícitamente.
"""

import logging

import pytest
from django.conf import settings
from django.test import Client
from django.urls import reverse

from apps.core.views import csrf_failure


class TestTheResponseStillRejects:
    """Primero lo que no debe cambiar: el envío sigue rechazado."""

    @pytest.mark.django_db
    def test_a_post_without_a_token_gets_a_403(self, client):
        # `enforce_csrf_checks` es lo que hace real la prueba: el cliente de
        # pruebas de Django **desactiva** la comprobación de CSRF por defecto, así
        # que sin esto el POST pasaría y el test no tocaría la vista nunca.
        strict = Client(enforce_csrf_checks=True)

        response = strict.post(reverse("login"), {"username": "x", "password": "y"})

        assert response.status_code == 403

    @pytest.mark.django_db
    def test_the_failure_view_is_the_one_wired_in_settings(self):
        # Si alguien renombra la función, la pantalla desaparece sin que falle
        # nada: Django sólo resuelve esta ruta cuando ya hay un fallo de CSRF.
        assert settings.CSRF_FAILURE_VIEW == "apps.core.views.csrf_failure"


class TestTheScreenCanBeRead:
    @pytest.mark.django_db
    def test_it_says_what_happened_and_what_to_do(self, rf):
        response = csrf_failure(rf.post("/entrar/"), reason="CSRF token missing")

        assert response.status_code == 403
        body = response.content.decode()
        assert "caducó" in body or "caducado" in body
        # Las dos salidas: recargar donde estaba, o entrar de nuevo.
        assert 'href="/entrar/"' in body
        assert settings.LOGIN_URL in body

    @pytest.mark.django_db
    def test_it_offers_to_reload_the_same_path_not_the_home_page(self, rf):
        # Si estaba a mitad de un formulario, recargar **esa** ruta lo devuelve
        # donde estaba con un token nuevo; mandarlo al inicio le pierde el lugar.
        response = csrf_failure(rf.post("/permisos/nuevo/"), reason="")

        assert 'href="/permisos/nuevo/"' in response.content.decode()

    @pytest.mark.django_db
    def test_it_renders_without_a_logged_in_user(self, rf):
        """El caso que motivó la fila: la sesión ya no vale.

        Por eso la plantilla no extiende `base.html`. Si alguien la "ordena"
        haciéndola extender la base, el menú pedirá permisos de un usuario que no
        existe y el 403 se convertirá en un 500 — justo en el peor momento.
        """
        request = rf.post("/entrar/")
        assert not hasattr(request, "user")

        response = csrf_failure(request, reason="")

        assert response.status_code == 403


class TestTheReasonGoesToTheLogNotTheScreen:
    @pytest.mark.django_db
    def test_the_technical_reason_is_logged(self, rf, caplog):
        with caplog.at_level(logging.WARNING, logger="aerocontrol.csrf"):
            csrf_failure(rf.post("/entrar/"), reason="CSRF token from POST incorrect")

        assert "CSRF token from POST incorrect" in caplog.text
        assert "/entrar/" in caplog.text

    @pytest.mark.django_db
    def test_the_technical_reason_is_not_shown_to_the_person(self, rf):
        # Exacto para diagnosticar, ruido para quien mira la pantalla.
        response = csrf_failure(
            rf.post("/entrar/"), reason="CSRF token from POST incorrect"
        )

        assert "CSRF token" not in response.content.decode()
