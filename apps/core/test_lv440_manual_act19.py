"""LV-440: «Cómo funciona» sigue la Actualización 19 del Manual de Operaciones (DGAC, 10-11-2026).

Sólo contenido: plazos de 24 h, niveles de mantención y registro único (REG-016) en lugar de
los plazos y formularios anteriores. Se compara contra `gettext` cuando se puede.
"""

import pytest
from django.urls import reverse
from django.utils import translation
from django.utils.translation import gettext

from apps.core.testing import login_as


def _page(language):
    client = login_as()
    with translation.override(language):
        response = client.get(reverse("start"), HTTP_ACCEPT_LANGUAGE=language)
    assert response.status_code == 200
    return response.content.decode()


@pytest.mark.django_db
def test_the_page_follows_update_19_in_spanish():
    html = _page("es")

    assert "24 h" in html
    assert "Actualización 19" in html
    assert "REG-016" in html
    assert "Cuestionario anual de eficiencia" in html
    assert "Jefe de Seguridad de Vuelo" in html
    assert "Jefe de Seguridad Aérea" not in html
    assert "2 días" not in html
    assert "es opcional" not in html


@pytest.mark.django_db
def test_the_page_follows_update_19_in_english():
    html = _page("en")

    assert "24 h" in html
    assert "Update 19" in html
    assert "2 days" not in html
    assert "training is optional" not in html


def test_the_new_wording_is_in_the_catalogue():
    with translation.override("es"):
        assert "24 h" in gettext(
            "Single Mission Record (REG-016): uploaded to the site folder within 24 h and reviewed within 24 h."
        )
        assert gettext("Head of Air Safety") == "Jefe de Seguridad de Vuelo"


@pytest.mark.django_db
def test_the_questionnaire_text_with_percentages_is_translated():
    html = _page("es")

    assert "Parte A 75 por ciento, Parte B" in html
    assert "examen general (75 por ciento)" in html
