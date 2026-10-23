"""LV-368 fase 3: subir la credencial DGAC, leerla, proponer y confirmar.

Lo que estos tests fijan **no** es que la lectura acierte con una credencial real --
nunca se vio una, y el PDF de estos tests es **sintético** (generado con `reportlab`,
con nombres, números y RUT ficticios) --. Fijan lo que sí está bajo nuestro control:

- que la lectura proponga y **no escriba**: nada cambia en el `Operator` hasta el paso 3;
- que se calle ante la duda (dos candidatos, fecha imposible);
- que lo no confirmado no se guarde;
- que el RUT leído sirva para comparar y **no aparezca en ninguna parte**.
"""

import io
import json
import logging
from datetime import date

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.compliance.models import Alert, AlertRule, Document, DocumentType
from apps.core.models import AuditEvent, OperationalTenant
from apps.core.testing import login_as
from apps.registry import credential_reader as reader
from apps.registry.models import Operator

# Todo ficticio. El RUT es válido en su dígito verificador a propósito (una ficha lo
# exige) y es el **centinela**: si aparece en una respuesta o en la auditoría, el test
# que lo busca falla.
SENTINEL_RUT = "12.345.678-5"
OWN_RUT = "12345678-5"

CREDENTIAL_LINES = [
    "Credencial de Piloto RPA",
    "N° Credencial: ZX-4417",
    "Titular: Juan Perez Soto",
    f"RUT: {SENTINEL_RUT}",
    "Fecha de emisión: 15/03/2024",
    "Vencimiento: 15/03/2029",
    "Clase: Clase 2",
    "Restricciones: Solo VLOS",
]

BOTH = ("add_document", "change_operator", "view_operator", "view_document")


def _pdf(lines):
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    page = canvas.Canvas(buffer)
    for index, line in enumerate(lines):
        page.drawString(70, 750 - index * 20, line)
    page.save()
    return buffer.getvalue()


def _upload(client, operator, lines=None, *, name="cred.pdf", content=None):
    data = content if content is not None else _pdf(lines or CREDENTIAL_LINES)
    return client.post(
        reverse("operator-credential-upload", args=[operator.pk]),
        {"file": SimpleUploadedFile(name, data, content_type="application/pdf")},
    )


@pytest.fixture
def scene(db, settings, tmp_path):
    settings.DOCUMENTS_ROOT = str(tmp_path)
    DocumentType.objects.get_or_create(
        code="dgac-credential",
        defaults={"name": "Credencial DGAC", "requires_expiry": True},
    )
    operator = Operator.objects.create(
        employee_id="OP-1",
        full_name="Juan Perez Soto",
        rut=OWN_RUT,
        dgac_credential="OLD-1",
        credential_expiry=date(2026, 12, 1),
    )
    return operator


def _confirm_url(response):
    assert response.status_code == 302, response.content[:300]
    return response["Location"]


def _snapshot(operator):
    operator.refresh_from_db()
    return (operator.dgac_credential, operator.credential_expiry)


# --- el lector -------------------------------------------------------------


class TestReader:
    def test_a_clean_credential_gives_exact_proposals(self):
        found = reader.credential_from_text("\n".join(CREDENTIAL_LINES))
        assert found[reader.NUMBER].value == "ZX-4417"
        assert found[reader.NUMBER].confidence == reader.EXACT
        assert found[reader.ISSUE_DATE].value == date(2024, 3, 15)
        assert found[reader.EXPIRY_DATE].value == date(2029, 3, 15)
        assert found[reader.CLASS_].value == "Clase 2"
        assert found[reader.RESTRICTIONS].value == "Solo VLOS"

    def test_a_loose_label_is_doubtful_not_exact(self):
        found = reader.credential_from_text("Válido hasta: 01/02/2030")
        assert found[reader.EXPIRY_DATE].confidence == reader.DOUBTFUL

    def test_two_different_candidates_leave_the_field_without_a_proposal(self):
        text = "N° Credencial: AA-111\nN° Credencial: BB-222\nVencimiento: 01/02/2030"
        found = reader.credential_from_text(text)
        assert reader.NUMBER not in found
        # y un campo con una sola respuesta sigue proponiéndose
        assert found[reader.EXPIRY_DATE].value == date(2030, 2, 1)

    def test_the_same_value_twice_is_still_one_candidate(self):
        found = reader.credential_from_text(
            "N° Credencial: AA-111\nCredencial N° AA-111"
        )
        assert found[reader.NUMBER].confidence == reader.EXACT

    def test_an_impossible_date_gives_no_proposal(self):
        found = reader.credential_from_text("Vencimiento: 31/02/2030")
        assert reader.EXPIRY_DATE not in found

    def test_a_range_is_two_candidates_so_it_gives_nothing(self):
        found = reader.credential_from_text("Vigencia: 01/01/2024 - 01/01/2029")
        assert reader.EXPIRY_DATE not in found

    @pytest.mark.parametrize(
        "text",
        [
            "Vencimiento: 05-07-2031",
            "Vencimiento: 05.07.2031",
            "Vencimiento: 2031-07-05",
            "Vencimiento: 5 de julio de 2031",
        ],
    )
    def test_date_variants(self, text):
        found = reader.credential_from_text(text)
        assert found[reader.EXPIRY_DATE].value == date(2031, 7, 5)

    def test_a_label_alone_on_its_line_takes_the_next_line(self):
        found = reader.credential_from_text(
            "N° Credencial\nZX-4417\nVencimiento\n15/03/2029"
        )
        assert found[reader.NUMBER].value == "ZX-4417"
        assert found[reader.EXPIRY_DATE].value == date(2029, 3, 15)

    def test_fragments_are_short_and_never_carry_the_rut_or_the_holder(self):
        found = reader.credential_from_text("\n".join(CREDENTIAL_LINES))
        for proposal in found.values():
            assert len(proposal.fragment) <= reader.FRAGMENT_MAX
        for field in (reader.RUT, reader.HOLDER):
            assert "345" not in found[field].fragment
            assert "Perez" not in found[field].fragment

    def test_a_rut_on_the_same_line_does_not_leak_into_another_fragment(self):
        found = reader.credential_from_text(
            f"N° Credencial: ZX-4417   RUT: {SENTINEL_RUT}"
        )
        assert "345" not in found[reader.NUMBER].fragment

    def test_garbage_gives_nothing_and_never_raises(self):
        assert reader.credential_from_text("") == {}
        assert reader.credential_from_text("lorem ipsum 123") == {}
        assert reader.credential_from_pdf(io.BytesIO(b"not a pdf")) is None


# --- el flujo --------------------------------------------------------------


def test_uploading_saves_the_document_and_touches_nothing_on_the_operator(scene):
    client = login_as(*BOTH)
    before = _snapshot(scene)

    response = _upload(client, scene)

    document = Document.objects.get()
    assert _confirm_url(response) == reverse(
        "operator-credential-confirm", args=[scene.pk, document.pk]
    )
    assert document.tenant_id == scene.tenant_id
    assert document.content_sha256
    assert document.file_path.endswith("cred.pdf")
    assert document.is_current_version is False
    assert _snapshot(scene) == before


def test_the_confirmation_screen_proposes_and_accepts_nothing_by_default(scene):
    client = login_as(*BOTH)
    url = _confirm_url(_upload(client, scene))

    response = client.get(url)

    body = response.content.decode()
    assert response.status_code == 200
    assert "ZX-4417" in body
    assert "2029-03-15" in body
    assert "Clase 2" in body
    # Ninguna propuesta viene aceptada: ninguna casilla `checked`.
    assert 'name="use_number"' in body
    for field in reader.WRITABLE_FIELDS:
        tag = body.split(f'id="id-use-{field}"')[1].split(">")[0]
        assert "checked" not in tag
    # Y leer tampoco cambió nada.
    assert _snapshot(scene) == ("OLD-1", date(2026, 12, 1))


def test_confirming_only_writes_what_was_ticked(scene):
    client = login_as(*BOTH)
    url = _confirm_url(_upload(client, scene))

    response = client.post(
        url,
        {
            "use_number": "1",
            "value_number": "ZX-4417",
            # la fecha viene con valor pero SIN «Usar»: no se escribe
            "value_expiry_date": "2029-03-15",
        },
    )

    assert response.status_code == 302
    assert _snapshot(scene) == ("ZX-4417", date(2026, 12, 1))


def test_the_post_ignores_what_the_client_claims_was_read(scene):
    """El servidor vuelve a leer: un campo inventado no cambia nada."""
    client = login_as(*BOTH)
    url = _confirm_url(_upload(client, scene))

    client.post(
        url,
        {
            "use_number": "1",
            "value_number": "ZX-4417",
            "use_expiry_date": "1",
            "value_expiry_date": "2031-01-01",
            "read_number": "FORGED-9",
            "proposal_number": "FORGED-9",
        },
    )

    scene.refresh_from_db()
    assert scene.dgac_credential == "ZX-4417"
    assert scene.credential_expiry == date(2031, 1, 1)
    event = AuditEvent.objects.get(action="operator_credential_confirmed")
    # el vencimiento difiere de lo leído: es tecleado; el número coincide: del PDF
    assert event.metadata["fields_from_pdf"] == ["number"]
    assert event.metadata["fields_typed"] == ["expiry_date"]


def test_confirming_completes_the_document_and_makes_it_current(scene):
    client = login_as(*BOTH)
    old = Document.objects.create(
        tenant=scene.tenant,
        content_type=ContentType.objects.get_for_model(Operator),
        object_id=scene.pk,
        doc_type=DocumentType.objects.get(code="dgac-credential"),
        title="Anterior",
        file_path="old.pdf",
        issue_date=date(2020, 1, 1),
        expiry_date=date(2026, 12, 1),
    )
    url = _confirm_url(_upload(client, scene))

    client.post(
        url,
        {
            "use_number": "1",
            "value_number": "ZX-4417",
            "use_issue_date": "1",
            "value_issue_date": "2024-03-15",
            "use_expiry_date": "1",
            "value_expiry_date": "2029-03-15",
        },
    )

    new = Document.objects.exclude(pk=old.pk).get()
    old.refresh_from_db()
    assert (new.issue_date, new.expiry_date) == (date(2024, 3, 15), date(2029, 3, 15))
    assert new.is_current_version is True
    assert old.is_current_version is False


def test_confirming_resolves_the_expiry_alert(scene):
    rule = AlertRule.objects.create(
        name="Credenciales por vencer",
        entity_type="registry.operator",
        field_to_watch="credential_expiry",
        days_before_expiry=30,
    )
    alert = Alert.objects.create(
        alert_rule=rule,
        content_type=ContentType.objects.get_for_model(Operator),
        object_id=scene.pk,
        message="Expiring soon",
    )
    client = login_as(*BOTH)
    url = _confirm_url(_upload(client, scene))
    alert.refresh_from_db()
    assert alert.is_resolved is False  # subir y leer no resuelven nada

    client.post(
        url,
        {"use_expiry_date": "1", "value_expiry_date": "2031-05-01"},
    )

    alert.refresh_from_db()
    assert alert.is_resolved is True


def test_a_repeated_number_is_refused_naming_the_owner(scene):
    Operator.objects.create(
        employee_id="OP-2", full_name="Maria Gonzalez Ruiz", dgac_credential="zx-4417"
    )
    client = login_as(*BOTH)
    url = _confirm_url(_upload(client, scene))

    response = client.post(url, {"use_number": "1", "value_number": "ZX-4417"})

    assert response.status_code == 200
    assert "Maria Gonzalez Ruiz" in response.content.decode()
    assert _snapshot(scene) == ("OLD-1", date(2026, 12, 1))


def test_number_and_expiry_are_required(scene):
    scene.credential_expiry = None
    scene.save()
    client = login_as(*BOTH)
    url = _confirm_url(_upload(client, scene))

    response = client.post(url, {"use_number": "1", "value_number": "ZX-4417"})

    assert response.status_code == 200
    assert _snapshot(scene) == ("OLD-1", None)


def test_expiry_must_be_after_issue(scene):
    client = login_as(*BOTH)
    url = _confirm_url(_upload(client, scene))

    response = client.post(
        url,
        {
            "use_issue_date": "1",
            "value_issue_date": "2030-01-01",
            "use_expiry_date": "1",
            "value_expiry_date": "2029-01-01",
        },
    )

    assert response.status_code == 200
    assert _snapshot(scene) == ("OLD-1", date(2026, 12, 1))


def test_nothing_ticked_changes_nothing(scene):
    client = login_as(*BOTH)
    url = _confirm_url(_upload(client, scene))

    response = client.post(url, {"value_number": "ZX-4417"})

    assert response.status_code == 200
    assert _snapshot(scene) == ("OLD-1", date(2026, 12, 1))


def test_a_different_holder_warns_but_does_not_block(scene):
    client = login_as(*BOTH)
    lines = [
        line.replace("Juan Perez Soto", "Pedro Lopez Diaz") for line in CREDENTIAL_LINES
    ]
    url = _confirm_url(_upload(client, scene, lines))

    page = client.get(url).content.decode()
    assert 'data-holder-state="mismatch"' in page
    assert "Pedro" not in page

    response = client.post(
        url, {"use_number": "1", "value_number": "ZX-4417"}, follow=True
    )

    assert scene.__class__.objects.get(pk=scene.pk).dgac_credential == "ZX-4417"
    warnings = [str(m) for m in response.context["messages"]]
    assert any(
        "titular" in text.lower() or "holder" in text.lower() for text in warnings
    )


def test_the_same_holder_with_a_different_word_order_matches(scene):
    client = login_as(*BOTH)
    lines = [
        line.replace("Juan Perez Soto", "Pérez Soto Juan") for line in CREDENTIAL_LINES
    ]
    url = _confirm_url(_upload(client, scene, lines))

    assert 'data-holder-state="match"' in client.get(url).content.decode()


def test_a_photo_is_saved_without_a_proposal_and_says_so_neutrally(scene):
    client = login_as(*BOTH)
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    response = client.post(
        reverse("operator-credential-upload", args=[scene.pk]),
        {"file": SimpleUploadedFile("cred.png", png, content_type="image/png")},
    )
    url = _confirm_url(response)
    assert Document.objects.filter(file_path__endswith="cred.png").exists()

    page = client.get(url).content.decode()

    assert "data-credential-unreadable" in page
    assert "alert-danger" not in page
    # el formulario trae los valores actuales y nada propuesto
    assert 'value="OLD-1"' in page
    assert _snapshot(scene) == ("OLD-1", date(2026, 12, 1))


def test_an_unreadable_log_line_carries_no_content(scene, caplog):
    client = login_as(*BOTH)
    with caplog.at_level(logging.INFO):
        url = _confirm_url(
            _upload(client, scene, content=b"%PDF-1.4\nnot really a pdf at all")
        )
        client.get(url)
    assert "credential_unreadable" in caplog.text
    assert "OLD-1" not in caplog.text and "Perez" not in caplog.text


def test_the_rut_is_only_compared_never_shown_stored_or_audited(scene, caplog):
    client = login_as(*BOTH)
    seen = []
    with caplog.at_level(logging.DEBUG):
        upload = _upload(client, scene)
        url = _confirm_url(upload)
        page = client.get(url)
        seen.append(page.content.decode())
        assert 'data-rut-state="match"' in seen[-1]
        # POST válido (redirige: no se sigue, porque la ficha del operador muestra
        # **su propio** RUT, y eso es correcto) y POST con error (se vuelve a dibujar)
        ok = client.post(url, {"use_number": "1", "value_number": "ZX-4417"})
        assert ok.status_code == 302
        seen.append(ok.content.decode())
        seen.append(client.post(url, {}).content.decode())

    # Sin "345" suelto: un token CSRF o un UUID podrían contenerlo por azar.
    forms = (SENTINEL_RUT, OWN_RUT, "345.678")
    for body in seen:
        for sentinel in forms:
            assert sentinel not in body
    audit = json.dumps(
        list(
            AuditEvent.objects.values(
                "action", "path", "metadata", "model_label", "object_id"
            )
        ),
        default=str,
    )
    assert "12.345" not in audit and OWN_RUT not in audit
    assert OWN_RUT not in caplog.text and "12.345" not in caplog.text
    # y el RUT de la ficha tampoco cambió desde el PDF
    scene.refresh_from_db()
    assert scene.rut == OWN_RUT


def test_a_rut_that_does_not_match_the_record_says_so_without_the_value(scene):
    client = login_as(*BOTH)
    lines = [line.replace(SENTINEL_RUT, "11.111.111-1") for line in CREDENTIAL_LINES]
    url = _confirm_url(_upload(client, scene, lines))

    page = client.get(url).content.decode()

    assert 'data-rut-state="mismatch"' in page
    assert "9.876" not in page and "9876543" not in page


def test_the_audit_names_fields_not_values(scene):
    client = login_as(*BOTH)
    url = _confirm_url(_upload(client, scene))

    client.post(url, {"use_number": "1", "value_number": "ZX-4417"})

    event = AuditEvent.objects.get(action="operator_credential_confirmed")
    # El middleware suma `query_keys` (nombres, no valores); lo nuestro es esto.
    assert {"document", "fields_from_pdf", "fields_typed"} <= set(event.metadata)
    assert "ZX-4417" not in json.dumps(event.metadata)
    assert event.model_label == "registry.Operator"


# --- permisos y tenant -----------------------------------------------------


@pytest.mark.parametrize("granted", [("add_document",), ("change_operator",), ()])
def test_both_permissions_are_required_to_upload(scene, granted):
    client = login_as(*granted)
    response = _upload(client, scene)
    assert response.status_code == 403
    assert not Document.objects.exists()


@pytest.mark.parametrize("granted", [("add_document",), ("change_operator",)])
def test_both_permissions_are_required_to_confirm(scene, granted):
    full = login_as(*BOTH)
    url = _confirm_url(_upload(full, scene))
    client = login_as(*granted)
    assert client.get(url).status_code == 403
    assert (
        client.post(url, {"use_number": "1", "value_number": "ZX-4417"}).status_code
        == 403
    )
    assert _snapshot(scene) == ("OLD-1", date(2026, 12, 1))


def test_an_operator_of_another_tenant_is_a_404(scene):
    other = OperationalTenant.objects.create(name="Otra empresa", slug="otra")
    foreign = Operator.objects.create(
        tenant=other, employee_id="OP-9", full_name="Ana Rivas"
    )
    client = login_as(*BOTH)

    assert _upload(client, foreign).status_code == 404
    assert not Document.objects.exists()


def test_a_document_of_another_tenant_cannot_be_confirmed(scene):
    other = OperationalTenant.objects.create(name="Otra empresa", slug="otra")
    foreign = Operator.objects.create(
        tenant=other, employee_id="OP-9", full_name="Ana Rivas"
    )
    # Un permiso de más: `login_as` deriva el usuario de los permisos y chocaría.
    foreign_client = login_as(*BOTH, "view_aircraft", member_of=other)
    url = _confirm_url(_upload(foreign_client, foreign))
    mine = login_as(*BOTH)

    assert mine.get(url).status_code == 404
    assert mine.post(url, {"use_number": "1", "value_number": "X-1"}).status_code == 404
    # y tampoco con **mi** operador: el documento tiene que ser de ese operador
    document = Document.objects.get()
    crossed = reverse("operator-credential-confirm", args=[scene.pk, document.pk])
    assert mine.get(crossed).status_code == 404


def test_the_detail_page_offers_the_upload_only_with_both_permissions(scene):
    full = login_as(*BOTH)
    page = full.get(reverse("operator-detail", args=[scene.pk])).content.decode()
    assert reverse("operator-credential-upload", args=[scene.pk]) in page

    half = login_as("view_operator", "change_operator", "view_document")
    page = half.get(reverse("operator-detail", args=[scene.pk])).content.decode()
    assert reverse("operator-credential-upload", args=[scene.pk]) not in page


def test_a_bad_file_is_refused_before_anything_is_saved(scene):
    client = login_as(*BOTH)
    response = client.post(
        reverse("operator-credential-upload", args=[scene.pk]),
        {
            "file": SimpleUploadedFile(
                "cred.pdf", b"MZ not a pdf", content_type="application/pdf"
            )
        },
    )
    assert response.status_code == 302
    assert not Document.objects.exists()


def test_the_same_file_twice_reuses_the_stored_copy_and_warns(scene):
    client = login_as(*BOTH)
    # reportlab sella fecha e id: los mismos bytes se generan una sola vez.
    data = _pdf(CREDENTIAL_LINES)
    _upload(client, scene, content=data)
    second = client.post(
        reverse("operator-credential-upload", args=[scene.pk]),
        {"file": SimpleUploadedFile("again.pdf", data, content_type="application/pdf")},
        follow=True,
    )
    first, other = Document.objects.order_by("created_at")
    assert first.file_path == other.file_path
    assert any("byte" in str(m) for m in second.context["messages"])
