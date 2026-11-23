"""LV-457: encuadre de la foto oficial, reutilizar la de un modelo parecido y rótulos.

Datos ficticios; sin red.
"""

from pathlib import Path

import pytest
from django.conf import settings as django_settings
from django.urls import reverse
from django.utils.translation import gettext

from apps.core.models import AuditEvent, OperationalTenant
from apps.core.testing import login_as
from apps.registry.models import Aircraft, AircraftModelImage
from apps.registry.test_lv399_model_image import (
    _aircraft,
    _stored_image,
    _upload_url,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def documents_root(settings, tmp_path):
    settings.DOCUMENTS_ROOT = tmp_path
    settings.DOCUMENTS_STORAGE_BACKEND = "local"
    return tmp_path


CSS = Path(django_settings.BASE_DIR, "static/css/identity.css")


def _detail(aircraft, *perms):
    client = login_as("view_aircraft", *perms)
    return client.get(reverse("aircraft-detail", args=[aircraft.pk])).content.decode()


def _reuse_url(aircraft, image):
    return reverse("aircraft-model-image-reuse", args=[aircraft.pk, image.pk])


class TestFraming:
    def test_the_figure_carries_the_frame_and_the_credit_inside(self, documents_root):
        aircraft = _aircraft()
        _stored_image(aircraft, credit="DJI")
        html = _detail(aircraft)
        figure = html.split("<figure")[1].split("</figure>")[0]
        assert "fleet-hero-frame" in figure
        assert "<figcaption" in figure
        assert gettext("Image: %(credit)s") % {"credit": "DJI"} in figure

    def test_the_silhouette_uses_the_same_frame(self):
        html = _detail(_aircraft())
        figure = html.split("<figure")[1].split("</figure>")[0]
        assert "fleet-hero-frame" in figure
        assert "img/aircraft/" in figure

    def test_the_upload_link_is_under_the_image_not_among_the_facts(
        self, documents_root
    ):
        aircraft = _aircraft()
        _stored_image(aircraft)
        html = _detail(aircraft, "change_aircraft")
        url = _upload_url(aircraft)
        assert url in html
        facts = html.split('<dl class="fleet-hero-facts">')[1].split("</dl>")[0]
        assert url not in facts
        figure = html.split("<figure")[1].split("</figure>")[0]
        assert url in figure

    def test_the_frame_never_crops(self):
        css = CSS.read_text(encoding="utf-8")
        frame = css.split(".fleet-hero-frame img {")[1].split("}")[0]
        assert "object-fit: contain" in frame
        assert "cover" not in frame
        assert (
            "aspect-ratio: 4 / 3" in css.split(".fleet-hero-frame {")[1].split("}")[0]
        )

    def test_the_hours_of_an_aircraft_without_flights_do_not_read_0min(self):
        aircraft = _aircraft()
        client = login_as("view_aircraft", "view_flightrecord")
        response = client.get(reverse("aircraft-detail", args=[aircraft.pk]))
        assert response.context["total_flight_hours"] == "0 h"
        assert "0min" not in response.content.decode()


class TestReuse:
    def _two_models(self, documents_root):
        source_aircraft = _aircraft("RPA-1", "Mavic 3 Enterprise")
        source = _stored_image(source_aircraft, credit="DJI")
        target = _aircraft("RPA-2", "Mavic 3E")
        return source, target

    def test_the_upload_page_offers_the_other_models_images(self, documents_root):
        source, target = self._two_models(documents_root)
        html = (
            login_as("change_aircraft", "view_aircraft")
            .get(_upload_url(target))
            .content.decode()
        )
        assert "data-reusable-image" in html
        assert "Mavic 3 Enterprise" in html
        assert _reuse_url(target, source) in html
        assert gettext("Use this image") in html

    def test_nothing_is_offered_for_the_models_own_image(self, documents_root):
        aircraft = _aircraft("RPA-1", "Mavic 3 Enterprise")
        _stored_image(aircraft)
        html = login_as("change_aircraft").get(_upload_url(aircraft)).content.decode()
        assert "data-reusable-image" not in html

    def test_happy_path_shares_the_file_and_shows_it(self, documents_root):
        source, target = self._two_models(documents_root)
        client = login_as("change_aircraft", "view_aircraft")
        response = client.post(_reuse_url(target, source))
        assert response.status_code == 302
        assert response["Location"] == reverse("aircraft-detail", args=[target.pk])
        mine = AircraftModelImage.for_aircraft(target)
        assert mine.pk != source.pk
        assert mine.storage_key == source.storage_key
        assert mine.credit == "DJI"
        assert mine.model_name == "Mavic 3E"
        html = client.get(reverse("aircraft-detail", args=[target.pk])).content.decode()
        assert "data-model-image" in html
        assert f"{reverse('aircraft-model-image', args=[mine.pk])}?v=" in html
        # Una sola copia del archivo.
        assert len(list(documents_root.rglob("*.webp"))) == 1

    def test_replacing_one_models_image_keeps_the_shared_file_of_the_other(
        self, documents_root
    ):
        source, target = self._two_models(documents_root)
        client = login_as("change_aircraft", "view_aircraft")
        client.post(_reuse_url(target, source))
        extra = _stored_image(_aircraft("RPA-4", "Mavic 3 Thermal"))
        client.post(_reuse_url(target, extra))
        assert extra.storage_key != source.storage_key
        # La de origen sigue en uso por «Mavic 3 Enterprise»: no se borró.
        assert (documents_root / source.storage_key).exists()

    def test_needs_change_aircraft(self, documents_root):
        source, target = self._two_models(documents_root)
        client = login_as("view_aircraft")
        assert client.post(_reuse_url(target, source)).status_code == 403
        assert AircraftModelImage.for_aircraft(target) is None

    def test_an_image_of_another_company_is_a_404(self, documents_root):
        other = OperationalTenant.objects.create(slug="otra", name="Otra")
        foreign = _stored_image(_aircraft("RPA-9", "Mavic 3 Enterprise", tenant=other))
        target = _aircraft("RPA-2", "Mavic 3E")
        client = login_as("change_aircraft")
        assert client.post(_reuse_url(target, foreign)).status_code == 404
        assert AircraftModelImage.for_aircraft(target) is None

    def test_get_does_not_mutate(self, documents_root):
        source, target = self._two_models(documents_root)
        client = login_as("change_aircraft")
        assert client.get(_reuse_url(target, source)).status_code == 405
        assert AircraftModelImage.for_aircraft(target) is None

    def test_it_is_audited(self, documents_root):
        source, target = self._two_models(documents_root)
        login_as("change_aircraft").post(_reuse_url(target, source))
        mine = AircraftModelImage.for_aircraft(target)
        event = AuditEvent.objects.filter(object_id=str(mine.pk)).latest("created_at")
        assert event.action == "official_image_reused"
        assert event.metadata["model_key"] == "mavic 3e"
        assert event.metadata["source_model_key"] == "mavic 3 enterprise"


class TestLabels:
    @pytest.mark.parametrize(
        ("field", "msgid"),
        [
            ("type", "Type"),
            ("year", "Year"),
            ("max_takeoff_weight_kg", "Maximum takeoff weight (kg)"),
            ("basic_weight_kg", "Basic weight (kg)"),
            ("vlos", "VLOS"),
            ("parachute", "Parachute"),
            ("authorized_services", "Authorized services"),
        ],
    )
    def test_the_label_is_translatable_and_readable(self, field, msgid):
        label = Aircraft._meta.get_field(field).verbose_name
        assert str(label) == gettext(msgid)
        assert "_" not in str(label)

    def test_the_detail_table_shows_the_translated_labels(self):
        aircraft = _aircraft()
        html = _detail(aircraft)
        assert gettext("Maximum takeoff weight (kg)") in html
        assert gettext("Basic weight (kg)") in html
