"""LV-288: el orden por columna «funcionaba mal» — cuatro defectos reales.

Reporte del usuario (2026-10-07, con captura de Permisos): *«está funcionando mal el
tema de ascendente y descendente»*. Reproducido en el demo con 24 permisos:

1. **Filtrar o buscar perdía el orden.** Un `<form method="get">` envía sólo sus
   campos, y el `sort`/`dir` no eran campos: ordenar, escribir en la búsqueda (o
   «Filtrar») y la lista volvía a su orden de siempre.
2. **Los vacíos saltaban de un extremo al otro.** SQLite pone los `NULL` primero al
   ascender: la lista «ascendente» de vigencias abría con «Esperando a la DGAC».
3. **«Estado» ordenaba por el código y mostraba otra cosa.** La celda dice
   «Caducado» para un aprobado con la vigencia vencida, y el orden por el código
   guardado dejaba esos caducados repartidos entre los aprobados.
4. **La flecha quedaba lejos del rótulo**, pegada al borde de la celda, y se leía como
   la de la columna de al lado.
"""

import re
from datetime import date, timedelta
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from apps.operations.models import FlightPermission
from apps.registry.models import CostCenter

TODAY = timezone.localdate()
CSS = Path(settings.BASE_DIR) / "static" / "css" / "app.css"


@pytest.fixture
def admin(client, db):
    user = User.objects.create_superuser("s288", "s288@test.com", "pw")  # nosec B106
    client.force_login(user)
    return client


@pytest.fixture
def centre(db):
    return CostCenter.objects.create(code="CC288", name="Faena", operates_flights=True)


def _permit(centre, folio, status, start=None, end=None, **extra):
    return FlightPermission.objects.create(
        internal_folio=folio,
        cost_center=centre,
        purpose="photogrammetry",
        status=status,
        permission_number=f"9{folio[-3:]}" if status == "approved" else None,
        location="Sector",
        area_type="unpopulated",
        valid_from=start,
        valid_until=end,
        **extra,
    )


def _filter_form(body):
    """El formulario de filtros de la lista: el que tiene la búsqueda `q` (el primer
    `<form method="get">` de la página es la búsqueda global del encabezado)."""
    forms = re.findall(r'<form method="get".*?</form>', body, re.S)
    return next(
        form for form in forms if 'name="q"' in form and "global-search" not in form
    )


def _folios(client, **params):
    response = client.get(reverse("permission-list"), params)
    return [permit.internal_folio for permit in response.context["objects"]]


@pytest.mark.django_db
class TestTheOrderSurvivesFilteringAndSearching:
    def test_the_filter_form_carries_the_active_sort(self, admin, centre):
        _permit(centre, "P-001", "requested")

        body = admin.get(
            reverse("permission-list"), {"sort": "validity", "dir": "desc"}
        ).content.decode()
        form = _filter_form(body)

        assert 'name="sort" value="validity"' in form
        assert 'name="dir" value="desc"' in form

    def test_the_live_search_input_sits_in_that_same_form(self, admin, centre):
        """`hx-include="closest form"` manda lo que haya en el formulario: si los
        ocultos están en él, la búsqueda en vivo conserva el orden."""
        _permit(centre, "P-001", "requested")

        body = admin.get(
            reverse("permission-list"), {"sort": "number", "dir": "asc"}
        ).content.decode()
        form = _filter_form(body)

        assert 'hx-include="closest form"' in form
        assert 'name="sort"' in form

    def test_without_a_sort_the_form_stays_clean(self, admin, centre):
        _permit(centre, "P-001", "requested")

        body = admin.get(reverse("permission-list")).content.decode()
        form = _filter_form(body)

        assert 'name="sort"' not in form
        assert 'name="dir"' not in form

    def test_an_invented_sort_never_reaches_the_form(self, admin, centre):
        """El valor sale de la lista blanca de la vista, no de la URL."""
        _permit(centre, "P-001", "requested")

        body = admin.get(
            reverse("permission-list"), {"sort": '"><script>x</script>', "dir": "asc"}
        ).content.decode()
        form = _filter_form(body)

        assert "<script>x" not in form
        assert 'name="sort"' not in form

    @pytest.mark.parametrize(
        "list_name",
        ["alert-list", "document-list", "deliverable-list", "nonconformity-list"],
    )
    def test_the_other_sortable_lists_do_it_too(self, admin, list_name):
        response = admin.get(reverse(list_name))
        declared = list(response.context["worktable_sort"]["columns"])
        column = declared[0]

        body = admin.get(
            reverse(list_name), {"sort": column, "dir": "desc"}
        ).content.decode()
        form = _filter_form(body)

        assert f'name="sort" value="{column}"' in form
        assert 'name="dir" value="desc"' in form


@pytest.mark.django_db
class TestBlanksGoLast:
    def _setup(self, centre):
        _permit(centre, "P-001", "requested")  # sin fechas
        _permit(centre, "P-002", "approved", date(2026, 8, 1), date(2026, 10, 1))
        _permit(centre, "P-003", "approved", date(2026, 8, 1), date(2026, 12, 1))
        _permit(centre, "P-004", "requested")  # sin fechas

    def test_ascending_does_not_open_with_the_blanks(self, admin, centre):
        self._setup(centre)

        order = _folios(admin, sort="validity", dir="asc")

        assert order[:2] == ["P-002", "P-003"]
        assert set(order[2:]) == {"P-001", "P-004"}

    def test_descending_keeps_them_last_as_well(self, admin, centre):
        self._setup(centre)

        order = _folios(admin, sort="validity", dir="desc")

        assert order[:2] == ["P-003", "P-002"]
        assert set(order[2:]) == {"P-001", "P-004"}


@pytest.mark.django_db
class TestStatusSortsByWhatTheColumnShows:
    def _setup(self, centre):
        _permit(
            centre,
            "P-001",
            "approved",
            TODAY - timedelta(days=5),
            TODAY + timedelta(days=20),
        )
        # Aprobado con la vigencia vencida: la celda dice «Caducado».
        _permit(
            centre,
            "P-002",
            "approved",
            TODAY - timedelta(days=90),
            TODAY - timedelta(days=2),
        )
        _permit(centre, "P-003", "requested")
        _permit(centre, "P-004", "denied")
        _permit(
            centre,
            "P-005",
            "approved",
            TODAY - timedelta(days=5),
            TODAY + timedelta(days=30),
        )
        _permit(
            centre,
            "P-006",
            "approved",
            TODAY - timedelta(days=60),
            TODAY - timedelta(days=1),
        )
        _permit(
            centre,
            "P-007",
            "completed",
            TODAY - timedelta(days=60),
            TODAY - timedelta(days=30),
        )

    def test_the_lapsed_ones_are_one_group_not_scattered_among_the_approved(
        self, admin, centre
    ):
        self._setup(centre)

        order = _folios(admin, sort="status", dir="asc")

        # Solicitado, aprobados, completado, caducados, rechazado.
        assert order == ["P-003", "P-001", "P-005", "P-007", "P-002", "P-006", "P-004"]

    def test_descending_is_the_exact_reverse_of_the_groups(self, admin, centre):
        self._setup(centre)

        order = _folios(admin, sort="status", dir="desc")

        assert order[0] == "P-004"
        assert order[-1] == "P-003"
        # Caducados contiguos también al revés.
        lapsed = [order.index("P-002"), order.index("P-006")]
        assert abs(lapsed[0] - lapsed[1]) == 1

    def test_ties_inside_a_group_keep_the_folio_order(self, admin, centre):
        self._setup(centre)

        asc = _folios(admin, sort="status", dir="asc")
        desc = _folios(admin, sort="status", dir="desc")

        assert asc.index("P-001") < asc.index("P-005")
        assert desc.index("P-001") < desc.index("P-005")

    def test_the_shown_badge_agrees_with_the_group(self, admin, centre):
        """El guardián de fondo: lo que la fila dice debe ser lo que la agrupa."""
        self._setup(centre)

        response = admin.get(
            reverse("permission-list"), {"sort": "status", "dir": "asc"}
        )
        shown = [
            "lapsed" if permit.has_lapsed else permit.status
            for permit in response.context["objects"]
        ]

        # Cada estado mostrado aparece en **un solo tramo** de la lista.
        runs = [shown[0]]
        for value in shown[1:]:
            if value != runs[-1]:
                runs.append(value)
        assert len(runs) == len(set(runs)), runs


class TestTheArrowSitsNextToTheLabel:
    def test_the_header_link_is_inline_not_spread_to_the_cell_edges(self):
        css = CSS.read_text(encoding="utf-8")
        block = re.search(r"\.worktable-sort\s*\{([^}]*)\}", css).group(1)

        assert "inline-flex" in block
        assert "space-between" not in block
