"""La pantalla de acceso: la ayuda que faltaba, y el bloqueo que no se explicaba.

Sale de la §2.1 del plan UX —que listaba cinco carencias— más dos que aparecieron
al mirar la pantalla y la configuración:

- **El eslogan se imprimía dos veces**, palabra por palabra: en el subtítulo y
  otra vez en el pie, a quince centímetros.
- **El bloqueo devolvía un 403 pelado** mientras el formulario decía "probá de
  nuevo". A los cinco intentos `django-axes` retiene la cuenta **quince minutos**
  por nombre de usuario, así que volver a probar es exactamente lo que no
  funciona — y lo que reinicia la espera.

Lo que más importa acá es lo último: no es decoración, es una pantalla que le
decía a la persona que hiciera lo contrario de lo que le convenía.
"""

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.template.loader import render_to_string
from django.test import Client
from django.urls import reverse
from django.utils import translation

from apps.core.lockout import cooloff_minutes, lockout_response
from apps.core.test_lv207_one_colour_per_section import contrast

CSS = Path(settings.BASE_DIR) / "static" / "css" / "login.css"
TEMPLATE = Path(settings.BASE_DIR) / "templates" / "registration" / "login.html"


class TestTheTaglineIsNotPrintedTwice:
    @pytest.mark.django_db
    def test_the_page_says_it_once(self, client):
        """Estaba en el subtítulo **y** en el pie, palabra por palabra.

        Un pie que repite el subtítulo no agrega nada y gasta el único lugar de
        la tarjeta donde cabía algo útil.

        Se cuenta el texto **renderizado** y no un literal en inglés: el
        `LocaleMiddleware` fija el idioma desde la petición y pisa cualquier
        `translation.override` de acá, así que un literal inglés contaría cero y
        el test pasaría por la razón equivocada — comprobado, fue el primer
        intento.
        """
        body = client.get(reverse("login")).content.decode()
        subtitle = re.search(r'class="login-subtitle">([^<]+)<', body).group(1)

        assert subtitle
        assert body.count(subtitle) == 1


class TestTheHelpThatWasMissing:
    @pytest.mark.django_db
    def test_it_says_what_to_do_when_you_cannot_get_in(self, client):
        """`password_change` existe pero exige estar **dentro**, así que quien
        queda afuera no tiene ningún camino propio."""
        body = client.get(reverse("login")).content.decode()

        assert "login-help" in body

    @pytest.mark.django_db
    def test_without_a_contact_configured_it_names_nobody(self, client, settings):
        """Una dirección inventada manda correo a un buzón que puede no existir,
        y quien queda afuera no se entera de que su pedido no llegó."""
        settings.SUPPORT_CONTACT = ""

        body = client.get(reverse("login")).content.decode()

        assert "@" not in body.split('class="login-help"')[1].split("</div>")[0]

    @pytest.mark.django_db
    def test_with_a_contact_configured_it_names_it(self, client, settings):
        settings.SUPPORT_CONTACT = "soporte@jej.cl"

        body = client.get(reverse("login")).content.decode()

        assert "soporte@jej.cl" in body

    @pytest.mark.django_db
    def test_it_says_which_instance_you_are_signing_in_to(self, client):
        """La demo, el respaldo y producción tienen la misma cara, y cargar
        evidencia en la máquina equivocada es la peor equivocación posible de
        esta pantalla."""
        body = client.get(reverse("login")).content.decode()

        assert "login-where" in body
        assert "testserver" in body


class TestTheLockoutExplainsItself:
    def test_the_wait_comes_from_the_setting_and_not_from_the_html(self, settings):
        """**Por esto es un callable y no `AXES_LOCKOUT_TEMPLATE`.**

        Escrito a mano en el HTML, el plazo se desincroniza en silencio el día
        que alguien cambie el ajuste — y una pantalla que promete quince minutos
        cuando son sesenta es peor que una que no promete nada.
        """
        from datetime import timedelta

        settings.AXES_COOLOFF_TIME = timedelta(minutes=45)

        assert cooloff_minutes() == 45

    def test_a_cooloff_given_in_hours_is_understood(self, settings):
        """`axes` acepta un número suelto y lo interpreta como horas."""
        settings.AXES_COOLOFF_TIME = 2

        assert cooloff_minutes() == 120

    def test_without_a_cooloff_it_promises_nothing(self, settings):
        """Sin `AXES_COOLOFF_TIME` el bloqueo no expira solo. Decir "esperá 0
        minutos" sería mentir en la dirección peligrosa."""
        settings.AXES_COOLOFF_TIME = None

        assert cooloff_minutes() is None

    @pytest.mark.django_db
    def test_the_page_is_a_403_with_the_app_chrome(self, rf):
        """403 y no 200: para un cliente automático y para el registro del proxy
        esto **es** un acceso denegado."""
        response = lockout_response(rf.post("/accounts/login/"))
        body = response.content.decode()

        assert response.status_code == 403
        assert "login-card" in body
        assert "Cuenta retenida" in body or "Account held" in body

    @pytest.mark.django_db
    def test_it_says_the_hold_is_on_the_username_not_the_device(self, rf):
        """Cambiar de máquina es lo primero que alguien intenta, y no sirve:
        `AXES_LOCKOUT_PARAMETERS` es `["username"]`. Decirlo ahorra el intento
        y la llamada."""
        with translation.override("es"):
            body = lockout_response(rf.post("/accounts/login/")).content.decode()

        assert "nombre de usuario" in body
        assert "otro computador" in body

    @pytest.mark.django_db
    def test_it_renders_without_a_request_so_no_context_processor_runs(self):
        """`LV-215` en otro contexto: `render` corre los context processors, y
        el de `compliance` consulta la base y pide `has_perm`. Quien ve esta
        pantalla es justamente alguien **sin** sesión."""
        body = render_to_string(
            "registration/lockout.html",
            {"cooloff_minutes": 15, "support_contact": ""},
        )

        assert "login-card" in body

    @pytest.mark.django_db
    def test_the_real_lockout_reaches_this_page(self, settings):
        """De punta a punta: que `axes` use de verdad el callable configurado.

        Sin esto, los tests de arriba comprobarían una pantalla que nadie llega
        a ver — que es exactamente cómo estaba antes.
        """
        from axes.utils import reset

        from django.contrib.auth.models import User

        User.objects.create_user("bloqueable", password="correcta-123")
        settings.AXES_ENABLED = True
        settings.AXES_FAILURE_LIMIT = 3
        settings.AXES_LOCKOUT_PARAMETERS = ["username"]
        reset()
        client = Client()
        try:
            for _ in range(6):
                response = client.post(
                    reverse("login"),
                    {"username": "bloqueable", "password": "mala"},
                )
                if response.status_code == 403:
                    break

            assert response.status_code == 403
            assert "login-card" in response.content.decode()
        finally:
            reset()


class TestTheButtonKeepsItsContrastInBothThemes:
    """**El motivo por el que el color no se unificó a ciegas.**

    El plan UX proponía reemplazar el `#087f78` escrito a mano por
    `--ac-primary`, y tenía razón en que es el mismo valor... **en tema claro**.
    En oscuro `--ac-primary` vale `#42d4c6`, y blanco sobre ese verde da 1,9:1.
    Así que se unifica el color y el **primer plano** cambia con el tema.

    Se calcula, no se mira: un ratio es aritmética sobre dos colores y el CSS
    los tiene. Es la lección de `LV-207`, donde fiarse de cifras escritas estuvo
    a punto de provocar el "arreglo" de siete colores que cumplían.
    """

    @staticmethod
    def _token(name, dark=False):
        css = CSS.read_text(encoding="utf-8")
        if dark:
            css = css.split('[data-theme="dark"]', 1)[1]
        match = re.search(rf"{name}:\s*([^;]+);", css)
        return match.group(1).strip()

    def test_light_theme_clears_aa(self):
        # `--login-accent` apunta al token de la app; el valor de respaldo es el
        # mismo `#087f78` que `--ac-primary` declara en claro.
        assert contrast("#ffffff", "#087f78") >= 4.5

    def test_dark_theme_clears_aa(self):
        assert contrast("#0d1520", "#42d4c6") >= 4.5

    def test_white_on_the_dark_accent_would_have_failed(self):
        """El error que este diseño evita, escrito para que no se reintroduzca."""
        assert contrast("#ffffff", "#42d4c6") < 4.5

    def test_the_foreground_flips_with_the_theme(self):
        assert self._token("--login-accent-ink") == "#ffffff"
        assert self._token("--login-accent-ink", dark=True) == "#0d1520"


class TestTheCacheBusterIsGone:
    def test_the_stylesheet_link_carries_no_hand_written_version(self):
        """En producción `ManifestStaticFilesStorage` versiona por hash, así que
        `?v=20260724-legibility` no hacía nada — y sugería una política de cache
        que no existe."""
        assert "?v=" not in TEMPLATE.read_text(encoding="utf-8")
