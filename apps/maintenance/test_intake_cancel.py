"""LV-388: «Cancelar» en el ingreso a servicio técnico (arriba y con borrado del PDF provisional).

PDF sintético y datos ficticios solamente; el almacenamiento apunta a un `tmp_path`.
"""

import hashlib
import io
import re

import pytest
from django.core import signing
from django.urls import reverse
from django.utils.translation import gettext

from apps.compliance.storage import get_document_storage
from apps.core.models import AuditEvent
from apps.core.testing import login_as
from apps.maintenance.intake_views import (
    INTAKE_SALT,
    PENDING_PREFIX,
    make_token,
    read_token,
)
from apps.maintenance.models import MaintenanceRecord
from apps.maintenance.test_intake_views import (
    NEW_URL,
    operator_client,
    reception_pdf,
    token_of,
    upload,
)
from apps.compliance.models import Document

pytestmark = pytest.mark.django_db

CANCEL_URL = "maintenance-intake-cancel"


@pytest.fixture(autouse=True)
def documents_root(settings, tmp_path):
    settings.DOCUMENTS_ROOT = tmp_path
    return tmp_path


def _pending(client):
    """Sube un PDF y devuelve `(respuesta, token, ruta)`."""
    response = upload(client, reception_pdf())
    token = token_of(response)
    path, _sha = read_token(token, client.user)
    assert get_document_storage().exists(path)
    return response, token, path


def _header(response, end):
    """La región del `page-header` (hasta `end`, lo que viene después): acota la búsqueda."""
    html = response.content.decode()
    return html.split('class="page-header"')[1].split(end)[0]


class TestCancel:
    def test_it_needs_both_permissions(self):
        for codenames in ((), ("add_maintenancerecord",), ("add_document",)):
            client = login_as(*codenames)
            assert client.post(reverse(CANCEL_URL), {"token": "x"}).status_code == 403

    def test_get_is_not_allowed(self):
        client = operator_client()
        assert client.get(reverse(CANCEL_URL)).status_code == 405

    def test_a_valid_token_deletes_the_pending_file_and_saves_nothing(self):
        client = operator_client()
        _response, token, path = _pending(client)

        response = client.post(reverse(CANCEL_URL), {"token": token})

        assert response.status_code == 302
        assert response.url == reverse("maintenance-list")
        assert not get_document_storage().exists(path)
        assert not MaintenanceRecord.objects.exists()
        assert not Document.objects.exists()

    def test_it_is_audited_without_personal_data(self):
        client = operator_client()
        _response, token, path = _pending(client)
        client.post(reverse(CANCEL_URL), {"token": token})

        events = AuditEvent.objects.filter(action="workshop_intake_cancelled")
        assert events.count() == 1
        assert path not in str(events.first().__dict__)

    def test_the_message_is_shown_on_the_list(self):
        client = operator_client("view_maintenancerecord")
        _response, token, _path = _pending(client)
        response = client.post(reverse(CANCEL_URL), {"token": token}, follow=True)
        assert (
            gettext("Intake cancelled; nothing was saved.") in response.content.decode()
        )

    def test_a_token_of_another_user_deletes_nothing(self):
        owner = operator_client()
        _response, token, path = _pending(owner)
        other = login_as("add_maintenancerecord", "add_document", "view_aircraft")

        response = other.post(reverse(CANCEL_URL), {"token": token})

        assert response.status_code == 302
        assert response.url == reverse("maintenance-list")
        assert get_document_storage().exists(path)

    @pytest.mark.parametrize("token", ["", "garbage", "a:b:c"])
    def test_an_altered_token_redirects_without_deleting(self, token):
        client = operator_client()
        _response, _good, path = _pending(client)

        response = client.post(reverse(CANCEL_URL), {"token": token})

        assert response.status_code == 302
        assert response.url == reverse("maintenance-list")
        assert get_document_storage().exists(path)

    def test_an_expired_token_redirects_without_deleting(self, monkeypatch):
        client = operator_client()
        _response, token, path = _pending(client)
        monkeypatch.setattr("apps.maintenance.intake_views.INTAKE_MAX_AGE", -1)

        response = client.post(reverse(CANCEL_URL), {"token": token})

        assert response.status_code == 302
        assert get_document_storage().exists(path)

    def test_a_path_outside_the_pending_area_is_never_deleted(self):
        client = operator_client()
        storage = get_document_storage()
        victim = "other/model/00000000/secret.pdf"
        storage.save(victim, io.BytesIO(reception_pdf()))
        sha = hashlib.sha256(reception_pdf()).hexdigest()
        forged = signing.dumps(
            {"p": victim, "h": sha, "u": str(client.user.pk)}, salt=INTAKE_SALT
        )
        assert not victim.startswith(PENDING_PREFIX)

        response = client.post(reverse(CANCEL_URL), {"token": forged})

        assert response.status_code == 302
        assert storage.exists(victim)


class TestCancelButtons:
    def test_the_upload_screen_has_the_button_in_the_header(self):
        client = operator_client()
        response = client.get(reverse(NEW_URL))
        assert reverse("maintenance-list") in _header(
            response, '<p class="text-body-secondary"'
        )

    def test_the_preview_has_a_cancel_post_form_and_the_button_in_the_header(self):
        client = operator_client()
        response, token, _path = _pending(client)
        html = response.content.decode()
        assert 'form="intake-cancel-form"' in _header(
            response, '<p class="text-body-secondary"'
        )
        form = re.search(r'<form id="intake-cancel-form"[^>]*>', html).group(0)
        assert reverse(CANCEL_URL) in form
        assert f'value="{token}"' in html.split('id="intake-cancel-form"')[1]
        # El del pie se conserva.
        assert html.count('form="intake-cancel-form"') == 2

    def test_make_token_is_the_one_the_cancel_view_reads(self):
        client = operator_client()
        path = f"{PENDING_PREFIX}x.pdf"
        get_document_storage().save(path, io.BytesIO(b"%PDF-1.4"))
        token = make_token(path, "0" * 64, client.user)
        client.post(reverse(CANCEL_URL), {"token": token})
        assert not get_document_storage().exists(path)
