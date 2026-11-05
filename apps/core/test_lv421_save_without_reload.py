"""`LV-421`: guardar en el modal no recarga la página (UX T9).

El servidor no cambia de contrato (204 + `HX-Trigger: modal-form-success`); lo que
cambia es que `app.js` refresca la región marcada y el contenedor de avisos en vez
de recargar. Se afirma sobre los archivos porque `app.js` es estático.
"""

import re

import pytest
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.urls import reverse

from apps.core.test_lv315_identity_foundation import ROOT

APP_JS = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
TEMPLATES = ROOT / "templates"


def _handler():
    return APP_JS.split("'modal-form-success'", 1)[1].split("});", 1)[0]


def _marked_templates():
    return [
        path
        for path in TEMPLATES.rglob("*.html")
        if "data-refresh-on-save" in path.read_text(encoding="utf-8")
    ]


def test_the_messages_container_is_always_in_base(client, django_user_model):
    user = django_user_model.objects.create_user("lv421-user", password="x")
    client.force_login(user)
    content = client.get(reverse("dashboard")).content.decode()
    tag = re.search(r'<div[^>]*id="page-messages"[^>]*>', content).group(0)
    assert 'aria-live="polite"' in tag and 'hx-swap-oob="true"' in tag
    assert "mb-3" not in tag


def test_a_message_goes_inside_the_container(rf):
    request = rf.get("/")
    request.user = get_user_model()(username="x")
    request.session = {}
    from django.contrib.messages.storage.fallback import FallbackStorage

    request._messages = FallbackStorage(request)
    messages.success(request, "Saved it")
    html = render_to_string("base.html", {"messages": messages.get_messages(request)})
    box = html.split('id="page-messages"', 1)[1].split("</main>", 1)[0]
    assert "Saved it" in box and "mb-3" in box.split(">", 1)[0]


def test_the_handler_no_longer_reloads_unconditionally():
    body = _handler()
    assert "modalDirty = false;" in body
    assert "window.location.reload()" not in body
    assert "refreshAfterSave()" in body
    # El reload sólo vive en el camino de respaldo, que guarda la posición.
    assert APP_JS.count("window.location.reload()") == 1
    fallback = APP_JS.split("function reloadKeepingScroll", 1)[1].split(
        "function restoreScroll", 1
    )[0]
    assert "window.location.reload()" in fallback and "sessionStorage" in fallback
    refresh = APP_JS.split("function refreshAfterSave", 1)[1]
    assert "[data-refresh-on-save][id]" in refresh
    assert "reloadKeepingScroll" in refresh


def test_the_refresh_asks_for_the_full_page_and_swaps_messages_too():
    refresh = APP_JS.split("function refreshAfterSave", 1)[1].split(
        "document.body.addEventListener('modal-form-success'", 1
    )[0]
    # Con HX-Request las listas devuelven sólo el cuerpo de la tabla.
    assert "HX-Request" not in refresh
    assert "page-messages" in refresh
    assert "htmx:afterSwap" in refresh


def test_every_session_storage_access_is_guarded():
    saved = APP_JS.split("var SCROLL_KEY", 1)[1].split("function announceMessages", 1)[
        0
    ]
    assert saved.count("try {") >= 2 and saved.count("catch") >= 2


def test_there_are_marked_lists():
    names = {p.relative_to(TEMPLATES).as_posix() for p in _marked_templates()}
    assert {
        "generic/worktable.html",
        "registry/assignment_list.html",
        "compliance/company_documents.html",
    } <= names


def test_every_marked_region_carries_a_stable_id():
    for path in _marked_templates():
        text = path.read_text(encoding="utf-8")
        for tag in re.findall(r"<[a-z]+[^>]*data-refresh-on-save[^>]*>", text):
            assert re.search(r'\sid="[a-z0-9-]+"', tag), path


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url_name", ["alert-list", "aircraft-list", "assignment-list", "company-documents"]
)
def test_the_full_page_returns_the_marked_region(client, url_name):
    root = get_user_model().objects.create_superuser("lv421-root", password="pw")
    client.force_login(root)
    content = client.get(reverse(url_name)).content.decode()
    assert re.search(r'id="table-wrapper"[^>]*data-refresh-on-save', content)
    assert 'id="page-messages"' in content


def test_the_floating_notice_style_lives_in_the_htmx_state_sheet():
    css = (ROOT / "static" / "css" / "htmx-state.css").read_text(encoding="utf-8")
    assert ".page-messages--floating" in css
