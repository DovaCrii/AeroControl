"""LV-405: dar de alta un operador con su credencial DGAC (PDF) en un solo paso.

El PDF es **sintético** (`reportlab`, nombres, números y RUT ficticios). Lo que se fija:

- subir deja el archivo provisional, sin crear nada, y prellena el alta con lo leído;
- guardar crea el operador **y** su documento (con la empresa del operador) y deja el
  archivo definitivo, sin el provisional;
- un error de formulario conserva el token; un token ajeno o alterado no se usa;
- cancelar borra el provisional.
"""

import io
from datetime import date
from pathlib import Path

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core import signing
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import translation

from apps.compliance.models import Document, DocumentType
from apps.core.testing import login_as
from apps.registry import operator_intake
from apps.registry.models import Operator

SENTINEL_RUT = "12.345.678-5"
LINES = [
    "Credencial de Piloto RPA",
    "N° Credencial: ZX-4417",
    "Titular: Juan Perez Soto",
    f"RUT: {SENTINEL_RUT}",
    "Fecha de emisión: 15/03/2024",
    "Vencimiento: 15/03/2029",
]
BOTH = ("add_operator", "add_document", "view_operator")


def _pdf(lines):
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    page = canvas.Canvas(buffer)
    for index, line in enumerate(lines):
        page.drawString(70, 750 - index * 20, line)
    page.save()
    return buffer.getvalue()


@pytest.fixture
def scene(db, settings, tmp_path):
    settings.DOCUMENTS_ROOT = str(tmp_path)
    DocumentType.objects.get_or_create(
        code="dgac-credential",
        defaults={"name": "Credencial DGAC", "requires_expiry": True},
    )
    return tmp_path


def _upload(client, data=None, name="cred.pdf"):
    data = data if data is not None else _pdf(LINES)
    return client.post(
        reverse("operator-credential-intake"),
        {"file": SimpleUploadedFile(name, data, content_type="application/pdf")},
    )


def _token(response):
    assert response.status_code == 302, response.content[:300]
    location = response["Location"]
    assert location.startswith(reverse("operator-create") + "?credential=")
    return location.split("credential=")[1]


def _pending_files(root):
    return list(Path(root, "workshop-intake-pending", "operator-credential").glob("*"))


def _form(token, **overrides):
    data = {
        "full_name": "Juan Perez Soto",
        "rut": "12345678-5",
        "dgac_credential": "ZX-4417",
        "credential_expiry": "2029-03-15",
        "operator_type": "pilot",
        "credential_token": token,
    }
    data.update(overrides)
    return {key: value for key, value in data.items() if value is not None}


# --- permisos ----------------------------------------------------------------


@pytest.mark.parametrize("codenames", [("add_operator",), ("add_document",), ()])
def test_uploading_needs_both_permissions(scene, codenames):
    client = login_as(*codenames)

    assert _upload(client).status_code == 403
    assert (
        client.post(reverse("operator-credential-intake-cancel"), {}).status_code == 403
    )
    assert _pending_files(scene) == []


def test_the_upload_block_only_shows_with_permission_to_add_documents(scene):
    only_operator = login_as("add_operator")
    body = only_operator.get(reverse("operator-create")).content.decode()
    assert "credential-intake" not in body

    both = login_as(*BOTH)
    assert "credential-intake" in both.get(reverse("operator-create")).content.decode()


# --- subir y prellenar ---------------------------------------------------------


def test_uploading_prefills_the_form_and_creates_nothing(scene):
    client = login_as(*BOTH)

    token = _token(_upload(client))

    assert Operator.objects.count() == 0
    assert Document.objects.count() == 0
    assert len(_pending_files(scene)) == 1
    body = client.get(
        reverse("operator-create"), {"credential": token}
    ).content.decode()
    assert "data-credential-read" in body
    assert 'value="Juan Perez Soto"' in body
    assert 'value="ZX-4417"' in body
    assert 'value="2029-03-15"' in body
    assert "12.345.678-5" in body
    assert f'name="credential_token" value="{token}"' in body


def test_an_unreadable_pdf_leaves_the_form_empty_with_a_neutral_notice(scene):
    client = login_as(*BOTH)

    token = _token(_upload(client, _pdf([])))

    body = client.get(
        reverse("operator-create"), {"credential": token}
    ).content.decode()
    assert "data-credential-unreadable" in body
    assert 'value="ZX-4417"' not in body
    # El archivo queda para adjuntarse igual.
    assert f'name="credential_token" value="{token}"' in body


def test_a_file_that_is_not_a_pdf_is_refused(scene):
    client = login_as(*BOTH)

    response = _upload(client, b"plain text", name="cred.txt")

    assert response["Location"] == reverse("operator-create")
    assert _pending_files(scene) == []


def test_a_bad_token_on_the_form_page_asks_to_upload_again(scene, settings):
    client = login_as(*BOTH)

    response = client.get(
        reverse("operator-create"), {"credential": "garbage"}, follow=True
    )

    body = response.content.decode()
    with translation.override(settings.LANGUAGE_CODE):
        expected = translation.gettext(
            "The credential upload expired or is no longer valid. Upload it again."
        )
    assert expected in body
    assert "credential_token" not in body


# --- guardar -------------------------------------------------------------------


def test_saving_creates_the_operator_and_its_credential_document(scene):
    client = login_as(*BOTH)
    token = _token(_upload(client))

    response = client.post(reverse("operator-create"), _form(token))

    assert response.status_code == 302, response.content[:400]
    operator = Operator.objects.get()
    document = Document.objects.get()
    assert document.content_type == ContentType.objects.get_for_model(Operator)
    assert document.object_id == operator.pk
    assert document.tenant_id == operator.tenant_id
    assert document.doc_type.code == "dgac-credential"
    assert document.content_sha256
    assert document.is_current_version is True
    assert document.issue_date == date(2024, 3, 15)
    assert document.expiry_date == date(2029, 3, 15)
    assert not document.file_path.startswith("workshop-intake-pending/")
    assert Path(scene, document.file_path).read_bytes().startswith(b"%PDF")
    assert _pending_files(scene) == []


def test_a_form_error_keeps_the_token_and_the_file(scene):
    client = login_as(*BOTH)
    token = _token(_upload(client))

    response = client.post(reverse("operator-create"), _form(token, full_name=""))

    assert response.status_code == 200
    assert Operator.objects.count() == 0
    assert Document.objects.count() == 0
    assert len(_pending_files(scene)) == 1
    assert f'name="credential_token" value="{token}"' in response.content.decode()


def test_another_persons_token_is_not_used(scene):
    owner = login_as(*BOTH)
    token = _token(_upload(owner))
    other = login_as(*BOTH, "view_document")

    response = other.post(reverse("operator-create"), _form(token))

    assert response.status_code == 302
    assert Operator.objects.count() == 1
    assert Document.objects.count() == 0
    # No era suyo: el provisional de la otra persona sigue ahí.
    assert len(_pending_files(scene)) == 1


def test_a_tampered_or_foreign_prefix_token_is_not_used(scene):
    client = login_as(*BOTH)
    token = _token(_upload(client))

    client.post(reverse("operator-create"), _form(token + "x"))
    forged = signing.dumps(
        {"p": "documents/anything.pdf", "h": "0" * 64, "u": str(client.user.pk)},
        salt=operator_intake.INTAKE_SALT,
        compress=False,
    )
    client.post(
        reverse("operator-create"),
        _form(
            forged,
            full_name="Otra Persona",
            rut="11111111-1",
            dgac_credential="ZX-9999",
        ),
    )

    assert Document.objects.count() == 0
    assert Operator.objects.count() == 2
    assert len(_pending_files(scene)) == 1


def test_a_token_without_permission_to_add_documents_is_ignored(scene):
    owner = login_as(*BOTH)
    token = _token(_upload(owner))
    limited = login_as("add_operator")
    # El token es de otra persona y además ésta no puede subir documentos.
    limited.post(reverse("operator-create"), _form(token))

    assert Document.objects.count() == 0


# --- cancelar --------------------------------------------------------------------


def test_cancelling_deletes_the_provisional_file(scene):
    client = login_as(*BOTH)
    token = _token(_upload(client))
    assert len(_pending_files(scene)) == 1

    response = client.post(
        reverse("operator-credential-intake-cancel"), {"token": token}
    )

    assert response["Location"] == reverse("operator-list")
    assert _pending_files(scene) == []
    assert Operator.objects.count() == 0


def test_cancelling_with_a_bad_or_foreign_token_does_not_fail_or_delete(scene):
    owner = login_as(*BOTH)
    token = _token(_upload(owner))
    other = login_as(*BOTH, "view_document")

    for bad in ("garbage", token):
        response = other.post(
            reverse("operator-credential-intake-cancel"), {"token": bad}
        )
        assert response.status_code == 302

    assert len(_pending_files(scene)) == 1
