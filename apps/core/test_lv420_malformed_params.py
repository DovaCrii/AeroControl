"""LV-420: un parámetro mal escrito en la URL no es un 500, y el CSV del cierre
mensual neutraliza fórmulas.

Auditoría #12: `?doc_type=abc` sobre una columna UUID (o `?entity_type=abc`
sobre el id entero de ContentType) lanzaba al construir el filtro. Un valor que
no puede existir no encuentra nada, igual que un id bien formado que no está.

Auditoría #10: el CSV del cierre mensual escribía el código de la faena y el
usuario tal cual, sin `neutralize` — el único export que se saltaba la regla.
"""

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from apps.core.exports import neutralize
from apps.core.views import filter_or_none
from apps.registry.models import CostCenter

GARBAGE = "abc'--"


@pytest.fixture
def admin(db):
    User.objects.create_superuser("admin", "admin@x.cl", "pw")
    client = Client()
    assert client.login(username="admin", password="pw")
    return client


@pytest.mark.parametrize(
    ("url_name", "params"),
    [
        ("document-list", {"doc_type": GARBAGE}),
        ("operational-records", {"doc_type": GARBAGE}),
        ("operational-records", {"cost_center": GARBAGE}),
        ("document-create", {"entity_type": GARBAGE}),
        ("can-i-fly", {"aircraft": GARBAGE, "operator": GARBAGE}),
        ("workboard-list", {"board": GARBAGE, "operator": GARBAGE}),
    ],
)
def test_malformed_filter_is_not_a_500(admin, url_name, params):
    response = admin.get(reverse(url_name), params)

    assert response.status_code == 200


def test_filter_or_none_matches_nothing_on_a_malformed_value(db):
    CostCenter.objects.create(code="CC1", name="One")

    assert list(filter_or_none(CostCenter.objects.all(), pk=GARBAGE)) == []
    assert filter_or_none(CostCenter.objects.all(), code="CC1").count() == 1


def test_monthly_close_csv_neutralizes_formulas(admin):
    centre = CostCenter.objects.create(
        code="=HYPERLINK(1)", name="Evil", operates_flights=True
    )

    body = admin.get(
        reverse("monthly-review"), {"export": "csv", "month": "2026-08"}
    ).content.decode()

    assert neutralize(centre.code) in body
    assert ",=HYPERLINK" not in body
