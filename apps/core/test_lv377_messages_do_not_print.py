"""LV-377: los mensajes de confirmación («Informe aprobado…») no se imprimen.

El 2026-10-26 la persona aprobó el informe mensual y lo guardó como PDF desde la misma pantalla:
el aviso verde «Informe aprobado. Queda de sólo lectura.» salió como una hoja propia (el diálogo
decía «Total: 7 páginas») y empujó la portada a la página 2. El bloque de mensajes de `base.html`
no llevaba `d-print-none`. Aquí se fija que el aviso se dibuja en pantalla y **no** en papel.
"""

import re
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.registry.models import CostCenter, Operator

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def archived_page(client, db):
    user = get_user_model().objects.create_superuser("root", "root@test.com", "pw")
    client.force_login(user)
    center = CostCenter.objects.create(code="CC900", name="Prueba")
    operator = Operator.objects.create(
        employee_id="RUT-181818180", full_name="Persona de prueba", cost_center=center
    )
    response = client.post(reverse("operator-archive", args=[operator.pk]), follow=True)
    assert response.status_code == 200
    return response.content.decode()


def test_the_flash_message_is_drawn_on_screen(archived_page):
    assert 'class="alert alert-success' in archived_page


def test_the_message_wrapper_is_hidden_when_printing(archived_page):
    wrapper = re.search(r'<div class="([^"]*)" aria-live="polite">', archived_page)
    assert wrapper, "el bloque de mensajes debería existir con un mensaje pendiente"
    assert "d-print-none" in wrapper.group(1).split()


def test_the_print_rule_that_hides_it_exists():
    css = (ROOT / "static" / "css" / "app.css").read_text(encoding="utf-8")
    block = css.split("@media print {", 1)[1]
    assert ".d-print-none { display: none !important; }" in block
