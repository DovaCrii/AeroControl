"""LV-406: la imagen de SIGO y SIPA ya viene con la app (`load_official_link_images`).

Sin red: se sustituyen `_resolve` (DNS) y `_open` (conexión HTTPS fijada), como en
`test_lv399_official_images.py`. Ninguna prueba sale a Internet.
"""

import io
import re

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse

from apps.core import official_images as service
from apps.core.models import OfficialLinkImage
from apps.core.official_links import OFFICIAL_LINKS, SIGO_IMAGE_URL, SIPA_IMAGE_URL
from apps.core.test_lv399_official_images import FakeResponse, png_bytes
from apps.core.test_lv396_official_links import CSS

COMMAND = "load_official_link_images"


class Fake:
    """DNS público y respuestas por servidor y ruta; `fail` lista rutas que dan 404."""

    def __init__(self, monkeypatch):
        self.opened = []
        self.fail = set()
        self.next_color = (10, 120, 200)
        monkeypatch.setattr(service, "_resolve", lambda host: {"8.8.8.8"})
        monkeypatch.setattr(service, "_open", self._open)

    def _open(self, host, address, target, timeout):
        self.opened.append((host, target))
        if target in self.fail:
            return FakeResponse(status=404)
        return FakeResponse(body=png_bytes(color=self.next_color))


@pytest.fixture
def net(monkeypatch):
    return Fake(monkeypatch)


@pytest.fixture(autouse=True)
def documents_root(settings, tmp_path):
    settings.DOCUMENTS_ROOT = tmp_path
    settings.DOCUMENTS_STORAGE_BACKEND = "local"
    return tmp_path


def run(*args):
    out, err = io.StringIO(), io.StringIO()
    call_command(COMMAND, *args, stdout=out, stderr=err)
    return out.getvalue(), err.getvalue()


def test_the_constants_point_to_allowed_dgac_hosts(settings):
    for link in OFFICIAL_LINKS:
        service.check_url(
            link["source_image_url"], settings.OFFICIAL_LINK_IMAGE_ALLOWED_HOSTS
        )
    assert OFFICIAL_LINKS[0]["source_image_url"] == SIGO_IMAGE_URL
    assert OFFICIAL_LINKS[1]["source_image_url"] == SIPA_IMAGE_URL


@pytest.mark.django_db
class TestCommand:
    def test_it_loads_both_images_privately(self, net, documents_root):
        out, _err = run()

        assert "sigo: ok" in out and "sipa: ok" in out
        assert net.opened == [
            ("servicios.dgac.gob.cl", "/sigo-web/assets/img/dgac-logotipo-footer.png"),
            ("sipa.dgac.gob.cl", "/public/img/header.jpg"),
        ]
        assert OfficialLinkImage.objects.count() == 2
        for image in OfficialLinkImage.objects.all():
            assert image.is_active
            assert image.storage_key.startswith("official-images/official-links/")
            assert (documents_root / image.storage_key).read_bytes()[8:12] == b"WEBP"
        assert OfficialLinkImage.objects.get(link_key="sipa").source_host == (
            "sipa.dgac.gob.cl"
        )

    def test_it_is_idempotent(self, net):
        run()
        before = {i.link_key: i.storage_key for i in OfficialLinkImage.objects.all()}
        net.opened.clear()

        out, _err = run()

        assert out.count("skipped") == 2
        assert net.opened == []
        assert before == {
            i.link_key: i.storage_key for i in OfficialLinkImage.objects.all()
        }

    def test_an_inactive_image_is_loaded_again(self, net):
        run()
        OfficialLinkImage.objects.filter(link_key="sigo").update(is_active=False)
        net.opened.clear()

        run()

        assert [host for host, _t in net.opened] == ["servicios.dgac.gob.cl"]
        assert OfficialLinkImage.objects.get(link_key="sigo").is_active

    def test_force_replaces_and_deletes_the_previous_file(self, net, documents_root):
        run()
        old = {i.link_key: i.storage_key for i in OfficialLinkImage.objects.all()}

        run("--force")

        assert OfficialLinkImage.objects.count() == 2
        for image in OfficialLinkImage.objects.all():
            assert image.storage_key != old[image.link_key]
            assert (documents_root / image.storage_key).exists()
            assert not (documents_root / old[image.link_key]).exists()

    def test_a_failure_does_not_stop_the_other_and_ends_in_error(self, net):
        net.fail.add("/sigo-web/assets/img/dgac-logotipo-footer.png")
        out, err = io.StringIO(), io.StringIO()

        with pytest.raises(CommandError, match="sigo"):
            call_command(COMMAND, stdout=out, stderr=err)

        assert "sipa: ok" in out.getvalue()
        assert "sigo: ERROR" in err.getvalue()
        assert list(OfficialLinkImage.objects.values_list("link_key", flat=True)) == [
            "sipa"
        ]

    def test_a_failed_force_keeps_the_previous_image(self, net, documents_root):
        run()
        before = OfficialLinkImage.objects.get(link_key="sigo").storage_key
        net.fail.add("/sigo-web/assets/img/dgac-logotipo-footer.png")

        with pytest.raises(CommandError):
            run("--force")

        image = OfficialLinkImage.objects.get(link_key="sigo")
        assert image.storage_key == before
        assert (documents_root / before).exists()

    def test_a_host_outside_the_list_is_rejected_without_connecting(
        self, net, settings
    ):
        settings.OFFICIAL_LINK_IMAGE_ALLOWED_HOSTS = ["example.org"]

        with pytest.raises(CommandError, match="sigo, sipa"):
            run()

        assert net.opened == []
        assert not OfficialLinkImage.objects.exists()


def _cards(content):
    section = content.split('id="ol-banners-title"')[-1].split("</section>")[0]
    return re.findall(r'<a class="ol-card.*?</a>', section, flags=re.S)


@pytest.mark.django_db
class TestPanel:
    def _panel(self, client, django_user_model):
        user = django_user_model.objects.create_user("ol-406", password="x")
        client.force_login(user)
        return client.get(reverse("dashboard")).content.decode()

    def test_the_panel_no_longer_asks_to_load_a_banner(self, client, django_user_model):
        from apps.core.testing import login_as

        admin = login_as("change_officiallinkimage")
        content = admin.get(reverse("dashboard")).content.decode()
        assert "ol-manage" not in content
        assert "official-link-image-upload" not in content
        assert "enlaces-oficiales" not in content
        assert "Cargar el banner" not in content and "Load the" not in content

    def test_the_card_shows_the_banner_on_top_when_loaded(
        self, net, client, django_user_model
    ):
        run()
        sigo, sipa = _cards(self._panel(client, django_user_model))
        for card, key in ((sigo, "sigo"), (sipa, "sipa")):
            assert "ol-card-banner" in card
            assert '<span class="ol-banner"><img class="ol-logo"' in card
            assert reverse("official-link-image", args=[key]) in card
            assert card.index("ol-banner") < card.index("ol-body")
            assert "ol-icon" not in card
        assert f'alt="{OFFICIAL_LINKS[0]["acronym"]}"' in sigo
        assert 'alt="SIPA"' in sipa

    def test_without_an_image_the_card_keeps_the_icon(self, client, django_user_model):
        cards = _cards(self._panel(client, django_user_model))
        assert all("ol-icon" in c and "ol-banner" not in c for c in cards)

    def test_the_banner_is_full_width_with_contained_height(self):
        css = CSS.read_text(encoding="utf-8")
        rule = css.split(".ol-banner {")[1].split("}")[0]
        assert "flex: 0 0 100%" in rule
        assert "height: 4rem" in rule
        assert "object-fit: contain" in css.split(".ol-logo {")[1].split("}")[0]
