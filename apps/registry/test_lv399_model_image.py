"""LV-399: la foto oficial del fabricante, una por modelo, guardada fuera de git.

Sin red: `_resolve` y `_open` del servicio se sustituyen (fixture `network` de
`apps/core/test_lv399_official_images.py`).
"""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.urls import reverse

from apps.core import official_images as service
from apps.core.models import AuditEvent, OperationalTenant
from apps.core.test_lv399_official_images import (
    install_fake_network,
    png_bytes,
    said,
)
from apps.core.testing import login_as
from apps.registry.models import (
    Aircraft,
    AircraftModelImage,
    CostCenter,
    normalize_model_key,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def network(monkeypatch):
    return install_fake_network(monkeypatch)


@pytest.fixture
def documents_root(settings, tmp_path):
    settings.DOCUMENTS_ROOT = tmp_path
    settings.DOCUMENTS_STORAGE_BACKEND = "local"
    return tmp_path


def _aircraft(registration="RPA-1", model="Matrice 300 RTK", tenant=None):
    centre = CostCenter.objects.create(
        code=f"CC-{registration}",
        name="Faena",
        **({"tenant": tenant} if tenant else {}),
    )
    return Aircraft.objects.create(
        registration=registration,
        type="RPA",
        model=model,
        manufacturer="DJI",
        cost_center=centre,
        **({"tenant": tenant} if tenant else {}),
    )


def _stored_image(aircraft, credit="DJI"):
    key = service.store_image("aircraft-models/t", service.normalize_image(png_bytes()))
    return AircraftModelImage.objects.create(
        tenant_id=aircraft.tenant_id,
        model_key=aircraft.model,
        model_name=aircraft.model,
        storage_key=key,
        credit=credit,
    )


def _upload_url(aircraft):
    return reverse("aircraft-model-image-upload", args=[aircraft.pk])


class TestTheCatalog:
    def test_the_key_is_case_and_space_insensitive(self):
        assert normalize_model_key("  MATRICE   300 rtk ") == "matrice 300 rtk"

    def test_one_image_per_model_and_company(self, documents_root):
        aircraft = _aircraft()
        _stored_image(aircraft)
        with pytest.raises(IntegrityError), transaction.atomic():
            AircraftModelImage.objects.create(
                tenant_id=aircraft.tenant_id,
                model_key="MATRICE 300 rtk",
                model_name="x",
                storage_key="k",
            )

    def test_an_empty_key_is_refused_by_the_database(self):
        aircraft = _aircraft()
        with pytest.raises(IntegrityError), transaction.atomic():
            AircraftModelImage.objects.create(
                tenant_id=aircraft.tenant_id,
                model_key="",
                model_name="",
                storage_key="k",
            )

    def test_every_aircraft_of_the_model_shares_it(self, documents_root):
        first = _aircraft("RPA-1", "Matrice 300 RTK")
        second = _aircraft("RPA-2", "matrice 300 rtk")
        image = _stored_image(first)
        assert AircraftModelImage.for_aircraft(second) == image
        assert AircraftModelImage.for_aircraft(_aircraft("RPA-3", "Mavic 3")) is None


class TestPermissions:
    def test_loading_needs_change_aircraft(self, documents_root):
        aircraft = _aircraft()
        client = login_as("view_aircraft")
        assert client.get(_upload_url(aircraft)).status_code == 403
        upload = SimpleUploadedFile("a.png", png_bytes(), content_type="image/png")
        response = client.post(_upload_url(aircraft), {"image": upload})
        assert response.status_code == 403
        assert not AircraftModelImage.objects.exists()

    def test_seeing_needs_view_aircraft(self, documents_root):
        image = _stored_image(_aircraft())
        url = reverse("aircraft-model-image", args=[image.pk])
        assert login_as("view_operator").get(url).status_code == 403
        assert login_as("view_aircraft").get(url).status_code == 200

    def test_another_company_cannot_load_or_see(self, documents_root):
        other = OperationalTenant.objects.create(slug="otra", name="Otra")
        foreign = _aircraft("RPA-9", "Mavic 3", tenant=other)
        image = _stored_image(foreign)

        assert login_as("change_aircraft").get(_upload_url(foreign)).status_code == 404
        url = reverse("aircraft-model-image", args=[image.pk])
        assert login_as("view_aircraft").get(url).status_code == 404
        member = login_as("view_aircraft", "view_operator", member_of=other)
        assert member.get(url).status_code == 200


class TestLoading:
    def test_a_valid_upload_is_reencoded_and_audited(self, documents_root):
        aircraft = _aircraft()
        client = login_as("change_aircraft", "view_aircraft")
        upload = SimpleUploadedFile(
            "m300.jpg", png_bytes(exif=True, fmt="JPEG"), content_type="image/jpeg"
        )

        response = client.post(
            _upload_url(aircraft), {"image": upload, "credit": "DJI"}
        )

        assert response.status_code == 302
        image = AircraftModelImage.objects.get()
        assert image.model_key == "matrice 300 rtk"
        assert image.credit == "DJI"
        assert image.uploaded_by == client.user
        stored = (documents_root / image.storage_key).read_bytes()
        assert stored[8:12] == b"WEBP"
        assert b"SecretMaker" not in stored
        event = AuditEvent.objects.filter(object_id=str(image.pk)).latest("created_at")
        assert event.action == "official_image_loaded"
        assert {
            key: event.metadata[key] for key in ("model_key", "source", "source_host")
        } == {"model_key": "matrice 300 rtk", "source": "upload", "source_host": ""}

    def test_a_file_that_is_not_an_image_is_refused(self, documents_root):
        aircraft = _aircraft()
        client = login_as("change_aircraft")
        upload = SimpleUploadedFile(
            "a.png", b"<html>no</html>", content_type="image/png"
        )
        response = client.post(_upload_url(aircraft), {"image": upload})
        assert response.status_code == 200
        assert (
            said("The file is not a valid image. Use a JPEG, PNG or WebP image.")
            in response.content.decode()
        )
        assert not AircraftModelImage.objects.exists()

    def test_a_file_too_big_is_refused(self, documents_root, settings):
        settings.OFFICIAL_IMAGE_MAX_BYTES = 100
        aircraft = _aircraft()
        client = login_as("change_aircraft")
        upload = SimpleUploadedFile("a.png", png_bytes(), content_type="image/png")
        response = client.post(_upload_url(aircraft), {"image": upload})
        assert (
            said("The image exceeds the maximum size of %(size)s MB.", size=0.0)
            in response.content.decode()
        )
        assert not AircraftModelImage.objects.exists()

    def test_a_dji_url_is_downloaded(self, documents_root, network):
        aircraft = _aircraft()
        client = login_as("change_aircraft")
        response = client.post(
            _upload_url(aircraft),
            {"source_url": "https://dl.djicdn.com/m300.png", "credit": "DJI"},
        )
        assert response.status_code == 302
        image = AircraftModelImage.objects.get()
        assert image.source_host == "dl.djicdn.com"
        assert image.source_url == "https://dl.djicdn.com/m300.png"

    @pytest.mark.parametrize(
        ("url", "message"),
        [
            (
                "https://example.com/a.png",
                (
                    "The host %(host)s is not on the list of allowed sources.",
                    "example.com",
                ),
            ),
            ("http://www.dji.com/a.png", ("Only https addresses are accepted.", None)),
        ],
    )
    def test_a_url_breaking_the_rules_is_refused(
        self, documents_root, network, url, message
    ):
        aircraft = _aircraft()
        response = login_as("change_aircraft").post(
            _upload_url(aircraft), {"source_url": url}
        )
        msgid, host = message
        expected = said(msgid, host=host) if host else said(msgid)
        assert expected in response.content.decode()
        assert network.opened == []
        assert not AircraftModelImage.objects.exists()

    def test_a_private_address_is_refused(self, documents_root, network):
        network.dns = {"10.1.2.3"}
        aircraft = _aircraft()
        response = login_as("change_aircraft").post(
            _upload_url(aircraft), {"source_url": "https://www.dji.com/a.png"}
        )
        assert said("The address points to a private or local network.") in (
            response.content.decode()
        )
        assert network.opened == []

    def test_replacing_updates_the_same_row(self, documents_root):
        aircraft = _aircraft()
        first = _stored_image(aircraft)
        client = login_as("change_aircraft")
        upload = SimpleUploadedFile("a.png", png_bytes(), content_type="image/png")
        client.post(
            _upload_url(aircraft), {"image": upload, "credit": "DJI Enterprise"}
        )
        image = AircraftModelImage.objects.get()
        assert image.pk == first.pk
        assert image.credit == "DJI Enterprise"
        assert image.storage_key != first.storage_key
        # El archivo reemplazado se borra; el nuevo queda.
        assert not (documents_root / first.storage_key).exists()
        assert (documents_root / image.storage_key).exists()


class TestTheDetailPage:
    def test_without_an_image_the_silhouette_is_shown(self):
        aircraft = _aircraft()
        html = (
            login_as("view_aircraft")
            .get(reverse("aircraft-detail", args=[aircraft.pk]))
            .content.decode()
        )
        hero = html.split('class="fleet-hero"')[1].split("</dl>")[0]
        assert "img/aircraft/matrice" in hero
        assert "data-model-image" not in hero
        assert "aircraft-model-image" not in hero

    def test_with_an_image_the_photo_and_credit_are_shown(self, documents_root):
        aircraft = _aircraft()
        image = _stored_image(aircraft, credit="DJI")
        client = login_as("view_aircraft")
        html = client.get(
            reverse("aircraft-detail", args=[aircraft.pk])
        ).content.decode()

        hero = html.split('class="fleet-hero"')[1].split("</dl>")[0]
        src = reverse("aircraft-model-image", args=[image.pk])
        assert f'src="{src}?v=' in hero
        assert 'alt="Matrice 300 RTK"' in hero
        assert said("Image: %(credit)s", credit="DJI") in hero
        assert "img/aircraft/matrice" not in hero
        # Nada de otro dominio: la imagen se sirve desde la app.
        assert "https://" not in hero

        served = client.get(src)
        assert served.status_code == 200
        assert served["Content-Type"] == "image/webp"
        assert served.content[8:12] == b"WEBP"

    def test_the_load_link_is_only_for_who_can_change(self):
        aircraft = _aircraft()
        url = _upload_url(aircraft)
        detail = reverse("aircraft-detail", args=[aircraft.pk])
        assert url not in login_as("view_aircraft").get(detail).content.decode()
        assert (
            url
            in login_as("view_aircraft", "change_aircraft").get(detail).content.decode()
        )
