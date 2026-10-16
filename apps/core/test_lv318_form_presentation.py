"""`LV-318` (ola C del rediseño): presentación de los formularios genéricos.

Sólo presentación: errores enlazados con `aria-describedby`, resumen arriba,
barra de acciones y un único botón primario. Los campos, las validaciones y las
vistas no cambian.
"""

import re

import pytest
from django.contrib.auth.models import Permission, User
from django.urls import reverse


@pytest.fixture
def editor(db):
    user = User.objects.create_user("lv318", password="x")
    user.user_permissions.add(
        *Permission.objects.filter(
            codename__in=[
                "add_aircraft",
                "view_aircraft",
                "add_qualificationtype",
                "view_qualificationtype",
            ],
            content_type__app_label="registry",
        )
    )
    return user


def _invalid_page(client, editor):
    client.force_login(editor)
    response = client.post(reverse("aircraft-create"), {})
    assert response.status_code == 200
    return response.content.decode()


def test_invalid_fields_point_to_their_error_with_aria_describedby(client, editor):
    html = _invalid_page(client, editor)
    inputs = re.findall(
        r"<(?:input|select|textarea)[^>]*aria-invalid=\"true\"[^>]*>", html
    )
    assert inputs, "the invalid form must render invalid fields"
    for tag in inputs:
        described = re.search(r'aria-describedby="([^"]+)"', tag)
        assert described, tag
        ids = [i for i in described.group(1).split() if i.endswith("_error")]
        assert ids and all(f'id="{i}"' in html for i in ids), tag


def test_error_summary_is_on_top_and_links_to_the_fields(client, editor):
    html = _invalid_page(client, editor)
    assert 'id="form-error-summary"' in html
    assert html.index('id="form-error-summary"') < html.index('aria-invalid="true"')
    assert re.search(r'<li><a href="#id_[a-z_]+">', html)


def test_action_bar_has_one_primary_and_cancel_as_link(client, editor):
    html = _invalid_page(client, editor)
    bar = html.split('class="form-actions', 1)[1].split("</form>", 1)[0]
    assert len(re.findall(r'class="[^"]*\bbtn-primary\b', bar)) == 1
    assert 'class="btn btn-link"' in bar


def test_modal_form_keeps_the_same_contract(client, editor):
    client.force_login(editor)
    response = client.post(
        reverse("qualificationtype-create"), {}, HTTP_HX_REQUEST="true"
    )
    html = response.content.decode()
    assert 'id="form-error-summary"' in html
    assert 'class="form-actions' in html
    assert len(re.findall(r'class="[^"]*\bbtn-primary\b', html)) == 1
    assert 'data-bs-dismiss="modal"' in html


def test_valid_form_has_no_error_summary(client, editor):
    client.force_login(editor)
    html = client.get(reverse("aircraft-create")).content.decode()
    assert 'id="form-error-summary"' not in html
