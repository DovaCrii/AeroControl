"""LV-419: estado de carga y de error de htmx, global (UX T10)."""

import re

from django.urls import reverse

from apps.core.test_lv315_identity_foundation import ROOT

JS = ROOT / "static" / "js" / "htmx-state.js"
CSS = ROOT / "static" / "css" / "htmx-state.css"


def _page(client, django_user_model):
    user = django_user_model.objects.create_user("htmx-user", password="x")
    client.force_login(user)
    return client.get(reverse("dashboard")).content.decode()


def test_the_error_message_rides_translated_on_the_live_region(
    client, django_user_model, settings
):
    from django.utils import translation

    with translation.override("es"):
        content = _page(client, django_user_model)
    tag = re.search(r'<div[^>]*id="htmx-status"[^>]*>', content).group(0)
    assert 'role="alert"' in tag
    assert (
        'data-error-label="No se pudo actualizar la lista. Vuelva a intentarlo."' in tag
    )
    assert "/static/js/htmx-state.js" in content
    assert "/static/css/htmx-state.css" in content


def test_the_script_listens_to_the_htmx_events_and_carries_no_text():
    js = JS.read_text(encoding="utf-8")
    for event in (
        "htmx:beforeRequest",
        "htmx:afterRequest",
        "htmx:responseError",
        "htmx:sendError",
    ):
        assert f"'{event}'" in js
    assert "aria-busy" in js and "is-loading" in js
    assert "dataset.errorLabel" in js
    assert "No se pudo" not in js and "could not be updated" not in js


def test_the_dimming_transition_only_runs_without_reduced_motion():
    css = CSS.read_text(encoding="utf-8")
    plain, _, guarded = css.partition("@media (prefers-reduced-motion: no-preference)")
    assert "opacity: 0.6" in plain
    assert "transition" not in plain
    assert "transition: opacity" in guarded


def test_the_modal_form_disables_its_submit_button_while_sending():
    html = (ROOT / "templates" / "generic" / "_form_content.html").read_text(
        encoding="utf-8"
    )
    assert 'hx-disabled-elt="find button[type=submit]"' in html
