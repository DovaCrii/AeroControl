"""`LV-328` (ola E del rediseño): pulido global.

Mensajes con icono y gravedad, estado vacío unificado, foco uniforme, responsivo
a 375 px y un guardián de peso de las hojas de estilo. Sólo presentación.
"""

import re
from pathlib import Path

import pytest
from django.contrib import messages
from django.contrib.auth.models import Permission, User
from django.shortcuts import render
from django.template.loader import render_to_string
from django.urls import path, reverse

from config.urls import urlpatterns as project_urlpatterns

STATIC = Path(__file__).resolve().parents[2] / "static" / "css"


def _emit(request, level):
    messages.add_message(request, level, "Hello LV328")
    return render(request, "base.html")


urlpatterns = [path("lv328-emit/<int:level>/", _emit), *project_urlpatterns]


def _section_e():
    css = (STATIC / "identity.css").read_text(encoding="utf-8")
    start = css.index("/* == E: pulido global == */")
    return css[start : css.index("/* == F:", start)]


@pytest.fixture
def user(db):
    return User.objects.create_user("lv328", password="x", is_superuser=True)


def _message_markup(client, user, level):
    client.force_login(user)
    html = client.get(f"/lv328-emit/{level}/").content.decode()
    match = re.search(r'<div class="alert [^"]*id-message[^>]*>.*?</svg>', html, re.S)
    assert match, "the message was not drawn with the identity markup"
    return match.group(0)


@pytest.mark.urls(__name__)
@pytest.mark.parametrize(
    "level, variant, role",
    [
        (messages.SUCCESS, "success", "status"),
        (messages.INFO, "info", "status"),
        (messages.WARNING, "warning", "status"),
        (messages.ERROR, "danger", "alert"),
    ],
)
def test_each_message_has_icon_severity_and_the_right_role(
    client, user, level, variant, role
):
    markup = _message_markup(client, user, level)
    assert f"id-message--{variant}" in markup
    assert f'role="{role}"' in markup
    assert "<svg" in markup and 'aria-hidden="true"' in markup


@pytest.mark.urls(__name__)
def test_a_message_is_dismissible_but_never_closes_by_itself(client, user):
    client.force_login(user)
    html = client.get(f"/lv328-emit/{messages.SUCCESS}/").content.decode()
    assert 'data-bs-dismiss="alert"' in html
    assert 'aria-label="Cerrar"' in html or 'aria-label="Close"' in html
    assert "data-bs-delay" not in html
    assert "setTimeout" not in _section_e()


def test_only_the_error_message_uses_role_alert():
    base = Path(__file__).resolve().parents[2] / "templates" / "base.html"
    block = re.search(
        r"\{% for message in messages %\}.*?\{% endfor %\}",
        base.read_text(encoding="utf-8"),
        re.S,
    ).group(0)
    assert (
        block.count("role=\"{% if sev == 'danger' %}alert{% else %}status{% endif %}\"")
        == 1
    )


def test_the_empty_art_partial_keeps_working_without_the_new_parameters():
    html = render_to_string("generic/_empty_art.html", {"src": "/x.svg"})
    assert "empty-art-wrap" in html
    assert "empty-state__body" not in html


def test_the_empty_state_action_is_drawn_only_when_the_includer_passes_it():
    context = {
        "title": "Nothing",
        "help": "Help line",
        "action_url": "/new/",
        "action_label": "Create",
    }
    with_action = render_to_string("generic/_empty_art.html", context)
    assert 'class="btn btn-primary">Create' in with_action
    assert "Help line" in with_action
    del context["action_url"]
    assert "btn-primary" not in render_to_string("generic/_empty_art.html", context)


@pytest.mark.django_db
def test_the_empty_kanban_offers_to_create_a_board_only_with_permission(client):
    from apps.workboard.models import KanbanBoard

    assert not KanbanBoard.objects.exists()
    viewer = User.objects.create_user("lv328v", password="x")
    viewer.user_permissions.add(Permission.objects.get(codename="view_kanbantask"))
    client.force_login(viewer)
    html = client.get(reverse("kanban")).content.decode().split("empty-state card")[1]
    assert "empty-state__title" in html
    assert reverse("board-create") not in html

    creator = User.objects.create_user("lv328c", password="x")
    creator.user_permissions.add(
        *Permission.objects.filter(codename__in=["view_kanbantask", "add_kanbanboard"])
    )
    client.force_login(creator)
    html = client.get(reverse("kanban")).content.decode().split("empty-state card")[1]
    assert reverse("board-create") in html


def test_uniform_focus_ring_is_declared_in_section_e():
    css = _section_e()
    block = re.search(r"summary:focus-visible\s*\{([^}]*)\}", css).group(1)
    assert "outline: 2px solid var(--ac-primary)" in block
    assert "outline-offset: 2px" in block
    for selector in ("a:focus-visible", "button:focus-visible", "input:focus-visible"):
        assert selector in css


def test_the_uniform_focus_does_not_override_the_sidebar_or_form_rules():
    """Esos estilos siguen existiendo y con más especificidad que la regla uniforme."""
    css = (STATIC / "identity.css").read_text(encoding="utf-8")
    assert ".sidebar a:focus-visible" in css
    assert ".form-shell .form-control:focus-visible" in css


def test_a_narrow_screen_rule_exists_and_creates_no_second_motion_block():
    css = _section_e()
    assert "max-width: 575.98px" in css
    whole = (STATIC / "identity.css").read_text(encoding="utf-8")
    assert (
        whole.count("prefers-reduced-motion: no-preference") <= 2
    )  # comentario + bloque
    assert "infinite" not in css


def test_the_state_badge_colors_come_from_tokens_not_repeated_hex():
    app = (STATIC / "app.css").read_text(encoding="utf-8")
    for line in app.splitlines():
        if ".badge.bg-danger-subtle" in line:
            assert "var(--sev-critical-bg)" in line
            assert "#fce4e6" not in line and "#3d1a1e" not in line


def test_stylesheet_weight_guard():
    """Techo de peso de las dos hojas juntas.

    La ola E fijó 200 KB (app.css 141.3 KB + identity.css 48.7 KB = ~190 KB al abrir la ola).
    La tanda «Visual v2» (listas, fondos de módulo, panel del asistente y señales) sumó unos
    7 KB más y el techo pasa a 220 KB de forma deliberada: sigue siendo un guardián.
    """
    total = sum((STATIC / name).stat().st_size for name in ("app.css", "identity.css"))
    assert total < 220 * 1024
