"""LV-218 paso (a): un enlace a los NOTAM del aeródromo del permiso.

Idea del usuario: *"no sé si existe una forma de cruzar el clima con las NOTAM y
el sector del permiso para informar la situación; si existe una API o algo que
muestre las NOTAM, o buscar dentro de la app"*.

Investigado el 2026-09-01: el IFIS de la DGAC (`aipchile.dgac.gob.cl`) **no tiene
API ni feed** — es Symfony y todo son `GET` con respuesta HTML. Consultar y
parsear es posible (cada NOTAM trae centro y radio en su campo `Q)`), pero el
riesgo es asimétrico: **un parseo que falla se lee como "no hay avisos"**, y esta
fila declaró desde el principio que eso es lo que no puede pasar.

Así que el paso (a) entrega un enlace a la fuente oficial. **Lo que estos tests
protegen es precisamente que la app no afirme nada sobre los NOTAM**: que no
invente un enlace sin aeródromo, y que el texto mande a consultar en vez de
sugerir un resultado.
"""

import pytest
from django.urls import reverse

from apps.core.testing import login_as
from apps.registry.models import Aerodrome, CostCenter

from .models import NOTAM_QUERY_BASE, FlightPermission


@pytest.fixture
def cost_center(db):
    return CostCenter.objects.create(code="CC1", name="Uno", operates_flights=True)


def _permit(cost_center, **extra):
    return FlightPermission.objects.create(
        cost_center=cost_center,
        purpose="photogrammetry",
        status=FlightPermission.STATUS_REQUESTED,
        location="Site",
        area_type="unpopulated",
        **extra,
    )


class TestTheLinkPointsAtTheDeclaredAerodrome:
    @pytest.mark.django_db
    def test_it_uses_the_icao_code_the_permit_already_declares(self, cost_center):
        """La búsqueda del IFIS es por designador, no por coordenadas.

        Por eso se apoya en `amc` (`LV-137`) en vez de inventar una consulta
        geográfica que el sitio no ofrece.
        """
        aerodrome = Aerodrome.objects.create(code="SCEL", name="Arturo Merino Benítez")
        permit = _permit(cost_center, amc=aerodrome, amc_distance_km=12.5)

        assert permit.notam_url.startswith(NOTAM_QUERY_BASE)
        assert "designador=SCEL" in permit.notam_url

    @pytest.mark.django_db
    def test_no_aerodrome_means_no_link(self, cost_center):
        """Sin aeródromo declarado no hay a qué enlazar.

        Mandar a una búsqueda vacía sería peor que no ofrecer el enlace: quien la
        abriera vería una pantalla sin resultados y podría leerla como "no hay
        NOTAM para este permiso", que es lo contrario de lo que dice.
        """
        assert _permit(cost_center).notam_url is None

    @pytest.mark.django_db
    def test_a_blank_code_means_no_link_either(self, cost_center):
        aerodrome = Aerodrome.objects.create(code="   ", name="Sin código")
        permit = _permit(cost_center, amc=aerodrome, amc_distance_km=3)

        assert permit.notam_url is None

    @pytest.mark.django_db
    def test_the_code_is_url_encoded(self, cost_center):
        """Un designador con espacio no puede armar una URL rota."""
        aerodrome = Aerodrome.objects.create(code="SC EL", name="Con espacio")
        permit = _permit(cost_center, amc=aerodrome, amc_distance_km=3)

        assert "designador=SC%20EL" in permit.notam_url


class TestTheAppNeverClaimsThereAreNoNotams:
    @pytest.mark.django_db
    def test_the_fiche_offers_to_check_rather_than_reporting(self, cost_center):
        """El texto manda a consultar: la app no leyó los NOTAM y no los resume."""
        aerodrome = Aerodrome.objects.create(code="SCEL", name="AMB")
        permit = _permit(cost_center, amc=aerodrome, amc_distance_km=12.5)

        body = (
            login_as("view_flightpermission")
            .get(reverse("permission-detail", args=[permit.pk]))
            .content.decode()
        )

        assert "designador=SCEL" in body
        # Y nada que se parezca a un veredicto sobre los avisos.
        assert "Sin NOTAM" not in body
        assert "No hay NOTAM" not in body

    @pytest.mark.django_db
    def test_the_link_does_not_leak_the_referrer_or_the_opener(self, cost_center):
        """El sitio de la DGAC no tiene por qué recibir `window.opener`."""
        aerodrome = Aerodrome.objects.create(code="SCEL", name="AMB")
        permit = _permit(cost_center, amc=aerodrome, amc_distance_km=12.5)

        body = (
            login_as("view_flightpermission")
            .get(reverse("permission-detail", args=[permit.pk]))
            .content.decode()
        )
        link = body[
            body.index("designador=SCEL") - 200 : body.index("designador=SCEL") + 300
        ]

        assert 'rel="noopener noreferrer"' in link
        assert 'target="_blank"' in link

    @pytest.mark.django_db
    def test_a_permit_without_aerodrome_shows_no_notam_link(self, cost_center):
        permit = _permit(cost_center)

        body = (
            login_as("view_flightpermission")
            .get(reverse("permission-detail", args=[permit.pk]))
            .content.decode()
        )

        assert NOTAM_QUERY_BASE not in body


class TestTheAddressIsDeclaredOnce:
    def test_the_base_url_is_the_dgac_service(self):
        """Si la DGAC muda la dirección, este test lo nota.

        Constante y no `settings`: es una dirección pública de un organismo del
        Estado, no una configuración de despliegue — ponerla en el entorno
        obligaría a declararla en cada instalación para que el enlace funcione.
        """
        assert NOTAM_QUERY_BASE == "https://aipchile.dgac.gob.cl/notam"
