"""`UX-26` · Instalable, con caché de sólo lectura.

El criterio de la fila, textual: *"en avión o sin señal se puede consultar la
última ficha de aeronave vista"*, marcada claramente como «datos del <fecha>»; y
**nunca se permite escribir sin conexión** — *"un registro de cumplimiento creado
offline y sincronizado tarde es peor que no tenerlo"*.

Esa segunda mitad es la que estos tests vigilan con más ganas, porque es la que
alguien podría "mejorar" sin querer: una cola de escrituras diferidas parece una
funcionalidad y es un defecto de cumplimiento. Un permiso registrado el martes y
sincronizado el jueves llega con la fecha equivocada, después de que alguien ya
decidió creyendo que no existía.

Se afirma sobre los archivos porque ahí vive la conducta: un service worker no se
puede ejercitar desde el cliente de pruebas de Django, y un test que abriera un
navegador mediría el navegador.
"""

import json
import re
from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse

STATIC = Path(settings.BASE_DIR) / "static"
SW = (Path(settings.BASE_DIR) / "templates" / "sw.js").read_text(encoding="utf-8")
PWA = (STATIC / "js" / "pwa.js").read_text(encoding="utf-8")
BASE = (Path(settings.BASE_DIR) / "templates" / "base.html").read_text(encoding="utf-8")


def _without_comments(source):
    """Los comentarios del archivo explican qué **no** se hace y por qué, así que
    buscarlos en el texto crudo encontraría la explicación en vez del código.
    Mismo tropiezo que ya obligó a `without_template_comments` del lado HTML."""
    return "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith("//")
    )


class TestItIsInstallable:
    def test_the_manifest_is_valid_json_with_what_a_browser_needs(self):
        manifest = json.loads(
            (STATIC / "manifest.webmanifest").read_text(encoding="utf-8")
        )

        assert manifest["start_url"] == "/"
        assert manifest["scope"] == "/"
        assert manifest["display"] == "standalone"
        assert manifest["icons"]

    def test_the_page_declares_it(self):
        assert 'rel="manifest"' in BASE
        assert 'name="theme-color"' in BASE

    @pytest.mark.django_db
    def test_the_service_worker_is_served_from_the_root(self, client):
        """⚠️ Y no desde `/static/js/`, que no es preferencia: el alcance de un
        service worker es el directorio del que se descarga, así que desde
        `/static/js/sw.js` sólo podría interceptar peticiones bajo `/static/js/`
        — o sea nada de lo que importa."""
        response = client.get("/sw.js")

        assert response.status_code == 200
        assert reverse("service-worker") == "/sw.js"
        assert response["Content-Type"].startswith("application/javascript")

    @pytest.mark.django_db
    def test_its_cache_is_named_after_the_deploy(self, client):
        """Un nombre nuevo por despliegue es lo que hace que el navegador tire lo
        guardado. Sin eso, quien instaló la aplicación seguiría viendo sin
        conexión la pantalla del despliegue anterior, para siempre."""
        body = client.get("/sw.js").content.decode()

        assert f'"aerocontrol-{settings.SERVICE_WORKER_VERSION}"' in body

    def test_the_version_does_not_depend_on_anyone_remembering_it(self):
        """⚠️ La primera versión de esto era una variable de entorno que el
        despliegue tenía que pasar, y ése es exactamente el tipo de paso que
        `HANDOFF` documenta **después** de que se olvidó: no falla, no avisa, y
        el síntoma aparece semanas más tarde en el teléfono de otra persona.

        Ahora sale de la fecha de `staticfiles.json`, que `collectstatic`
        reescribe en cada corrida — y `collectstatic` ya es obligatorio en este
        proyecto, así que la invalidación viaja con un paso que no se puede
        saltear (sin él las listas dan 500).
        """
        from pathlib import Path

        source = (
            Path(settings.BASE_DIR) / "config" / "settings" / "base.py"
        ).read_text(encoding="utf-8")
        derivation = source.split("def _service_worker_version", 1)[1].split(
            "\nSERVICE_WORKER_VERSION", 1
        )[0]

        assert "staticfiles.json" in derivation
        # La variable de entorno se conserva y gana, para poder forzar la
        # invalidación sin tocar los estáticos.
        assert 'config("SERVICE_WORKER_VERSION"' in derivation

    @pytest.mark.django_db
    def test_the_policy_names_the_worker_and_the_manifest(self, client, db):
        """⚠️ Los dos ya pasarían por herencia —`worker-src` cae en `script-src`
        y `manifest-src` en `default-src`, y los dos valen `'self'`— y se
        escriben igual porque de esa herencia depende que la aplicación funcione
        sin señal. Una directiva heredada se rompe en silencio: el día que
        alguien acote `script-src` para otra cosa, el worker deja de registrarse
        y lo único que se nota es que la copia sin conexión dejó de existir.
        """
        from apps.core.middleware import build_csp

        policy = build_csp("")

        assert "worker-src 'self'" in policy
        assert "manifest-src 'self'" in policy

    @pytest.mark.django_db
    def test_it_is_reachable_without_a_session(self, client):
        """El navegador pide `/sw.js` sin las cookies de la página en algunos
        casos, y un 302 al login registrado como service worker no registra
        nada."""
        assert client.get("/sw.js").status_code == 200


class TestNothingIsEverWrittenOffline:
    """⚠️ La regla que no se negocia."""

    def test_only_get_is_intercepted(self):
        """Todo lo que no sea `GET` va a la red y no se guarda ni se reintenta.
        Sin conexión falla, y falla a la vista."""
        assert 'request.method !== "GET"' in SW
        fetch_handler = SW.split('addEventListener("fetch"', 1)[1]
        # El `return` que suelta la petición viene **antes** de cualquier
        # `respondWith`: si el worker respondiera primero y filtrara después, un
        # `POST` habría pasado por sus manos.
        assert fetch_handler.index('request.method !== "GET"') < fetch_handler.index(
            "respondWith"
        )

    def test_there_is_no_machinery_to_defer_a_write(self):
        """⚠️ Lo que alguien podría agregar creyendo que mejora. Una cola de
        escrituras diferidas parece una funcionalidad y es un defecto de
        cumplimiento: un permiso registrado el martes y sincronizado el jueves
        llega con la fecha equivocada, después de que alguien ya decidió creyendo
        que no existía."""
        for machinery in ("sync", "IndexedDB", "indexedDB", "BackgroundSync", "queue"):
            assert not re.search(rf"\b{machinery}\b", _without_comments(SW)), machinery


class TestTheOfflineCopyIsPlanB:
    def test_the_network_comes_first(self):
        """La caché nunca es el plan A: esta aplicación muestra vencimientos, y
        una pantalla de ayer servida como si fuera de hoy es exactamente el error
        que no puede cometer."""
        assert "networkFirst" in SW
        body = SW.split("async function networkFirst", 1)[1]

        assert body.index("await fetch(request)") < body.index("caches.match")

    def test_a_failed_response_is_not_kept(self):
        """Una 404 guardada se serviría como «la última vez que miraste» cuando
        en realidad es la última vez que fallaste."""
        assert "response.ok" in SW

    def test_credentials_and_the_api_are_never_kept(self):
        never = SW.split("NEVER_CACHE = ", 1)[1].split("]", 1)[0]

        for prefix in ("/admin/", "/accounts/", "/api/"):
            assert prefix in never, prefix

    def test_signing_out_takes_the_cache_with_it(self):
        """La contrapartida de guardar fichas de personas y aeronaves en el
        navegador: en un equipo compartido en faena, cerrar sesión tiene que
        llevarse lo que se vio."""
        assert "aero-clear-cache" in SW
        assert "aero-clear-cache" in PWA
        assert 'form[action*="logout"]' in PWA


class TestTheStaleCopySaysSo:
    def test_the_banner_exists_on_every_page(self):
        assert 'id="offline-banner"' in BASE
        assert "data-stale-label=" in BASE

    def test_it_starts_hidden_both_ways(self):
        """`d-none` además de `hidden`: el atributo pierde contra las utilidades
        de Bootstrap que ponen `display` con `!important` (`LV-209`), y un aviso
        de "sin conexión" dibujado con conexión sería peor que ninguno."""
        banner = BASE.split('id="offline-banner"', 1)[0].rsplit("<div", 1)[1]

        assert "d-none" in banner
        assert "hidden" in BASE.split('id="offline-banner"', 1)[1].split(">", 1)[0]

    def test_the_date_comes_from_the_cache_and_not_from_a_clock(self):
        """⚠️ `sw.js` sella cada respuesta que guarda; `pwa.js` lee ese sello.
        Deducirla de la cabecera `Date` habría dado la hora en que el servidor
        generó la página, que puede ser muy anterior a cuando esta persona la
        miró — y la pregunta que el aviso contesta es «¿de cuándo es lo que estoy
        viendo?», no «¿de cuándo es este HTML?»."""
        assert "X-Aero-Cached-At" in SW
        assert "X-Aero-Cached-At" in PWA

    def test_it_only_speaks_when_the_browser_says_there_is_no_network(self):
        """`navigator.onLine` es optimista en el otro sentido —un `true` no
        garantiza internet— pero un `false` es fiable, y ése es el único caso en
        que esta página pudo haber salido de la caché."""
        assert "navigator.onLine" in PWA

    def test_the_label_is_translated_by_the_server(self):
        from django.utils.translation import activate, gettext

        activate("es")
        message = (
            "No connection. You are looking at data saved on %(when)s; "
            "nothing can be saved until it comes back."
        )

        assert gettext(message) != message
