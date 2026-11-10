"""LV-426: la ficha de mantención al estándar visual de las demás fichas.

Usa la cabecera común (`_entity_head`), nombra la aeronave en el título, pone el
estado como chip con el tono del filtro `status_tone`, sube el recorrido bajo la
cabecera (antes de documentos) y no deja `style` ni `onsubmit` en línea. El cierre
con errores re-renderiza esta misma plantilla y tiene que seguir dibujándolos.
"""

from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse

from apps.core.templatetags.aero_tags import status_tone
from apps.core.testing import login_as, without_template_comments
from apps.maintenance.models import MaintenanceRecord
from apps.registry.models import Aircraft

TEMPLATE = Path(settings.BASE_DIR) / "templates/maintenance/record_detail.html"
HEAD = '<header class="entity-bar">'


def _record(status="pending"):
    aircraft = Aircraft.objects.create(
        registration="CC-LV426", type="RPA", model="M3", manufacturer="DJI"
    )
    return MaintenanceRecord.objects.create(
        aircraft=aircraft,
        maintenance_type="preventive",
        description="Revision",
        status=status,
    )


def _html(client, record):
    response = client.get(reverse("maintenance-detail", args=[record.pk]))
    assert response.status_code == 200
    return response.content.decode()


@pytest.mark.django_db
def test_the_ficha_uses_the_shared_head_and_names_the_aircraft():
    record = _record()
    html = _html(login_as("view_maintenancerecord"), record)

    head = html.split(HEAD)[1].split("</header>")[0]
    assert record.aircraft.registration in head
    assert record.get_maintenance_type_display() in head


@pytest.mark.django_db
@pytest.mark.parametrize(
    "status", [code for code, _label in MaintenanceRecord.STATUSES]
)
def test_the_status_chip_uses_the_status_tone(status):
    record = _record(status)
    html = _html(login_as("view_maintenancerecord"), record)

    head = html.split(HEAD)[1].split("</header>")[0]
    assert f"id-chip--{status_tone(record.status)}" in head
    assert record.get_status_display() in head


@pytest.mark.django_db
def test_the_steps_come_before_the_documents_section():
    record = _record()
    html = _html(login_as("view_maintenancerecord", "view_document"), record)

    assert 'id="status-steps"' in html
    assert 'id="tab-documents"' in html
    assert html.index('id="status-steps"') < html.index('id="tab-documents"')
    assert html.index(HEAD) < html.index('id="status-steps"')


@pytest.mark.django_db
def test_the_main_transition_is_primary_and_the_rest_secondary():
    record = _record("pending")
    html = _html(login_as("view_maintenancerecord"), record)

    start = html.split('action="start/"')[1].split("</form>")[0]
    send = html.split('action="send/"')[1].split("</form>")[0]
    assert "btn-primary" in start
    assert "btn-outline-secondary" in send


@pytest.mark.django_db
def test_void_keeps_its_confirmation_and_is_outline_danger():
    record = _record("pending")
    html = _html(login_as("view_maintenancerecord", "change_maintenancerecord"), record)

    void = html.split(f'action="{reverse("maintenance-void", args=[record.pk])}"')[1]
    void = void.split("</form>")[0]
    assert "btn-outline-danger" in void
    assert (
        "data-confirm"
        in html.split(f'action="{reverse("maintenance-void", args=[record.pk])}"')[
            1
        ].split(">")[0]
    )


def test_the_template_has_no_inline_style_display_or_onsubmit():
    source = without_template_comments(TEMPLATE.read_text(encoding="utf-8"))

    assert 'style="display:inline"' not in source
    assert "onsubmit=" not in source


@pytest.mark.django_db
def test_an_invalid_completion_still_draws_its_errors():
    record = _record("in_progress")
    client = login_as("view_maintenancerecord", "change_maintenancerecord")

    response = client.post(reverse("maintenance-complete", args=[record.pk]), {})

    assert response.status_code == 200
    html = response.content.decode()
    assert HEAD in html
    assert "is-invalid" in html or "invalid-feedback" in html or "errorlist" in html


@pytest.mark.django_db
def test_the_ficha_needs_view_permission():
    record = _record()

    response = login_as().get(reverse("maintenance-detail", args=[record.pk]))

    assert response.status_code == 403
