"""LV-355 F0: la red de seguridad del informe mensual a la DGAC.

El A4 del informe mensual es un **contrato de salida**: va firmado ante la
autoridad. Hasta ahora lo vigilaban pruebas que localizan una clase o un texto,
y ninguna miraba el documento entero, así que un cambio de plantilla o de CSS en
otra parte (cabecera A4 de las otras vistas, tubería de exportación) podía mover
una etiqueta del mensual sin que nada fallara. Este archivo guarda el HTML
normalizado de un `ReportRun` de datos **ficticios** fijos —el informe mensual y
el Dato Ejecutivo— y falla ante cualquier diferencia.

Qué se normaliza (y sólo eso): el token CSRF, los UUID de las rutas, el hash de
contenido de los estáticos y el nonce de CSP. Todo lo demás es salida.

⚠️ **Fechas fijadas, declaradas**: `pin_now` fija el instante en 2026-09-02, así
que «hoy» (por ejemplo para la lista de avisos previos a la emisión) no depende
del día en que se corra. El corte del informe sale del payload (2026-08-31).

Cuando el cambio de salida es **a propósito**, se regenera a mano y se revisa el
diff del `.html` en el PR:

    $env:UPDATE_SNAPSHOTS = "1"; uv run pytest apps/reporting/test_snapshot_monthly.py
"""

import json
import os
import re
from datetime import date, datetime, timezone as dt_timezone
from pathlib import Path

import pytest
from django.contrib.auth.models import Permission, User
from django.urls import reverse

from apps.core.testing import pin_now
from apps.reporting.models import ReportRun

SNAPSHOTS = Path(__file__).parent / "snapshots"
PERIOD = date(2026, 8, 1)
NOW = datetime(2026, 9, 2, 15, 0, tzinfo=dt_timezone.utc)

UUID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE
)
CSRF = re.compile(r'(name="csrfmiddlewaretoken" value=")[^"]*(")')
CSRF_META = re.compile(r'(name="csrf-token" content=")[^"]*(")')
CSRF_HEADER = re.compile(r'("X-CSRFToken": ")[^"]*(")')
NONCE = re.compile(r'(nonce=")[^"]*(")')
# El sello «Impreso desde AeroControl · url · AAAA-MM-DD HH:MM · usuario» de
# `base.html` usa la hora **real** del reloj (`{% now %}`, no `timezone.now`): es
# el único «ahora» de la página y no es salida del informe.
PRINT_STAMP = re.compile(
    r"(Impreso desde AeroControl · [^<]*? · )\d{4}-\d\d-\d\d \d\d:\d\d( · )"
)
STATIC_HASH = re.compile(r"(/static/[^\s\"'?]*?)\.[0-9a-f]{12}(\.[a-z0-9]+)")
STATIC_QUERY = re.compile(r"(/static/[^\s\"']*?)\?v=[^\s\"']*")


def normalize(html):
    """El HTML sin lo que cambia entre corridas y no es salida del informe."""
    html = UUID.sub("<uuid>", html)
    html = CSRF.sub(r"\1<csrf>\2", html)
    html = CSRF_META.sub(r"\1<csrf>\2", html)
    html = CSRF_HEADER.sub(r"\1<csrf>\2", html)
    html = NONCE.sub(r"\1<nonce>\2", html)
    html = PRINT_STAMP.sub(r"\1<now>\2", html)
    html = STATIC_HASH.sub(r"\1\2", html)
    html = STATIC_QUERY.sub(r"\1", html)
    # Sin espacio en blanco al final de línea ni líneas vacías repetidas: la
    # plantilla las produce de `{% if %}` y no son contenido.
    lines = [line.rstrip() for line in html.splitlines()]
    return "\n".join(line for line in lines if line.strip()) + "\n"


@pytest.fixture
def frozen_report(db, monkeypatch):
    pin_now(monkeypatch, NOW)
    payload = json.loads((SNAPSHOTS / "payload_2026_08.json").read_text("utf-8"))
    return ReportRun.objects.create(
        period=PERIOD,
        revision=0,
        generated_by="test",
        payload=payload,
        findings=[
            {
                "title": "Dependencia de una persona",
                "text": "La faena CC102 depende de un solo operador designado.",
            }
        ],
        period_note="Nota ficticia del periodo para la prueba.",
        actions=[
            {
                "action": "Renovar el permiso JEJ-2026-901",
                "owner": "ADC",
                "due": "15-09-2026",
            }
        ],
    )


@pytest.fixture
def reader_client(client, db):
    user = User.objects.create_user("reader", password="x")
    user.user_permissions.add(
        Permission.objects.get(
            codename="view_reportrun", content_type__app_label="reporting"
        )
    )
    client.force_login(user)
    return client


def _check(name, html):
    path = SNAPSHOTS / f"{name}.html"
    current = normalize(html)
    if os.environ.get("UPDATE_SNAPSHOTS") == "1":
        path.write_text(current, encoding="utf-8", newline="\n")
        return
    assert path.exists(), f"falta {path.name}: corre con UPDATE_SNAPSHOTS=1"
    expected = path.read_text(encoding="utf-8")
    if current != expected:
        old, new = expected.splitlines(), current.splitlines()
        first = next(
            (i for i, (a, b) in enumerate(zip(old, new)) if a != b),
            min(len(old), len(new)),
        )
        raise AssertionError(
            f"la salida de {name} cambió (primera diferencia en la línea "
            f"{first + 1}):\n- {old[first : first + 1]}\n+ {new[first : first + 1]}\n"
            "Si es a propósito: UPDATE_SNAPSHOTS=1 y revisar el diff."
        )


@pytest.mark.django_db
class TestTheMonthlyReportIsFrozenOutput:
    def test_the_monthly_report_html_does_not_change(
        self, frozen_report, reader_client
    ):
        response = reader_client.get(reverse("monthly-report"), {"period": "2026-08"})

        assert response.status_code == 200
        assert response.context["run"].pk == frozen_report.pk
        _check("monthly_2026_08", response.content.decode())

    def test_the_executive_brief_html_does_not_change(
        self, frozen_report, reader_client
    ):
        response = reader_client.get(
            reverse("monthly-report-brief"), {"period": "2026-08"}
        )

        assert response.status_code == 200
        _check("brief_2026_08", response.content.decode())

    def test_the_numbering_ends_at_page_five_with_the_roster_annex(
        self, frozen_report, reader_client
    ):
        """El contrato de páginas: portada, resumen, permisos, cobertura+plan y
        el anexo de nómina. Si el reparto cambia, esto lo dice antes del diff."""
        response = reader_client.get(reverse("monthly-report"), {"period": "2026-08"})

        assert response.context["total_pages"] == 5
        assert len(response.context["roster_sheets"]) == 1


class TestTheNormalizerOnlyRemovesNoise:
    def test_it_hides_csrf_uuids_and_static_hashes_and_nothing_else(self):
        html = (
            '<input name="csrfmiddlewaretoken" value="abc123">\n'
            '<a href="/reports/monthly/'
            '3f2b8c1e-1111-4222-8333-444455556666/approve/">x</a>\n'
            '<link href="/static/css/report-a4.0123456789ab.css">\n'
            "<p>Vigencia al corte</p>\n"
        )

        out = normalize(html)

        assert "abc123" not in out
        assert "3f2b8c1e" not in out
        assert "/static/css/report-a4.css" in out
        assert "<p>Vigencia al corte</p>" in out
