"""LV-399: servicio de imagen oficial (descarga anti-SSRF, validación y re-codificación) y el
banner de SIGO/SIPA en las tarjetas del panel.

Sin red: `conftest.py` hace fallar `urlopen`, y acá además se sustituyen `_resolve` (el DNS) y
`_open` (la conexión HTTPS fijada a la IP comprobada). Ninguna prueba sale a Internet.
"""

import io
import re

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings
from django.urls import reverse
from django.utils import translation
from django.utils.html import escape
from django.utils.translation import gettext
from PIL import Image

from apps.core import official_images as service
from apps.core.models import AuditEvent, OfficialLinkImage
from apps.core.official_images import OfficialImageError
from apps.core.test_lv315_identity_foundation import ROOT
from apps.core.testing import login_as

DJI = ["dji.com", "www.dji.com", "enterprise.dji.com", "dl.djicdn.com"]
DGAC = ["dgac.gob.cl"]


@pytest.fixture(autouse=True)
def english_messages():
    """El servicio se prueba con los msgid (inglés). Las respuestas de las vistas salen en el
    idioma de la petición y se comparan con `said()`, que traduce el mismo msgid."""
    with translation.override("en"):
        yield


def said(msgid, **params):
    """El mensaje como lo ve la persona en la página: traducido y escapado."""
    with translation.override(settings.LANGUAGE_CODE):
        text = gettext(msgid)
    return escape(text % params if params else text)


def png_bytes(size=(64, 48), color=(10, 120, 200), exif=False, fmt="PNG"):
    image = Image.new("RGB", size, color)
    buffer = io.BytesIO()
    kwargs = {}
    if exif:
        data = Image.Exif()
        data[0x010F] = "SecretMaker"  # Make
        data[0x8825] = {1: "S"}  # GPSInfo
        kwargs["exif"] = data.tobytes()
    image.save(buffer, fmt, **kwargs)
    return buffer.getvalue()


class FakeResponse:
    def __init__(self, status=200, body=b"", headers=None):
        self.status = status
        self._body = io.BytesIO(body)
        self._headers = headers or {}
        self.closed = False

    def getheader(self, name, default=None):
        return self._headers.get(name, default)

    def read(self, size=-1):
        return self._body.read(size)

    read1 = read

    def close(self):
        self.closed = True


def install_fake_network(monkeypatch):
    """DNS y conexión falsos. `.dns` y `.response` se ajustan por prueba."""

    class Network:
        dns = {"8.8.8.8"}
        response = FakeResponse(body=png_bytes())
        opened = []

    def resolve(host):
        return set(Network.dns)

    def open_(host, address, target, timeout):
        Network.opened.append((host, address, target))
        return Network.response

    Network.opened = []
    monkeypatch.setattr(service, "_resolve", resolve)
    monkeypatch.setattr(service, "_open", open_)
    return Network


@pytest.fixture
def network(monkeypatch):
    return install_fake_network(monkeypatch)


@pytest.fixture
def documents_root(settings, tmp_path):
    settings.DOCUMENTS_ROOT = tmp_path
    settings.DOCUMENTS_STORAGE_BACKEND = "local"
    return tmp_path


class TestHostRules:
    @pytest.mark.parametrize(
        "host",
        [
            "dji.com",
            "www.dji.com",
            "enterprise.dji.com",
            "a.b.dji.com",
            "dl.djicdn.com",
        ],
    )
    def test_listed_hosts_and_their_subdomains_pass(self, host):
        assert service.host_is_allowed(host, DJI)

    @pytest.mark.parametrize(
        "host", ["evildji.com", "dji.com.evil.net", "djicdn.com", "", "localhost"]
    )
    def test_lookalikes_do_not_pass(self, host):
        assert not service.host_is_allowed(host, DJI)

    def test_a_host_off_the_list_is_rejected(self, network):
        with pytest.raises(OfficialImageError, match="not on the list"):
            service.fetch_image("https://example.com/a.png", DJI)
        assert network.opened == []

    def test_http_is_rejected(self, network):
        with pytest.raises(OfficialImageError, match="https"):
            service.fetch_image("http://www.dji.com/a.png", DJI)
        assert network.opened == []

    def test_credentials_in_the_address_are_rejected(self, network):
        with pytest.raises(OfficialImageError, match="user name"):
            service.fetch_image("https://user:pw@www.dji.com/a.png", DJI)

    def test_a_non_standard_port_is_rejected(self, network):
        with pytest.raises(OfficialImageError, match="port"):
            service.fetch_image("https://www.dji.com:8443/a.png", DJI)

    @pytest.mark.parametrize(
        "address",
        [
            "127.0.0.1",
            "10.0.0.5",
            "192.168.1.20",
            "172.16.4.4",
            "169.254.169.254",
            "0.0.0.0",
            "224.0.0.1",
            "::1",
            "fe80::1",
            "fc00::1",
            "::ffff:127.0.0.1",
            "ff02::1",
        ],
    )
    def test_a_private_or_local_address_is_rejected(self, network, address):
        network.dns = {"8.8.8.8", address}
        with pytest.raises(OfficialImageError, match="private or local"):
            service.fetch_image("https://www.dji.com/a.png", DJI)
        assert network.opened == []

    def test_the_connection_goes_to_the_checked_address(self, network):
        data, host = service.fetch_image("https://www.dji.com/p/a.png?x=1", DJI)
        assert host == "www.dji.com"
        assert network.opened == [("www.dji.com", "8.8.8.8", "/p/a.png?x=1")]
        assert data == network.response._body.getvalue()

    def test_ipv4_is_preferred_over_ipv6(self, network):
        # Por orden de texto, "2001:…" va antes que "23.…": el servidor puede no tener IPv6.
        network.dns = {"2001:4860:4860::8888", "23.1.1.1"}
        service.fetch_image("https://www.dji.com/a.png", DJI)
        assert network.opened[0][1] == "23.1.1.1"


class TestDownloadLimits:
    @pytest.mark.parametrize("status", [301, 302, 307, 308])
    def test_a_redirect_is_not_followed(self, network, status):
        network.response = FakeResponse(
            status=status, headers={"Location": "https://169.254.169.254/"}
        )
        with pytest.raises(OfficialImageError, match="redirects"):
            service.fetch_image("https://www.dji.com/a.png", DJI)
        assert len(network.opened) == 1
        assert network.response.closed

    def test_an_error_status_is_reported(self, network):
        network.response = FakeResponse(status=404)
        with pytest.raises(OfficialImageError, match="404"):
            service.fetch_image("https://www.dji.com/a.png", DJI)

    def test_a_declared_size_over_the_limit_is_rejected(self, network):
        network.response = FakeResponse(body=b"x", headers={"Content-Length": "999"})
        with pytest.raises(OfficialImageError, match="maximum size"):
            service.fetch_image("https://www.dji.com/a.png", DJI, max_bytes=100)

    def test_an_undeclared_body_over_the_limit_is_cut(self, network):
        network.response = FakeResponse(body=b"x" * 500)
        with pytest.raises(OfficialImageError, match="maximum size"):
            service.fetch_image("https://www.dji.com/a.png", DJI, max_bytes=100)

    def test_a_network_failure_is_a_readable_error(self, monkeypatch, network):
        def boom(*args, **kwargs):
            raise TimeoutError("slow")

        monkeypatch.setattr(service, "_open", boom)
        with pytest.raises(OfficialImageError, match="could not be downloaded"):
            service.fetch_image("https://www.dji.com/a.png", DJI)

    def test_an_unresolvable_host_is_a_readable_error(self, monkeypatch):
        def fail(host):
            raise OSError("nxdomain")

        monkeypatch.setattr(service, "_resolve", fail)
        with pytest.raises(OfficialImageError, match="resolved"):
            service.fetch_image("https://www.dji.com/a.png", DJI)


class TestNormalization:
    def test_it_reencodes_to_webp_without_metadata(self):
        source = png_bytes(size=(400, 300), exif=True, fmt="JPEG")
        assert b"SecretMaker" in source

        webp = service.normalize_image(source)

        assert webp[:4] == b"RIFF" and webp[8:12] == b"WEBP"
        assert b"SecretMaker" not in webp
        assert b"EXIF" not in webp and b"Exif" not in webp
        with Image.open(io.BytesIO(webp)) as result:
            assert result.format == "WEBP"
            assert not result.getexif()
            assert "icc_profile" not in result.info

    def test_a_big_image_is_shrunk_under_the_target(self):
        noise = Image.effect_noise((3000, 2000), 90).convert("RGB")
        buffer = io.BytesIO()
        noise.save(buffer, "PNG")

        webp = service.normalize_image(buffer.getvalue())

        assert len(webp) <= service.TARGET_BYTES
        with Image.open(io.BytesIO(webp)) as result:
            assert max(result.size) <= service.MAX_SIDE

    @pytest.mark.parametrize(
        "data", [b"", b"not an image at all", b"%PDF-1.7 fake", b"GIF89a" + b"\0" * 20]
    )
    def test_something_that_is_not_an_accepted_image_is_rejected(self, data):
        with pytest.raises(OfficialImageError, match="not a valid image"):
            service.normalize_image(data)

    def test_a_gif_is_rejected_even_if_valid(self):
        with pytest.raises(OfficialImageError, match="not a valid image"):
            service.normalize_image(png_bytes(fmt="GIF"))

    def test_too_many_pixels_is_rejected_before_decoding(self, monkeypatch):
        monkeypatch.setattr(service, "MAX_PIXELS", 100)
        with pytest.raises(OfficialImageError, match="too many pixels"):
            service.normalize_image(png_bytes(size=(20, 20)))

    def test_an_upload_over_the_limit_is_rejected(self):
        upload = SimpleUploadedFile("a.png", b"x" * 200, content_type="image/png")
        with pytest.raises(OfficialImageError, match="maximum size"):
            service.read_upload(upload, max_bytes=100)


def _cards(content):
    section = content.split('id="ol-banners-title"')[-1].split("</section>")[0]
    return re.findall(r'<a class="ol-card".*?</a>', section, flags=re.S)


@pytest.mark.django_db
class TestOfficialLinkBanner:
    def upload_url(self, key="sigo"):
        return reverse("official-link-image-upload", args=[key])

    def test_loading_needs_the_permission(self, documents_root):
        client = login_as("view_aircraft")
        assert client.get(self.upload_url()).status_code == 403
        upload = SimpleUploadedFile("a.png", png_bytes(), content_type="image/png")
        assert client.post(self.upload_url(), {"image": upload}).status_code == 403
        assert not OfficialLinkImage.objects.exists()

    def test_an_unknown_system_is_404(self):
        client = login_as("change_officiallinkimage")
        assert client.get(self.upload_url("other")).status_code == 404

    def test_an_upload_is_stored_privately_and_audited(self, documents_root):
        client = login_as("change_officiallinkimage")
        upload = SimpleUploadedFile("a.png", png_bytes(), content_type="image/png")

        response = client.post(self.upload_url(), {"image": upload})

        assert response.status_code == 302
        image = OfficialLinkImage.objects.get(link_key="sigo")
        assert image.storage_key.startswith("official-images/official-links/")
        assert (documents_root / image.storage_key).read_bytes()[8:12] == b"WEBP"
        event = AuditEvent.objects.filter(object_id=str(image.pk)).latest("created_at")
        assert event.action == "official_image_loaded"
        assert event.metadata["source"] == "upload"

    def test_a_dji_host_is_not_allowed_for_the_dgac_banner(
        self, documents_root, network
    ):
        client = login_as("change_officiallinkimage")
        response = client.post(
            self.upload_url(), {"source_url": "https://www.dji.com/logo.png"}
        )
        assert response.status_code == 200
        assert (
            said(
                "The host %(host)s is not on the list of allowed sources.",
                host="www.dji.com",
            )
            in response.content.decode()
        )
        assert network.opened == []
        assert not OfficialLinkImage.objects.exists()

    def test_a_dgac_url_is_downloaded_and_its_host_audited(
        self, documents_root, network
    ):
        client = login_as("change_officiallinkimage")
        response = client.post(
            self.upload_url("sipa"),
            {"source_url": "https://sipa.dgac.gob.cl/img/logo.png"},
        )
        assert response.status_code == 302
        image = OfficialLinkImage.objects.get(link_key="sipa")
        assert image.source_host == "sipa.dgac.gob.cl"
        event = AuditEvent.objects.filter(object_id=str(image.pk)).latest("created_at")
        assert event.metadata["source_host"] == "sipa.dgac.gob.cl"

    def test_both_or_neither_source_is_an_error(self, documents_root):
        client = login_as("change_officiallinkimage")
        response = client.post(self.upload_url(), {})
        assert said("Upload a file or paste an address, one of the two.") in (
            response.content.decode()
        )

    def test_the_card_shows_the_icon_without_a_banner(self, client, django_user_model):
        user = django_user_model.objects.create_user("ol-plain", password="x")
        client.force_login(user)
        cards = _cards(client.get(reverse("dashboard")).content.decode())
        assert len(cards) == 2
        assert all(
            'class="ol-icon"' in card and "ol-logo" not in card for card in cards
        )

    def test_the_card_shows_the_banner_when_loaded(
        self, client, django_user_model, documents_root
    ):
        key = service.store_image(
            "official-links", service.normalize_image(png_bytes())
        )
        image = OfficialLinkImage.objects.create(link_key="sigo", storage_key=key)
        user = django_user_model.objects.create_user("ol-banner", password="x")
        client.force_login(user)

        cards = _cards(client.get(reverse("dashboard")).content.decode())

        sigo, sipa = cards
        assert 'class="ol-logo"' in sigo and 'alt="SIGO"' in sigo
        assert reverse("official-link-image", args=["sigo"]) in sigo
        assert "ol-icon" in sipa
        served = client.get(reverse("official-link-image", args=["sigo"]))
        assert served.status_code == 200
        assert served["Content-Type"] == "image/webp"
        assert served["X-Content-Type-Options"] == "nosniff"
        assert "private" in served["Cache-Control"]
        assert served.content[8:12] == b"WEBP"
        assert image.pk

    def test_the_banner_needs_a_session(self, client):
        response = client.get(reverse("official-link-image", args=["sigo"]))
        assert response.status_code == 302
        assert reverse("login") in response["Location"]


class TestTheIconTakesTheTokenColour:
    """El defecto de la captura: el símbolo del sprite se rellenaba de negro."""

    def test_the_icon_rule_strokes_with_current_colour_and_no_fill(self):
        css = (ROOT / "static" / "css" / "official-links.css").read_text(
            encoding="utf-8"
        )
        rule = css.split(".ol-icon {")[1].split("}")[0]
        assert "fill: none" in rule
        assert "stroke: currentColor" in rule
        assert "color: var(--ac-primary)" in rule

    def test_the_icons_are_drawn_with_strokes_not_own_colours(self):
        from apps.core.official_links import OFFICIAL_LINKS

        sprite = (ROOT / "static" / "img" / "icons.svg").read_text(encoding="utf-8")
        for link in OFFICIAL_LINKS:
            symbol = sprite.split(f'<symbol id="icon-{link["icon"]}"')[1].split(
                "</symbol>"
            )[0]
            assert "fill=" not in symbol and "stroke=" not in symbol, link["key"]
