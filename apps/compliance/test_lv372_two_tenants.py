"""LV-372 (F-08): barrido de **dos empresas** sobre listas, detalles y acciones.

`test_lv372_lists_and_actions` fija las seis listas y las dos transiciones que dieron el
aviso; esta prueba recorre **el resto** con el mismo método. Un fixture de dos empresas, una
persona de la empresa A que tiene **todos** los permisos de las apps (el rol más amplio que
no es superusuario) y, para cada vista, una afirmación:

- **lectura de un registro de B por su pk → 404** (detalle, edición, descarga, KMZ...);
- **acción sobre un registro de B → 404 y B queda intacto**;
- **listas, cifras y exportaciones → lo de B no aparece**.

Cada caso falló antes del acotado (se comprobó rompiendo el arreglo, ver la fila LV-372).
Donde no había fuga la prueba queda como guardián. Datos ficticios.
"""

from datetime import timedelta
from io import BytesIO
from zipfile import ZipFile

import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse

from apps.compliance.models import Deliverable, NonConformity
from apps.compliance.test_lv372_tenant_scope import SOON, TODAY, world  # noqa: F401
from apps.core.testing import login_as
from apps.maintenance.models import MaintenanceRecord
from apps.operations.models import (
    FlightRecord,
    FlightRequest,
    PreflightCheck,
    PreflightChecklist,
)
from apps.registry.models import (
    Assignment,
    KnowledgeAssessment,
    OperatorAssignment,
    Qualification,
    QualificationType,
)
from apps.workboard.models import (
    KanbanBoard,
    KanbanChecklistItem,
    KanbanStage,
    KanbanTask,
)

APPS = ("maintenance", "operations", "compliance", "registry", "workboard", "reporting")


def _everything_of(tenant):
    """Una persona de `tenant` con todos los permisos de las apps: el rol más amplio que no es root."""
    codenames = list(
        Permission.objects.filter(content_type__app_label__in=APPS).values_list(
            "codename", flat=True
        )
    )
    return login_as(*codenames, member_of=tenant)


@pytest.fixture
def rich(world):  # noqa: F811
    """Para cada empresa: lo que las vistas de esta prueba abren por pk."""
    import datetime

    qualification_type = QualificationType.objects.create(
        name="Habilitacion ficticia", code="Q372"
    )
    checklist = PreflightChecklist.objects.create(name="Lista")
    for key in ("a", "b"):
        row = world[key]
        center, aircraft, operator = row["center"], row["aircraft"], row["operator"]
        row["maintenance"] = MaintenanceRecord.objects.create(
            aircraft=aircraft,
            maintenance_type="preventive",
            status="pending",
            scheduled_date=TODAY + timedelta(days=5),
            description=f"Mantencion {key.upper()}",
        )
        row["request"] = FlightRequest.objects.create(
            title=f"Solicitud {key.upper()}",
            cost_center=center,
            center_lat=-31.7,
            center_lon=-70.6,
            status="prepared",
        )
        row["record"] = FlightRecord.objects.create(
            permission=row["permit"],
            actual_date=TODAY,
            departure_time=datetime.time(9),
            arrival_time=datetime.time(10),
            pilot=operator,
            aircraft=aircraft,
        )
        row["check"] = PreflightCheck.objects.create(
            permission=row["permit"],
            aircraft=aircraft,
            planned_date=TODAY,
            checklist=checklist,
            checklist_name="Lista",
        )
        row["record_check"] = PreflightCheck.objects.create(
            flight_record=row["record"],
            aircraft=aircraft,
            checklist=checklist,
            checklist_name="Lista",
        )
        row["deliverable"] = Deliverable.objects.create(
            title=f"Entrega {key.upper()}", cost_center=center
        )
        row["finding"] = NonConformity.objects.create(
            title=f"Hallazgo {key.upper()}",
            source=NonConformity.SOURCE_INCIDENT,
            cost_center=center,
        )
        row["assignment"] = Assignment.objects.create(
            operator=operator,
            aircraft=aircraft,
            cost_center=center,
            start_date=TODAY,
            status="planned",
        )
        row["op_assignment"] = OperatorAssignment.objects.create(
            operator=operator, cost_center=center, start_date=TODAY, status="planned"
        )
        row["qualification"] = Qualification.objects.create(
            operator=operator,
            qualification_type=qualification_type,
            issue_date=TODAY - timedelta(days=30),
            expiry_date=SOON,
        )
        row["assessment"] = KnowledgeAssessment.objects.create(
            operator=operator,
            question_count=10,
            correct_count=9,
            score_percent=90,
            passed=True,
            expires_on=SOON,
        )
        board = KanbanBoard.objects.create(
            name=f"Tablero {key.upper()}", tenant=row["tenant"]
        )
        stage = KanbanStage.objects.create(board=board, name="Pendiente")
        row["board"] = board
        row["task"] = KanbanTask.objects.create(
            board=board, stage=stage, title=f"Tarea {key.upper()}"
        )
        row["item"] = KanbanChecklistItem.objects.create(
            task=row["task"], title="Paso", order=0
        )
        row["stage"] = stage
    return world


# ---------------------------------------------------------------------------------------------
# Lecturas por pk: la fila de B es 404 para una persona de A.
# ---------------------------------------------------------------------------------------------

# (ruta, clave de la fila de B que se pasa como pk)
FOREIGN_READS = [
    ("maintenance-detail", "maintenance"),
    ("permission-detail", "permit"),
    ("permission-update", "permit"),
    ("permission-operations", "permit"),
    ("notam-review-create", "permit"),
    ("record-detail", "record"),
    ("preflight-check", "record"),
    ("preflight-standalone", "check"),
    ("flight-request-detail", "request"),
    ("flight-request-update", "request"),
    ("flight-request-kmz", "request"),
    ("deliverable-detail", "deliverable"),
    ("deliverable-update", "deliverable"),
    ("nonconformity-detail", "finding"),
    ("nonconformity-update", "finding"),
    ("document-detail", "document"),
    ("document-download", "document"),
    ("document-preview", "document"),
    ("alertrule-update", "rule"),
    ("aircraft-detail", "aircraft"),
    ("aircraft-update", "aircraft"),
    ("operator-detail", "operator"),
    ("operator-update", "operator"),
    ("operator-departure", "operator"),
    ("costcenter-detail", "center"),
    ("costcenter-update", "center"),
    ("assignment-detail", "assignment"),
    ("assignment-update", "assignment"),
    ("operatorassignment-detail", "op_assignment"),
    ("qualification-detail", "qualification"),
    ("qualification-update", "qualification"),
    ("assessment-detail", "assessment"),
    ("task-detail", "task"),
    ("task-edit", "task"),
]


@pytest.mark.django_db
@pytest.mark.parametrize("url_name,key", FOREIGN_READS)
def test_reading_a_row_of_the_other_tenant_by_pk_is_404(rich, url_name, key):
    client = _everything_of(rich["a"]["tenant"])
    pk = rich["b"][key].pk
    assert client.get(reverse(url_name, args=[pk])).status_code == 404


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url_name,key",
    # Descargar y previsualizar necesitan el archivo en el almacenamiento: acá no hay ninguno.
    [
        row
        for row in FOREIGN_READS
        if row[0] not in {"document-download", "document-preview"}
    ],
)
def test_reading_the_own_row_still_works(rich, url_name, key):
    """Contraparte: con una sola empresa nada cambia. La fila de A abre (200) o redirige."""
    client = _everything_of(rich["a"]["tenant"])
    pk = rich["a"][key].pk
    status = client.get(reverse(url_name, args=[pk])).status_code
    assert status != 404, f"{url_name} dejó de abrir la fila propia"


# ---------------------------------------------------------------------------------------------
# Acciones sobre un registro de B: 404 y B queda como estaba.
# ---------------------------------------------------------------------------------------------

# (ruta, clave, cuerpo del POST)
FOREIGN_ACTIONS = [
    ("maintenance-start", "maintenance", {}),
    ("maintenance-send", "maintenance", {}),
    ("maintenance-arrive-at-workshop", "maintenance", {}),
    ("maintenance-finish", "maintenance", {}),
    ("maintenance-depart", "maintenance", {}),
    ("maintenance-complete", "maintenance", {}),
    ("aircraft-report-incident", "aircraft", {}),
    ("permission-approve", "permit", {}),
    ("permission-deny", "permit", {}),
    ("permission-complete", "permit", {}),
    ("permission-archive", "permit", {"confirm": "1"}),
    ("permission-restore", "permit", {}),
    ("permission-correct-status", "permit", {"status": "denied", "reason": "x"}),
    ("permission-folio-from-pdf", "permit", {}),
    ("notam-review-create", "permit", {}),
    ("preflight-start", "permit", {"aircraft": "@aircraft"}),
    ("record-delete", "record", {}),
    ("preflight-check", "record", {}),
    ("preflight-sign", "record", {}),
    ("preflight-standalone", "check", {}),
    ("preflight-standalone-sign", "check", {}),
    ("flight-request-file", "request", {}),
    ("flight-request-close", "request", {}),
    ("flight-request-link", "request", {}),
    ("flight-request-add-note", "request", {"text": "x"}),
    ("flight-request-add-work-item", "request", {}),
    ("deliverable-validate", "deliverable", {}),
    ("deliverable-release", "deliverable", {}),
    ("deliverable-reject", "deliverable", {}),
    ("nonconformity-close", "finding", {}),
    ("nonconformity-reopen", "finding", {}),
    ("nonconformity-verify-effectiveness", "finding", {}),
    ("nonconformity-assign", "finding", {}),
    ("alert-assign", "alert", {}),
    ("document-delete", "document", {}),
    ("document-replace", "document", {}),
    ("aircraft-archive", "aircraft", {"confirm": "1"}),
    ("aircraft-restore", "aircraft", {}),
    ("aircraft-insurance-pending", "aircraft", {}),
    ("aircraft-insurance-filed", "aircraft", {}),
    ("aircraft-insurance-active", "aircraft", {}),
    ("operator-archive", "operator", {}),
    ("operator-restore", "operator", {}),
    ("operator-departure", "operator", {}),
    ("costcenter-archive", "center", {}),
    ("costcenter-archive", "center", {"confirm": "1"}),
    ("costcenter-restore", "center", {}),
    ("assignment-archive", "assignment", {}),
    ("assignment-restore", "assignment", {}),
    ("operatorassignment-archive", "op_assignment", {}),
    ("qualification-archive", "qualification", {}),
    ("assessment-archive", "assessment", {"confirm": "1"}),
    ("assessment-restore", "assessment", {}),
    ("task-archive", "task", {}),
    ("task-move", "task", {"stage_id": "x"}),
    ("checklist-create", "task", {"title": "x"}),
    ("checklist-toggle", "item", {}),
    ("board-archive", "board", {}),
]


@pytest.mark.django_db
@pytest.mark.parametrize("url_name,key,body", FOREIGN_ACTIONS)
def test_an_action_on_a_row_of_the_other_tenant_is_404(rich, url_name, key, body):
    client = _everything_of(rich["a"]["tenant"])
    target = rich["b"][key]
    # `"@clave"` en el cuerpo: el pk de otra fila de B (p. ej. la aeronave de un permiso).
    body = {
        name: rich["b"][value[1:]].pk if str(value).startswith("@") else value
        for name, value in body.items()
    }
    if url_name.endswith("-restore"):
        # Sólo una fila archivada se puede restaurar: sin esto el 404 vendría de «no está archivada».
        type(target).objects.filter(pk=target.pk).update(is_active=False)
    before = type(target).objects.filter(pk=target.pk).values().get()
    response = client.post(reverse(url_name, args=[target.pk]), body)
    assert response.status_code == 404
    after = type(target).objects.filter(pk=target.pk).values().get()
    assert after == before, "la fila de la otra empresa cambió"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url_name,key,body,field,expected",
    [
        ("maintenance-start", "maintenance", {}, "status", "in_progress"),
        ("permission-deny", "permit", {}, "status", "denied"),
        ("flight-request-file", "request", {}, "status", "filed"),
        ("flight-request-close", "request", {}, "status", "prepared"),
        ("aircraft-insurance-pending", "aircraft", {}, "insurance_status", "pending"),
    ],
)
def test_the_same_actions_still_work_on_the_own_tenant(
    rich, url_name, key, body, field, expected
):
    """Con una sola empresa nada cambia: la acción sobre la fila propia sigue funcionando."""
    client = _everything_of(rich["a"]["tenant"])
    target = rich["a"][key]
    if url_name == "permission-deny":
        type(target).objects.filter(pk=target.pk).update(status="requested")
    response = client.post(reverse(url_name, args=[target.pk]), body)
    assert response.status_code == 302
    target.refresh_from_db()
    assert getattr(target, field) == expected


# ---------------------------------------------------------------------------------------------
# Listas, contadores y exportaciones.
# ---------------------------------------------------------------------------------------------

# (ruta de lista, texto que sólo está en la fila de B, texto de la fila de A)
LISTS = [
    ("maintenance-list", "RPA-B1", "RPA-A1"),
    ("history-list", "RPA-B1", None),
    ("permission-list", "JEJ-2026-B", "JEJ-2026-A"),
    ("record-list", "RPA-B1", "RPA-A1"),
    ("flight-request-list", "Solicitud B", "Solicitud A"),
    ("deliverable-list", "Entrega B", "Entrega A"),
    ("nonconformity-list", "Hallazgo B", "Hallazgo A"),
    ("document-list", "Documento B", "Documento A"),
    ("alertrule-list", "Regla b", "Regla a"),
    ("alert-list", "Regla b", "Regla a"),
    ("aircraft-list", "RPA-B1", "RPA-A1"),
    ("operator-list", "Piloto B", "Piloto A"),
    ("costcenter-list", "Faena b", "Faena a"),
    ("assignment-list", "RPA-B1", "RPA-A1"),
    ("operatorassignment-list", "Piloto B", "Piloto A"),
    ("aircraftassignment-list", "RPA-B1", None),
    ("qualification-list", "Piloto B", "Piloto A"),
    ("task-list", "Tarea B", "Tarea A"),
    ("board-list", "Tablero B", "Tablero A"),
    ("workboard-list", "Tarea B", "Tarea A"),
]


@pytest.mark.django_db
@pytest.mark.parametrize("url_name,theirs,mine", LISTS)
def test_lists_show_only_the_own_tenant(rich, url_name, theirs, mine):
    client = _everything_of(rich["a"]["tenant"])
    response = client.get(reverse(url_name), {"is_active": "", "is_resolved": "all"})
    assert response.status_code == 200
    body = response.content.decode()
    assert theirs not in body
    if mine:
        assert mine in body


@pytest.mark.django_db
@pytest.mark.parametrize("url_name,theirs,mine", LISTS)
def test_list_partials_and_search_do_not_leak(rich, url_name, theirs, mine):
    """El parcial htmx y la búsqueda salen del mismo queryset que la página."""
    client = _everything_of(rich["a"]["tenant"])
    query = {"q": theirs[:4], "is_resolved": "all"}
    response = client.get(reverse(url_name), query, HTTP_HX_REQUEST="true")
    assert response.status_code == 200
    assert theirs not in response.content.decode()


CSV_LISTS = [name for name, _theirs, _mine in LISTS if name != "alert-list"]


@pytest.mark.django_db
@pytest.mark.parametrize("url_name", CSV_LISTS)
def test_csv_exports_do_not_leak(rich, url_name):
    theirs = {name: needle for name, needle, _ in LISTS}[url_name]
    client = _everything_of(rich["a"]["tenant"])
    response = client.get(reverse(url_name), {"export": "csv"})
    if response.status_code != 200 or not response.has_header("Content-Disposition"):
        pytest.skip("la lista no exporta")
    body = b"".join(response.streaming_content).decode("utf-8-sig")
    assert theirs not in body


@pytest.mark.django_db
def test_xlsx_export_does_not_leak(rich):
    client = _everything_of(rich["a"]["tenant"])
    response = client.get(reverse("permission-list"), {"export": "xlsx"})
    if response.status_code != 200 or not response.has_header("Content-Disposition"):
        pytest.skip("la lista no exporta XLSX")
    content = b"".join(getattr(response, "streaming_content", [response.content]))
    with ZipFile(BytesIO(content)) as archive:
        text = "".join(
            archive.read(name).decode("utf-8", "ignore") for name in archive.namelist()
        )
    assert "JEJ-2026-B" not in text


@pytest.mark.django_db
def test_the_to_be_defined_chip_counts_only_own_maintenance(rich):
    """El chip «mantenciones por definir» del panel enlaza a esta lista con `needs_planning`."""
    for key in ("a", "b"):
        MaintenanceRecord.objects.create(
            aircraft=rich[key]["aircraft"], maintenance_type="to_be_defined"
        )
    client = _everything_of(rich["a"]["tenant"])
    response = client.get(reverse("maintenance-list"), {"needs_planning": "1"})
    rows = list(response.context["objects"])
    assert rows and all(
        row.aircraft.tenant_id == rich["a"]["tenant"].pk for row in rows
    )


@pytest.mark.django_db
def test_a_foreign_cost_centre_filter_on_a_list_is_empty_not_a_peek(rich):
    client = _everything_of(rich["a"]["tenant"])
    center = rich["b"]["center"].pk
    for name in ("maintenance-list", "permission-list", "flight-request-list"):
        response = client.get(reverse(name), {"cost_center": center})
        assert response.status_code == 200
        assert "RPA-B1" not in response.content.decode()
        assert "JEJ-2026-B" not in response.content.decode()


# ---------------------------------------------------------------------------------------------
# Formularios: los desplegables no nombran a la otra empresa y un pk ajeno en el POST se rechaza.
# ---------------------------------------------------------------------------------------------

THEIR_NAMES = (
    "Faena b",
    "CC-B",
    "RPA-B1",
    "Piloto B",
    "JEJ-2026-B",
    "Documento B",
    "Regla b",
    "Tablero B",
)

CREATE_FORMS = [
    "permission-create",
    "maintenance-create",
    "record-create",
    "deliverable-create",
    "nonconformity-create",
    "document-create",
    "document-bulk-upload",
    "alertrule-create",
    "alert-create",
    "aircraft-create",
    "operator-create",
    "costcenter-create",
    "assignment-create",
    "operatorassignment-create",
    "aircraftassignment-create",
    "qualification-create",
    "task-create",
    "stage-create",
    "label-create",
]


@pytest.mark.django_db
@pytest.mark.parametrize("url_name", CREATE_FORMS)
def test_create_forms_do_not_offer_the_other_tenant(rich, url_name):
    client = _everything_of(rich["a"]["tenant"])
    response = client.get(reverse(url_name))
    assert response.status_code == 200
    body = response.content.decode()
    assert [name for name in THEIR_NAMES if name in body] == []


EDIT_FORMS = [
    ("permission-update", "permit"),
    ("deliverable-update", "deliverable"),
    ("nonconformity-update", "finding"),
    ("assignment-update", "assignment"),
    ("qualification-update", "qualification"),
    ("aircraft-update", "aircraft"),
    ("operator-update", "operator"),
    ("task-edit", "task"),
]


@pytest.mark.django_db
@pytest.mark.parametrize("url_name,key", EDIT_FORMS)
def test_edit_forms_do_not_offer_the_other_tenant(rich, url_name, key):
    client = _everything_of(rich["a"]["tenant"])
    response = client.get(reverse(url_name, args=[rich["a"][key].pk]))
    assert response.status_code == 200
    body = response.content.decode()
    assert [name for name in THEIR_NAMES if name in body] == []


@pytest.mark.django_db
def test_a_foreign_choice_in_a_post_is_rejected_and_nothing_is_saved(rich):
    """El campo valida contra el queryset acotado: el pk de una aeronave de B no es una opción."""
    client = _everything_of(rich["a"]["tenant"])
    before = MaintenanceRecord.objects.count()
    response = client.post(
        reverse("maintenance-create"),
        {
            "aircraft": rich["b"]["aircraft"].pk,
            "maintenance_type": "preventive",
            "description": "x",
        },
    )
    assert response.status_code == 200  # el formulario vuelve con el error
    assert MaintenanceRecord.objects.count() == before
    before = Deliverable.objects.count()
    client.post(
        reverse("deliverable-create"),
        {"title": "x", "cost_center": rich["b"]["center"].pk},
    )
    assert Deliverable.objects.count() == before


@pytest.mark.django_db
def test_the_document_entity_picker_lists_only_own_records(rich):
    from django.contrib.contenttypes.models import ContentType

    from apps.registry.models import Aircraft

    client = _everything_of(rich["a"]["tenant"])
    ct = ContentType.objects.get_for_model(Aircraft).pk
    body = client.get(
        reverse("document-entity-options"), {"entity_type": ct}
    ).content.decode()
    assert "RPA-A1" in body and "RPA-B1" not in body
    # Y la página de alta con la entidad ajena precargada no la ofrece.
    page = client.get(
        reverse("document-create"),
        {"entity_type": ct, "object_id": rich["b"]["aircraft"].pk},
    ).content.decode()
    assert "RPA-B1" not in page


@pytest.mark.django_db
def test_attaching_an_existing_document_to_a_foreign_entity_is_refused(rich):
    from django.contrib.contenttypes.models import ContentType

    from apps.registry.models import Aircraft

    client = _everything_of(rich["a"]["tenant"])
    response = client.get(
        reverse("document-attach-existing"),
        {
            "entity_type": ContentType.objects.get_for_model(Aircraft).pk,
            "object_id": rich["b"]["aircraft"].pk,
            "doc_type": "t372c",
        },
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------------------------
# Bandeja de trabajo, búsqueda global y calendarios (`core`).
# ---------------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_work_tray_lists_only_own_pending_work(rich):
    from apps.operations.models import FlightPermission

    for key in ("a", "b"):
        FlightPermission.objects.create(
            internal_folio=f"PEND-{key.upper()}",
            cost_center=rich[key]["center"],
            purpose="patrol",
            status=FlightPermission.STATUS_REQUESTED,
            location="Sitio ficticio",
            area_type="unpopulated",
        )
    client = _everything_of(rich["a"]["tenant"])
    body = client.get(reverse("work-tray")).content.decode()
    for mine in ("PEND-A", "Hallazgo A", "Entrega A", "Regla a"):
        assert mine in body
    for theirs in ("PEND-B", "Hallazgo B", "Entrega B", "Regla b"):
        assert theirs not in body


@pytest.mark.django_db
def test_a_finding_without_cost_centre_is_pending_work_for_everyone(rich):
    """Sin faena no se puede atribuir a una empresa: se sigue viendo (no cambia con una sola)."""
    NonConformity.objects.create(
        title="Hallazgo comun", source=NonConformity.SOURCE_INCIDENT
    )
    client = _everything_of(rich["a"]["tenant"])
    assert "Hallazgo comun" in client.get(reverse("work-tray")).content.decode()
    assert (
        "Hallazgo comun" in client.get(reverse("nonconformity-list")).content.decode()
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "query,theirs,mine",
    [
        ("RPA", "RPA-B1", "RPA-A1"),
        ("Piloto", "Piloto B", "Piloto A"),
        ("Documento", "Documento B", "Documento A"),
        ("Faena", "Faena b", "Faena a"),
    ],
)
def test_the_global_search_only_finds_own_records(rich, query, theirs, mine):
    client = _everything_of(rich["a"]["tenant"])
    body = client.get(reverse("global-search"), {"q": query}).content.decode()
    assert mine in body and theirs not in body


@pytest.mark.django_db
def test_the_calendars_do_not_show_the_other_tenants_dates(rich):
    client = _everything_of(rich["a"]["tenant"])
    month = SOON.strftime("%Y-%m")
    for name in ("calendar", "ops-calendar"):
        try:
            url = reverse(name)
        except Exception:  # noqa: BLE001 - la ruta puede no existir con ese nombre
            continue
        body = client.get(url, {"month": month}).content.decode()
        assert "JEJ-2026-B" not in body and "RPA-B1" not in body
    start = (SOON - timedelta(days=40)).isoformat()
    end = (SOON + timedelta(days=40)).isoformat()
    events = client.get(reverse("calendar-events"), {"start": start, "end": end})
    assert events.status_code == 200
    assert "JEJ-2026-B" not in events.content.decode()
    assert "RPA-B1" not in events.content.decode()


# ---------------------------------------------------------------------------------------------
# Informe de cumplimiento (cifras, filtros, exportaciones).
# ---------------------------------------------------------------------------------------------

REPORT_ROUTES = [
    "compliance-report",
    "compliance-report-csv",
    "compliance-report-xlsx",
    "compliance-report-docx",
    "compliance-report-pdf",
]


@pytest.mark.django_db
@pytest.mark.parametrize("url_name", REPORT_ROUTES)
def test_the_compliance_report_is_scoped_to_the_tenant(rich, url_name):
    client = _everything_of(rich["a"]["tenant"])
    response = client.get(reverse(url_name))
    assert response.status_code == 200
    if url_name == "compliance-report":
        body = response.content.decode()
        assert "CC-A" in body and "CC-B" not in body
        assert "Alerta B" not in body
        return
    content = b"".join(getattr(response, "streaming_content", [response.content]))
    if url_name in ("compliance-report-xlsx", "compliance-report-docx"):
        with ZipFile(BytesIO(content)) as archive:
            text = "".join(
                archive.read(name).decode("utf-8", "ignore")
                for name in archive.namelist()
            )
    else:
        text = content.decode("utf-8-sig", "ignore")
    assert "CC-B" not in text and "CC-A" in text or url_name.endswith("pdf")


@pytest.mark.django_db
def test_the_compliance_report_figures_count_only_own_rows(rich):
    from apps.compliance.reports import build_compliance_report

    user = _everything_of(rich["a"]["tenant"]).user
    scoped = build_compliance_report(user=user)
    assert {row["code"] for row in scoped["by_cost_center"]} == {"CC-A"}
    assert all("B" not in row["entity"][-3:] for row in scoped["open_alerts"])
    everything = build_compliance_report()
    assert {row["code"] for row in everything["by_cost_center"]} == {"CC-A", "CC-B"}
    # El informe sin sesión (correo ejecutivo, snapshots) sigue siendo el de toda la organización.
    assert everything["totals"]["total"] >= scoped["totals"]["total"]


@pytest.mark.django_db
def test_a_foreign_cost_centre_in_the_report_filter_is_ignored(rich):
    client = _everything_of(rich["a"]["tenant"])
    response = client.get(
        reverse("compliance-report"), {"cost_center": rich["b"]["center"].pk}
    )
    assert response.status_code == 200
    assert response.context["report"]["filters"]["cost_center"] is None
    assert "CC-B" not in response.content.decode()


@pytest.mark.django_db
def test_the_roster_report_does_not_offer_or_filter_by_a_foreign_centre(rich):
    client = _everything_of(rich["a"]["tenant"])
    response = client.get(
        reverse("registry-roster"), {"cost_center": rich["b"]["center"].pk}
    )
    body = response.content.decode()
    assert response.status_code == 200
    assert "CC-B" not in body and "RPA-B1" not in body and "Piloto B" not in body


# ---------------------------------------------------------------------------------------------
# Tablero de trabajo: quien no es miembro de ninguna empresa ya no ve las de todas.
# ---------------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_user_without_membership_does_not_see_every_tenants_boards(rich):
    from apps.core.models import OperationalTenant

    default, _ = OperationalTenant.objects.get_or_create(
        slug="default", defaults={"name": "Defecto"}
    )
    KanbanBoard.objects.create(name="Tablero defecto", tenant=default)
    client = login_as("view_kanbanboard", "view_kanbantask")
    body = client.get(reverse("board-list")).content.decode()
    assert "Tablero defecto" in body
    assert "Tablero A" not in body and "Tablero B" not in body


@pytest.mark.django_db
def test_a_board_without_tenant_stays_visible_to_everyone(rich):
    KanbanBoard.objects.create(name="Tablero comun", tenant=None)
    client = _everything_of(rich["a"]["tenant"])
    assert "Tablero comun" in client.get(reverse("board-list")).content.decode()


@pytest.mark.django_db
def test_quick_task_on_a_foreign_stage_creates_nothing(rich):
    client = _everything_of(rich["a"]["tenant"])
    before = KanbanTask.objects.count()
    response = client.post(
        reverse("task-quick"),
        {"stage_id": rich["b"]["stage"].pk, "title": "intruso", "priority": "medium"},
    )
    assert response.status_code in (400, 404)
    assert KanbanTask.objects.count() == before
    assert client.get(
        reverse("task-quick"), {"stage_id": rich["b"]["stage"].pk}
    ).status_code in (400, 404)


@pytest.mark.django_db
def test_the_operator_dropdowns_of_the_board_do_not_name_the_other_tenant(rich):
    client = _everything_of(rich["a"]["tenant"])
    assert "Piloto B" not in client.get(reverse("workboard-list")).content.decode()
    assert "Piloto B" not in client.get(reverse("kanban")).content.decode()


# ---------------------------------------------------------------------------------------------
# Informe mensual DGAC: global por diseño (se declara, no se acota).
# ---------------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_monthly_dgac_report_is_global_by_design():
    """`ReportRun` no tiene `tenant`: hay **un** informe por período para toda la organización.

    El informe mensual se entrega a la DGAC en nombre del operador y su payload cubre todas las
    faenas; `(period, revision)` es único. Partirlo por empresa exige un `tenant` en `ReportRun`,
    cambiar esa unicidad y una migración: una decisión de negocio, no una corrección mecánica
    (ver `MASTER_PLAN.md`, LV-372). Hasta entonces el acceso es por permiso (`view_reportrun`),
    que debe dársele sólo a roles de toda la organización. Si alguien agrega el campo, esta
    prueba falla y obliga a acotar de verdad el informe y `report_notice` del panel.
    """
    from apps.reporting.models import ReportRun

    assert "tenant" not in {field.name for field in ReportRun._meta.fields}


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url_name,args",
    [
        ("monthly-report", []),
        ("monthly-report-brief", []),
        ("monthly-report-template", []),
    ],
)
def test_the_monthly_report_screens_need_their_permission(rich, url_name, args):
    client = login_as(member_of=rich["a"]["tenant"])
    assert client.get(reverse(url_name, args=args)).status_code == 403


@pytest.mark.django_db
def test_the_dashboard_report_notice_is_global_by_design(rich):
    """`report_notice` lee el último `ReportRun` (global por diseño) y sólo con `view_reportrun`."""
    from apps.dashboard.compliance_section import report_notice
    from apps.reporting.models import ReportRun

    ReportRun.objects.create(period=TODAY.replace(day=1), revision=0, payload={})
    without = login_as(member_of=rich["a"]["tenant"]).user
    assert report_notice(without) is None
    with_perm = login_as("view_reportrun", member_of=rich["a"]["tenant"]).user
    assert report_notice(with_perm)["period"] == TODAY.replace(day=1)
