"""LV-428: los cortes de urgencia (7/15/30 dias) viven en un solo lugar.

La tabla de bordes es la verdad observable: cada consumidor tiene que devolver
exactamente lo mismo para ella, antes y despues de unificar la definicion.
"""

import re
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from apps.compliance.digest import BUCKETS, bucket_for
from apps.compliance.urgency import (
    HORIZON_DAYS,
    URGENCY_BUCKETS,
    URGENCY_CUTOFFS_DAYS,
    urgency_bucket,
)
from apps.compliance.models import Alert, Document, DocumentType
from apps.compliance.reports import build_compliance_report
from apps.registry.models import Aircraft, CostCenter
from apps.workboard.models import KanbanTask

TODAY = timezone.localdate()

# dias que faltan -> tramo. Vencido es estrictamente antes de hoy; cada corte
# es inclusivo (<=), de modo que el dia 7 todavia es due_7.
EDGE_TABLE = {
    -1: "overdue",
    0: "due_7",
    6: "due_7",
    7: "due_7",
    8: "due_15",
    14: "due_15",
    15: "due_15",
    16: "due_30",
    29: "due_30",
    30: "due_30",
    31: None,
}


@pytest.mark.parametrize("days_left, expected", EDGE_TABLE.items())
def test_single_urgency_bucket_edges(days_left, expected):
    assert urgency_bucket(days_left) == expected


def test_cutoffs_and_buckets_agree():
    assert URGENCY_CUTOFFS_DAYS == tuple(days for _key, days in URGENCY_BUCKETS)
    assert HORIZON_DAYS == URGENCY_CUTOFFS_DAYS[-1]
    assert [key for key, _bound in BUCKETS] == [
        "overdue",
        *(key for key, _days in URGENCY_BUCKETS),
    ]


# Guardian: los cortes no se vuelven a escribir en estos modulos. Se buscan los
# literales por forma (tupla de cortes, `days=N`, `<= N` sobre dias) y se exige
# que sólo `urgency.py` los contenga.
GUARDED_MODULES = (
    "apps/compliance/digest.py",
    "apps/compliance/reports.py",
    "apps/compliance/models.py",
    "apps/workboard/models.py",
)
CUTOFF_LITERALS = (
    re.compile(r"\(\s*7\s*,\s*15\s*,\s*30\s*\)"),
    re.compile(r"\[\s*7\s*,\s*15\s*,\s*30\s*\]"),
    # Solo hacia adelante: `end - timedelta(days=30)` es la ventana por defecto
    # de un periodo de informe, otro concepto que no es un corte de urgencia.
    re.compile(r"\+\s*timedelta\(days=(7|15|30)\)"),
    re.compile(r"(days_left|\.days)\s*(<=|<)\s*(7|15|30)\b"),
    re.compile(r"\(\s*\"due_(7|15|30)\"\s*,\s*(7|15|30)\s*\)"),
)


@pytest.mark.parametrize("module", GUARDED_MODULES)
def test_no_module_redefines_the_urgency_cutoffs(module):
    source = (Path(__file__).resolve().parents[2] / module).read_text(encoding="utf-8")
    for pattern in CUTOFF_LITERALS:
        assert not pattern.search(source), (module, pattern.pattern)


def test_the_single_definition_still_holds_the_cutoffs():
    source = (Path(__file__).with_name("urgency.py")).read_text(encoding="utf-8")
    assert any(p.search(source) for p in CUTOFF_LITERALS)


@pytest.mark.parametrize("days_left, expected", EDGE_TABLE.items())
def test_digest_bucket_for_edges(days_left, expected):
    assert bucket_for(TODAY + timedelta(days=days_left), TODAY) == expected


@pytest.mark.parametrize("days_left, expected", EDGE_TABLE.items())
def test_task_urgency_bucket_edges(days_left, expected):
    task = KanbanTask(due_date=TODAY + timedelta(days=days_left))
    assert task.urgency_bucket(TODAY) == (expected or "")


def test_task_without_due_date_has_no_bucket():
    assert KanbanTask(due_date=None).urgency_bucket(TODAY) == ""


@pytest.mark.django_db
@pytest.mark.parametrize("days_left, expected", EDGE_TABLE.items())
def test_compliance_report_counts_in_the_same_bucket(days_left, expected):
    cost_center = CostCenter.objects.create(code="FAENA-01", name="Faena Norte")
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Multirotor",
        model="M300",
        manufacturer="DJI",
        cost_center=cost_center,
    )
    doc_type = DocumentType.objects.create(code="SEG", name="Seguro")
    Document.objects.create(
        title="edge",
        doc_type=doc_type,
        content_type=ContentType.objects.get_for_model(Aircraft),
        object_id=aircraft.pk,
        file_path="seg/edge.pdf",
        issue_date=date(2026, 1, 1),
        expiry_date=TODAY + timedelta(days=days_left),
    )

    totals = build_compliance_report()["totals"]

    counted = {key: totals[key] for key in ("expired", "due_7", "due_15", "due_30")}
    key = "expired" if expected == "overdue" else expected
    assert counted == {k: int(k == key) for k in counted}


@pytest.mark.parametrize(
    "days_left, expected",
    [(-1, "critical"), (0, "high"), (7, "high"), (8, "medium"), (30, "medium")],
)
def test_follow_up_priority_edges(days_left, expected):
    alert = SimpleNamespace(_watched_value=lambda: TODAY + timedelta(days=days_left))
    assert Alert._follow_up_priority(alert) == expected
