"""LV-403: escrituras concurrentes en SQLite.

Dos defectos con la misma raíz. Sin `transaction_mode=IMMEDIATE`, una transacción
que lee y luego escribe falla de inmediato con "database is locked" cuando otro
escritor se coló en medio, y `select_for_update()` no protege nada. Y ocho
`save()` calculaban `sequence = último + 1` sin transacción, así que dos
escritores leían el mismo valor y la secuencia se repetía.

No hay prueba de reproducción con dos hilos: contra una base SQLite en archivo
con `pytest-django` y xdist en Windows resultó inestable (bloqueos de archivo del
propio arnés), así que la garantía se vigila con la configuración y con un
guardián de código.
"""

import ast
from pathlib import Path

import pytest
from django.conf import settings
from django.db import connections

ROOT = Path(settings.BASE_DIR) / "apps"


def test_sqlite_opens_every_transaction_as_immediate():
    connection = connections["default"]
    if connection.vendor != "sqlite":
        pytest.skip("transaction_mode es una opción de SQLite")

    assert connection.settings_dict["OPTIONS"]["transaction_mode"] == "IMMEDIATE"


def _is_atomic(item):
    call = item.context_expr
    if not isinstance(call, ast.Call):
        return False
    func = call.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "atomic"
        and isinstance(func.value, ast.Name)
        and func.value.id == "transaction"
    )


def _sequence_reads_outside_atomic(path):
    """Lecturas `order_by("-sequence")` que no están bajo `with transaction.atomic()`."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []

    def visit(node, atomic):
        for child in ast.iter_child_nodes(node):
            inside = atomic
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                inside = False  # el contexto atómico no cruza a otra función
            if isinstance(child, ast.With) and any(_is_atomic(i) for i in child.items):
                inside = True
            if (
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Attribute)
                and child.func.attr == "order_by"
                and any(
                    isinstance(a, ast.Constant) and a.value == "-sequence"
                    for a in child.args
                )
                and not inside
            ):
                found.append(child.lineno)
            visit(child, inside)

    visit(tree, False)
    return found


def test_every_next_sequence_is_computed_inside_atomic():
    """`order_by("-sequence")` en código de la app sólo vale dentro de `transaction.atomic()`."""
    offenders = []
    for path in sorted(ROOT.rglob("*.py")):
        name = path.name
        if name.startswith("test") or "migrations" in path.parts:
            continue
        for line in _sequence_reads_outside_atomic(path):
            offenders.append(f"{path.relative_to(ROOT.parent)}:{line}")

    assert not offenders, (
        "El «último + 1» de una secuencia debe leerse e insertarse en la misma "
        "transacción (transaction.atomic()): " + ", ".join(offenders)
    )


def test_the_guard_catches_an_unprotected_read(tmp_path):
    bad = tmp_path / "models.py"
    bad.write_text(
        "def save(self):\n"
        "    latest = M.objects.order_by('-sequence').first()\n"
        "    with transaction.atomic():\n"
        "        other = M.objects.order_by('-sequence').first()\n",
        encoding="utf-8",
    )

    assert _sequence_reads_outside_atomic(bad) == [2]
