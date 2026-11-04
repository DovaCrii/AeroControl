"""LV-398: «Cómo funciona» (`/inicio/`), su tarjeta en el panel y los logos oficiales de J.E.J.

Pedido del usuario (2026-11-03): una página moderna e interactiva que explique qué busca
AeroControl, qué se requiere, el proceso y el cumplimiento, a partir de la guía visual
JEJ-GRI-SS-INS-096. Lo que estos guardianes fijan:

- la página pide sesión y nada más (no lee datos de dominio), dibuja sus seis secciones y
  sus pestañas son accesibles sin JS (cada `<label>` nombra un radio que controla un panel);
- los enlaces a pantallas reales se ofrecen **sólo** a quien puede abrirlas, y cada uno
  pide al menos lo que pide su vista (el mismo contrato que el menú, `LV-381`);
- la tarjeta del panel enlaza a la página y su JS envuelve **todo** acceso a
  `localStorage` (lanza en una ventana privada: lección de `app.js` en `AGENTS.md`);
- los dos logos existen, pesan poco y se usan en par, uno por tema;
- la hoja propia queda bajo su techo de 16 KB sin tocar `app.css` ni `identity.css`.
"""

import re
from pathlib import Path

import pytest
from django.contrib.auth.models import Permission, User
from django.urls import resolve, reverse
from django.utils import translation
from django.utils.translation import gettext
from PIL import Image

from apps.core import start_guide
from apps.core.official_links import SIGO_URL, SIPA_URL
from apps.core.testing import full_sidebar_html, login_as

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "static"
START_CSS = STATIC / "css" / "start.css"
IMAGERY_CSS = STATIC / "css" / "imagery.css"
CARD_JS = STATIC / "js" / "start-card.js"
LOGIN = ROOT / "templates" / "registration" / "login.html"
LOGOS = {
    "blue": STATIC / "img" / "jej-logo-blue.webp",
    "white": STATIC / "img" / "jej-logo-white.webp",
}
LOGO_CEILING = 40 * 1024
SECTIONS = (
    "st-purpose",
    "st-requirements",
    "st-process",
    "st-lights",
    "st-roles",
    "st-links",
)


def _lf_bytes(path):
    return path.read_bytes().replace(b"\r\n", b"\n")


def _page(client):
    response = client.get(reverse("start"))
    assert response.status_code == 200
    return response.content.decode()


def _main(html):
    """Sólo el contenido de la página: el menú lateral también enlaza a pantallas reales."""
    return html.split('<article class="st">', 1)[1].split("</article>", 1)[0]


# --- La página ---------------------------------------------------------------


@pytest.mark.django_db
def test_without_a_session_it_redirects_to_the_login(client):
    response = client.get(reverse("start"))

    assert response.status_code == 302
    assert reverse("login") in response["Location"]


@pytest.mark.django_db
def test_any_session_opens_it_and_it_draws_its_sections():
    html = _page(login_as())
    main = _main(html)

    for section in SECTIONS:
        assert f'id="{section}"' in main, section
        assert f'href="#{section}"' in main, (
            section
        )  # el índice de la cabecera llega a cada una
    assert "<h1" in main
    # Los banners oficiales se reutilizan, con su título visible acá.
    assert SIGO_URL in main and SIPA_URL in main
    assert 'id="ol-banners-title" class="st-h2"' in main
    # Los requisitos se abren sin JS.
    assert main.count('<details class="st-req">') == 6


@pytest.mark.django_db
def test_the_tabs_work_without_js_and_every_label_names_a_radio_that_controls_a_panel():
    main = _main(_page(login_as()))

    radios = re.findall(
        r'<input class="st-tab-input" type="radio" name="st-process" id="([^"]+)" aria-controls="([^"]+)"',
        main,
    )
    labels = re.findall(r'<label class="st-tab[^"]*" for="([^"]+)"', main)
    panels = re.findall(r'<section class="st-panel" id="([^"]+)"', main)

    assert len(radios) == 5
    assert [radio for radio, _panel in radios] == labels
    assert [panel for _radio, panel in radios] == panels
    assert main.count(" checked>") == 1  # una pestaña abierta al llegar
    # La hoja muestra cada panel con su radio, y marca la pestaña elegida con algo más que color.
    css = START_CSS.read_text(encoding="utf-8")
    for radio, panel in radios:
        assert f"#{radio}:checked ~ .st-panels #{panel}" in css
        assert f'#{radio}:checked ~ .st-tab-list [for="{radio}"]' in css
        assert f'#{radio}:focus-visible ~ .st-tab-list [for="{radio}"]' in css


@pytest.mark.django_db
def test_without_permissions_no_link_to_a_real_screen_is_offered():
    main = _main(_page(login_as()))

    assert "data-shortcut=" not in main
    assert 'class="st-req-link"' not in main
    for link in start_guide.all_links():
        assert f'href="{reverse(link.url_name)}"' not in main, link.key


@pytest.mark.django_db
def test_a_shortcut_appears_only_with_its_permission():
    main = _main(_page(login_as("view_flightpermission")))

    assert f'data-shortcut="permits" href="{reverse("permission-list")}"' in main
    assert 'data-shortcut="aircraft"' not in main
    # El requisito del permiso enlaza a la misma pantalla; los demás no.
    assert main.count('class="st-req-link"') == 1


@pytest.mark.django_db
def test_someone_who_can_do_everything_sees_every_shortcut():
    user = User.objects.create_superuser("root398", password="pw")  # nosec B106
    from django.test import Client

    client = Client()
    client.force_login(user)
    main = _main(_page(client))

    for link in start_guide.SHORTCUTS:
        assert f'data-shortcut="{link.key}" href="{reverse(link.url_name)}"' in main
    assert main.count('class="st-req-link"') == len(start_guide.REQUIREMENT_LINKS)


@pytest.mark.django_db
def test_every_link_asks_at_least_what_its_view_asks():
    """El contrato del menú (`LV-381`): un enlace más flojo que su vista termina en 403."""
    checked = 0
    for link in start_guide.all_links():
        view_class = getattr(resolve(reverse(link.url_name)).func, "view_class", None)
        getter = getattr(view_class, "get_permission_required", None)
        if getter is None:
            continue
        required = set(getter(view_class()))
        assert required <= set(link.permissions), (link.key, sorted(required))
        checked += 1

    assert checked >= 6  # el guardián del guardián


@pytest.mark.django_db
def test_every_link_opens_for_someone_with_exactly_its_permissions():
    """También cubre la sección de cumplimiento, que es una función y no una clase."""
    unique = {
        link.key: link for link in start_guide.all_links()
    }  # un usuario por permiso
    for link in unique.values():
        codenames = [perm.split(".", 1)[1] for perm in link.permissions]
        client = login_as(*codenames)
        status = client.get(reverse(link.url_name)).status_code
        assert status == 200, (link.key, status)


@pytest.mark.django_db
def test_every_permission_named_exists():
    named = {perm for link in start_guide.all_links() for perm in link.permissions}
    existing = {
        f"{app}.{code}"
        for app, code in Permission.objects.values_list(
            "content_type__app_label", "codename"
        )
    }

    assert named - existing == set()


@pytest.mark.django_db
def test_the_page_is_translated_to_spanish():
    """El `.mo` está versionado y el despliegue no lo recompila: se comprueba el compilado."""
    client = login_as()
    with translation.override("es"):
        html = client.get(reverse("start"), HTTP_ACCEPT_LANGUAGE="es").content.decode()

    assert "Ninguna faena vuela sin permiso vigente" in html
    assert "El semáforo de vencimientos" in html


# --- La entrada desde el menú y desde el panel -------------------------------


def test_the_menu_offers_the_page():
    html = full_sidebar_html()

    assert f'<a href="{reverse("start")}" class="nav-item nav-overview' in html
    assert '<span class="nav-label">How it works</span>' in html


@pytest.mark.django_db
def test_the_menu_marks_it_as_current_on_the_page():
    html = _page(login_as())
    sidebar = html[html.index('<aside class="sidebar') : html.index("</aside>")]

    assert (
        f'<a href="{reverse("start")}" class="nav-item nav-overview active" aria-current="page"'
        in sidebar
    )


@pytest.mark.django_db
def test_the_dashboard_card_links_to_the_page_and_loads_its_script():
    html = login_as().get(reverse("dashboard")).content.decode()
    card = html.split('id="start-card"', 1)[1].split("</section>", 1)[0]

    assert f'href="{reverse("start")}"' in card
    # Sin JS el botón de cerrar no aparece: nace oculto y lo muestra el script.
    assert re.search(r"<button[^>]*data-start-card-dismiss[^>]*\bhidden\b", card)
    assert f'aria-label="{gettext("Hide this card")}"' in card
    assert 'src="/static/js/start-card.js"' in html
    # El script va después de la tarjeta, sin `defer`, para que no parpadee.
    assert html.index('id="start-card"') < html.index("js/start-card.js")
    assert 'start-card.js" defer' not in html


def test_every_storage_access_in_the_card_script_is_wrapped_in_try():
    lines = CARD_JS.read_text(encoding="utf-8").splitlines()
    accesses = [
        i
        for i, line in enumerate(lines)
        if "localStorage." in line and not line.lstrip().startswith("//")
    ]

    assert len(accesses) == 2  # la lectura y la escritura
    for index in accesses:
        assert lines[index - 1].strip() == "try {", lines[index]


def test_the_card_script_hides_with_d_none_and_not_only_hidden():
    """`hidden` pierde contra `d-flex` de Bootstrap (LV-209)."""
    js = CARD_JS.read_text(encoding="utf-8")

    assert "classList.add('d-none')" in js
    assert "element.hidden = true" in js


# --- Logos -------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(LOGOS))
def test_each_logo_exists_is_light_and_sharp_enough(name):
    path = LOGOS[name]

    assert path.exists(), path
    assert path.stat().st_size <= LOGO_CEILING
    with Image.open(path) as image:
        assert image.format == "WEBP"
        assert image.mode == "RGBA"  # fondo transparente
        # Nítido a 2x del mayor uso (150 px en la cabecera de «Cómo funciona»).
        assert image.width >= 300
        # El margen transparente se recortó: la marca toca los bordes.
        assert image.getchannel("A").getbbox() == (0, 0, image.width, image.height)


@pytest.mark.django_db
def test_the_start_page_uses_the_pair_one_per_theme():
    html = _page(login_as())
    hero = html.split('<header class="st-hero">', 1)[1].split("</header>", 1)[0]

    assert re.search(
        r'<img class="brand-logo brand-logo--on-light" src="/static/img/jej-logo-blue.webp" alt="J\.E\.J\. [^"]+"',
        hero,
    )
    assert re.search(
        r'<img class="brand-logo brand-logo--on-dark" src="/static/img/jej-logo-white.webp" alt="J\.E\.J\. [^"]+"',
        hero,
    )
    assert html.index("css/imagery.css") < html.index("css/start.css")


def test_the_pair_follows_the_theme_attribute():
    css = IMAGERY_CSS.read_text(encoding="utf-8")

    assert ".brand-logo--on-dark { display: none; }" in css
    assert '[data-theme="dark"] .brand-logo--on-dark { display: inline-block; }' in css
    assert '[data-theme="dark"] .brand-logo--on-light { display: none; }' in css


def test_the_login_uses_white_on_the_navy_panel_and_the_pair_on_the_card():
    login = LOGIN.read_text(encoding="utf-8")
    showcase = login.split('<aside class="login-showcase"', 1)[1].split("</aside>", 1)[
        0
    ]
    footer = login.split('<div class="login-footer">', 1)[1].split(
        "</div>\n    </div>", 1
    )[0]

    assert "img/jej-logo-white.webp" in showcase
    assert "img/jej-logo-blue.webp" not in showcase
    assert "brand-logo--on-light" in footer and "img/jej-logo-blue.webp" in footer
    assert "brand-logo--on-dark" in footer and "img/jej-logo-white.webp" in footer
    assert footer.count('alt="J.E.J. Ingeniería S.A."') == 2


def test_the_pdf_letterhead_keeps_its_own_logo():
    """Los informes PDF no se tocan: siguen con el PNG del membrete (`LV-144`)."""
    from apps.core.branding import LOGO_STATIC_PATH

    assert LOGO_STATIC_PATH == "img/jej-logo-blue.png"
    assert (STATIC / LOGO_STATIC_PATH).exists()


# --- La hoja propia ----------------------------------------------------------


def test_the_sheet_is_under_16_kb_in_lf_bytes():
    assert len(_lf_bytes(START_CSS)) < 16 * 1024


def test_the_sheet_defines_no_tokens_and_has_no_motion():
    css = _lf_bytes(START_CSS).decode("utf-8")

    assert not re.search(r"(?m)^\s*--[\w-]+\s*:", css)
    assert not re.search(r"\banimation(-[a-z]+)?\s*:|@keyframes|transition\s*:", css)


def test_the_sheet_links_no_image_from_another_domain():
    css = _lf_bytes(START_CSS).decode("utf-8")

    for url in re.findall(r"url\(([^)]+)\)", css):
        assert "//" not in url, url
