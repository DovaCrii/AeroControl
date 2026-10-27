"""LV-355 F1: el informe de tareas exporta lo mismo antes y después de la tubería.

Los `golden/*.json` se generaron **con los escritores anteriores a
`apps/reporting/export.py`** (CSV con BOM a mano, XLSX y DOCX propios); que sigan
pasando prueba que unificar los escritores no movió una celda. Datos ficticios;
reloj fijado en 2026-10-26.
"""

from datetime import date, datetime, timezone as dt_timezone
from pathlib import Path

import pytest
from django.urls import reverse

from apps.core.testing import assert_golden, docx_grid, pin_now, workbook_grid

from .models import KanbanLabel, KanbanTask
from .tests import auth_client, board, operator, user  # noqa: F401

GOLDEN = Path(__file__).resolve().parents[1] / "reporting" / "snapshots" / "exports"
NOW = datetime(2026, 10, 26, 15, 0, tzinfo=dt_timezone.utc)


@pytest.fixture
def tasks(board, operator, monkeypatch):  # noqa: F811
    pin_now(monkeypatch, NOW)
    board_obj, todo, done = board
    label = KanbanLabel.objects.create(board=board_obj, name="urgente")
    first = KanbanTask.objects.create(
        board=board_obj,
        stage=todo,
        title="=SENTINEL(1+1)",
        priority="high",
        assigned_to=operator,
        due_date=date(2026, 11, 3),
    )
    first.labels.add(label)
    KanbanTask.objects.create(board=board_obj, stage=done, title="Segunda tarea")


@pytest.mark.django_db
def test_csv(auth_client, tasks):  # noqa: F811
    raw = auth_client.get(reverse("task-report-csv")).content

    assert_golden(
        GOLDEN / "tasks_csv.json",
        {
            "bom": raw.startswith(b"\xef\xbb\xbf"),
            "lines": raw.decode("utf-8-sig").split("\r\n"),
        },
    )


@pytest.mark.django_db
def test_xlsx(auth_client, tasks):  # noqa: F811
    grid = workbook_grid(auth_client.get(reverse("task-report-xlsx")).content)

    assert_golden(GOLDEN / "tasks_xlsx.json", grid)


@pytest.mark.django_db
def test_docx(auth_client, tasks):  # noqa: F811
    grid = docx_grid(auth_client.get(reverse("task-report-docx")).content)

    assert_golden(GOLDEN / "tasks_docx.json", grid)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "route,extension",
    [
        ("task-report-csv", "csv"),
        ("task-report-xlsx", "xlsx"),
        ("task-report-docx", "docx"),
    ],
)
def test_every_file_is_named_with_its_date(
    auth_client,  # noqa: F811
    tasks,
    route,
    extension,
):
    """S12: `stem_AAAA-MM-DD`."""
    disposition = auth_client.get(reverse(route))["Content-Disposition"]

    assert disposition == (
        f'attachment; filename="aerocontrol-tasks_2026-10-26.{extension}"'
    )
