"""LV-415: las fechas se toman en la hora de Chile, no en UTC.

`TIME_ZONE="America/Santiago"` con `USE_TZ=True`: entre las ~21:00 y las 23:59 locales
el reloj UTC ya está en el día siguiente (y el 31-12 a las 21:00 ya es otro año).
`.date()` sobre un datetime aware devuelve la fecha **UTC**, y `timezone.now().year`
el año UTC. Hallazgos #4 y #16 de la auditoría.

Los tests fijan la hora con `apps.core.testing.pin_now`. El guardián al final recorre
`apps/**` con `ast` y falla ante los tres patrones que lo causan.
"""

import ast
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.core.testing import login_as, pin_now

CHILE = timezone.get_default_timezone()


def _aware(year, month, day, hour, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=CHILE)


def _utc(year, month, day, hour, minute=0):
    # Como lo entrega 	imezone.now() en producción: el instante en UTC.
    return _aware(year, month, day, hour, minute).astimezone(UTC)


@pytest.mark.django_db
class TestMovementAtNightCountsOnItsLocalDay:
    def test_a_move_at_23h_local_on_the_cutoff_day_counts(self):
        from apps.operations.models import FlightPermission, PermissionHistory
        from apps.registry.models import CostCenter
        from apps.reporting.builder import status_at_cutoff

        centre = CostCenter.objects.create(
            code="CC738", name="MLP", operates_flights=True
        )
        permit = FlightPermission.objects.create(
            cost_center=centre,
            purpose="photogrammetry",
            status=FlightPermission.STATUS_APPROVED,
            permission_number="9001",
            location="Site",
            area_type="unpopulated",
            valid_from=date(2026, 8, 1),
            valid_until=date(2026, 11, 1),
        )
        entry = PermissionHistory.objects.create(
            permission=permit,
            previous_status=FlightPermission.STATUS_REQUESTED,
            new_status=FlightPermission.STATUS_APPROVED,
            changed_by="alguien",
        )
        # 31-08 23:00 en Santiago = 01-09 02:00 UTC.
        moment = _aware(2026, 8, 31, 23)
        PermissionHistory.objects.filter(pk=entry.pk).update(created_at=moment)
        assert moment.astimezone(UTC).date() == date(2026, 9, 1)

        result = status_at_cutoff([permit], date(2026, 8, 31))

        assert result[permit.pk] == FlightPermission.STATUS_APPROVED


@pytest.mark.django_db
class TestTheYearOfTheFolioIsTheLocalYear:
    NEW_YEARS_EVE = _aware(2026, 12, 31, 23, 30)  # 2027-01-01 02:30 UTC

    def test_permit_folio(self, monkeypatch):
        from apps.operations.models import FlightPermission
        from apps.registry.models import CostCenter

        pin_now(monkeypatch, self.NEW_YEARS_EVE.astimezone(UTC))
        centre = CostCenter.objects.create(code="OPS", name="Operations")

        permit = FlightPermission.objects.create(
            cost_center=centre,
            purpose="Training",
            valid_from=date(2026, 12, 31),
            valid_until=date(2026, 12, 31),
            location="Santiago",
        )

        assert permit.internal_folio == "JEJ-2026-001"

    def test_plan_folio(self, monkeypatch):
        from django.contrib.auth.models import User

        from apps.geo.models import GeoPlan
        from apps.registry.models import CostCenter

        pin_now(monkeypatch, self.NEW_YEARS_EVE.astimezone(UTC))
        centre = CostCenter.objects.create(code="CC738", name="MLP")
        owner = User.objects.create_user("o415", "o415@test.com", "pw")  # nosec B106

        plan = GeoPlan.objects.create(
            title="Plan", cost_center=centre, created_by=owner
        )

        assert plan.folio == "PG-2026-001"


@pytest.mark.django_db
def test_the_calendar_opens_on_the_local_month(monkeypatch):
    pin_now(monkeypatch, _utc(2026, 12, 31, 23, 30))
    client = login_as("view_flightpermission")

    response = client.get(reverse("ops-calendar"))

    assert response.context["month_value"] == "2026-12"


# --------------------------------------------------------------------------
# Guardián
# --------------------------------------------------------------------------

APPS = Path(__file__).resolve().parent.parent

# (ruta relativa a apps/, patrón) -> motivo. Lista corta y justificada.
ALLOWED: dict[tuple[str, str], str] = {}


def _violations(tree):
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Call)):
            continue
        call = node.value
        func = call.func
        # timezone.now().date() / timezone.now().year
        if (
            node.attr in {"date", "year"}
            and isinstance(func, ast.Attribute)
            and func.attr == "now"
            and isinstance(func.value, ast.Name)
            and func.value.id == "timezone"
        ):
            yield node.lineno, f"timezone.now().{node.attr}"
    for node in ast.walk(tree):
        # <algo>_at.date()
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "date"
            and isinstance(node.func.value, ast.Attribute)
            and node.func.value.attr.endswith("_at")
        ):
            yield node.lineno, f"{node.func.value.attr}.date()"


def _production_files():
    for path in APPS.rglob("*.py"):
        rel = path.relative_to(APPS)
        name = path.name
        if "migrations" in rel.parts or "tests" in rel.parts:
            continue
        if name.startswith("test_") or name in {"tests.py", "conftest.py"}:
            continue
        yield path, rel.as_posix()


def test_no_utc_dates_in_production_code():
    found = []
    for path, rel in _production_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for lineno, pattern in _violations(tree):
            if (rel, pattern) not in ALLOWED:
                found.append(f"{rel}:{lineno} {pattern}")

    assert not found, (
        "Fecha en UTC en vez de la local (LV-415); usar timezone.localdate() o "
        "timezone.localtime(x).date():\n" + "\n".join(found)
    )


def test_the_guardian_catches_the_patterns():
    tree = ast.parse(
        "a = timezone.now().date()\nb = timezone.now().year\nc = x.created_at.date()\n"
        "d = timezone.localdate()\ne = timezone.localtime(x.created_at).date()\n"
    )

    assert sorted(p for _line, p in _violations(tree)) == [
        "created_at.date()",
        "timezone.now().date",
        "timezone.now().year",
    ]
