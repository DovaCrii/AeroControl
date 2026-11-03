"""LV-396: tarjetas y grupo de menú hacia SIGO y SIPA, con las URL salidas de las constantes."""

import re

from django.urls import reverse

from apps.core import official_links as registry
from apps.core.test_lv315_identity_foundation import ROOT

CSS = ROOT / "static" / "css" / "official-links.css"


def _banners(content):
    section = content.split('id="ol-banners-title"')[-1].split("</section>")[0]
    return re.findall(r"<a class=\"ol-card\"[^>]*>", section)


def _get_panel(client, django_user_model):
    user = django_user_model.objects.create_user("ol-user", password="x")
    client.force_login(user)
    return client.get(reverse("dashboard")).content.decode()


def test_registry_urls_are_the_constants():
    urls = {link["key"]: link["url"] for link in registry.OFFICIAL_LINKS}
    assert urls == {"sigo": registry.SIGO_URL, "sipa": registry.SIPA_URL}


def test_the_panel_shows_both_banners_with_safe_external_links(
    client, django_user_model
):
    content = _get_panel(client, django_user_model)
    tags = _banners(content)
    assert len(tags) == len(registry.OFFICIAL_LINKS) == 2
    for tag, link in zip(tags, registry.OFFICIAL_LINKS, strict=True):
        assert f'href="{link["url"]}"' in tag
        assert 'target="_blank"' in tag
        assert 'rel="noopener noreferrer"' in tag
    assert 'href="/static/css/official-links.css"' in content


def test_the_sidebar_group_uses_the_same_registry(client, django_user_model):
    content = _get_panel(client, django_user_model)
    group = content.split('id="nav-group-official-links"')[-1].split("</nav>")[0]
    links = re.findall(r'<a href="([^"]+)" class="nav-item[^>]*>', group)
    assert links[:2] == [link["url"] for link in registry.OFFICIAL_LINKS]
    assert group.count('rel="noopener noreferrer"') >= 2


def test_anonymous_gets_no_links(client):
    assert "official_links" not in (client.get(reverse("login")).context or {})


def test_the_sheet_is_under_16_kb_in_lf_bytes():
    assert len(CSS.read_bytes().replace(b"\r\n", b"\n")) < 16 * 1024
    assert "infinite" not in CSS.read_text(encoding="utf-8")
