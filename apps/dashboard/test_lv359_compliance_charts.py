"""LV-359 (fase 2): los gráficos de «Cumplimiento»: SVG de servidor, datos y contraste calculado.

Qué se vigila:
- las tres marcas (`ring`, `hbar`, `sparkline`): geometría en atributos, sin `style`, con `role="img"`,
  `<title>`, `<desc>` y escapado;
- coherencia: «vencido» y «hasta 30 días» de los anillos son EXACTAMENTE las cifras de la tarjeta del
  panel, con los mismos argumentos (`upcoming_expirations` + `bucket_for`);
- permisos: cada categoría con el permiso de sus fuentes; alertas sólo con `view_alert`;
- la tabla del mapa de calor es una `<table>` real, sin `colspan` ni `.table-normalized`;
- contraste CALCULADO de los tokens `--id-cx-*` y de los rellenos de los gráficos.
"""

import re
from datetime import timedelta
from uuid import uuid4

import pytest
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import timezone

from apps.compliance.models import Alert, AlertRule
from apps.core.models import OperationalTenant
from apps.core.test_lv315_identity_foundation import (
    APP,
    IDENTITY,
    _contrast,
    _resolve,
    _theme_tokens as _light_and_partial_dark,
)
from apps.core.tenancy import visible_tenant_ids
from apps.core.testing import login_as
from apps.dashboard.compliance_data import (
    LEVEL_SYMBOL,
    LEVELS,
    WEEKS,
    expiry_data,
    heat_step,
)
from apps.dashboard.templatetags.compliance_charts import (
    render_hbar,
    render_ring,
    render_sparkline,
)
from apps.maintenance.models import MaintenanceRecord
from apps.operations.models import FlightPermission
from apps.registry.models import Aircraft, CostCenter, Operator
from apps.reporting.models import ReportRun

URL = "dashboard-compliance"
HX = {"HTTP_HX_REQUEST": "true"}
ALL_SOURCES = (
    "view_alert",
    "view_document",
    "view_aircraft",
    "view_operator",
    "view_qualification",
    "view_knowledgeassessment",
    "view_flightpermission",
    "view_maintenancerecord",
    "view_monthlycompliancereview",
)


def _theme_tokens(theme):
    """Los tokens efectivos de un tema, con el bloque oscuro COMPLETO.

    El ayudante de `test_lv315` sólo lee los bloques `[data-theme="dark"] {` sueltos y se pierde el
    de `app.css` que se declara como `[data-theme="dark"], [data-bs-theme="dark"] {` (ahí viven
    `--ac-surface` y compañía): con él, el fondo oscuro de una tarjeta se leería como el claro y un
    par oscuro se mediría contra un color que no existe.
    """
    tokens = _light_and_partial_dark(theme)
    if theme == "dark":
        for css in (APP, IDENTITY):
            for block in re.findall(
                r'(?m)^\[data-theme="dark"\](?:,\s*\[data-bs-theme="dark"\])?\s*\{([^}]*)\}',
                css,
            ):
                tokens.update(
                    {
                        k: v.strip()
                        for k, v in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", block)
                    }
                )
    return tokens


# --- las tres marcas ------------------------------------------------------------------------


class TestRing:
    def test_it_is_an_accessible_image_with_numbers_in_attributes(self):
        svg = render_ring(
            [("id-cx-seg--overdue", 1), ("id-cx-seg--later", 3)],
            "u1",
            "Documents: 1 overdue",
            "Documents: 1 overdue, 3 later.",
            center=4,
        )
        assert 'role="img"' in svg
        assert 'aria-labelledby="u1-t u1-d"' in svg
        assert '<title id="u1-t">Documents: 1 overdue</title>' in svg
        assert '<desc id="u1-d">Documents: 1 overdue, 3 later.</desc>' in svg
        assert "style=" not in svg
        assert svg.count("<circle") == 3  # pista + dos tramos
        assert ">4</text>" in svg

    def test_the_segments_cover_the_circumference_with_a_gap_between_them(self):
        svg = render_ring([("a", 1), ("b", 3)], "u", "t", "d", size=96, stroke=12)
        radius = (96 - 12) / 2
        circumference = 2 * 3.141592653589793 * radius
        arrays = [
            tuple(map(float, m))
            for m in re.findall(r'stroke-dasharray="([\d.]+) ([\d.]+)"', svg)
        ]
        assert len(arrays) == 2
        # 1/4 y 3/4 del perímetro, menos el hueco de 1,5 de cada tramo
        assert arrays[0][0] == pytest.approx(circumference / 4 - 1.5, abs=0.02)
        assert arrays[1][0] == pytest.approx(circumference * 3 / 4 - 1.5, abs=0.02)
        offsets = [float(m) for m in re.findall(r'stroke-dashoffset="(-?[\d.]+)"', svg)]
        assert offsets[0] == 0
        assert offsets[1] == pytest.approx(-circumference / 4, abs=0.02)

    def test_a_single_segment_is_a_full_ring_without_a_gap(self):
        svg = render_ring([("a", 5)], "u", "t", "d")
        visible, rest = map(
            float, re.search(r'stroke-dasharray="([\d.]+) ([\d.]+)"', svg).groups()
        )
        assert visible + rest == pytest.approx(2 * 3.141592653589793 * 42, abs=0.05)
        assert rest < 0.05

    def test_an_empty_ring_is_just_the_track(self):
        svg = render_ring([("a", 0), ("b", 0)], "u", "t", "d", center=0)
        assert svg.count("<circle") == 1
        assert "id-cx-track" in svg
        assert ">0</text>" in svg

    def test_text_is_escaped(self):
        svg = render_ring([("a", 1)], "u", "<script>x</script>", '"><img src=x>')
        assert "<script>" not in svg
        assert "<img" not in svg


class TestHbar:
    def test_it_prints_every_figure_and_scales_the_bars(self):
        svg = render_hbar(
            [("0–7 days", 4, "id-cx-bar--fresh"), ("8–30 days", 2, "id-cx-bar--mid")],
            "b1",
            "6 open alerts",
            "desc",
        )
        assert 'role="img"' in svg and "<title" in svg and "<desc" in svg
        assert "style=" not in svg
        widths = [float(w) for w in re.findall(r'<rect[^>]* width="([\d.]+)"', svg)]
        assert len(widths) == 2
        assert widths[0] == pytest.approx(widths[1] * 2, abs=0.05)
        for figure in (">4</text>", ">2</text>"):
            assert figure in svg

    def test_a_zero_bar_has_no_rect_but_keeps_its_figure(self):
        svg = render_hbar([("a", 0, "x"), ("b", 3, "y")], "b", "t", "d")
        assert svg.count("<rect") == 1
        assert ">0</text>" in svg

    def test_labels_are_escaped(self):
        svg = render_hbar([("<b>x</b>", 1, "c")], "b", "t", "d")
        assert "<b>" not in svg


class TestSparkline:
    def test_it_draws_a_polyline_and_the_last_point(self):
        svg = render_sparkline([1, 3, 2, 5], "s", "Trend", "Rising")
        assert "<polyline" in svg and "<circle" in svg
        assert 'role="img"' in svg and "<title" in svg and "<desc" in svg
        assert "style=" not in svg
        points = re.search(r'points="([^"]+)"', svg).group(1).split()
        assert len(points) == 4

    def test_one_point_is_only_a_dot_and_no_points_is_empty(self):
        assert "<polyline" not in render_sparkline([7], "s", "t", "d")
        assert "<circle" not in render_sparkline([], "s", "t", "d")

    def test_a_flat_series_does_not_divide_by_zero(self):
        assert "<polyline" in render_sparkline([2, 2, 2], "s", "t", "d")


# --- datos ----------------------------------------------------------------------------------


@pytest.fixture
def mix(db):
    """Vencimientos en todos los tramos, en dos faenas, más mantenciones."""
    today = timezone.localdate()
    a = CostCenter.objects.create(code="CC738", name="Faena")
    b = CostCenter.objects.create(code="CC861", name="Otra")

    def aircraft(cc, reg, days):
        return Aircraft.objects.create(
            registration=reg,
            type="RPA",
            model="M3",
            manufacturer="DJI",
            cost_center=cc,
            status="active",
            insurance_expiry=today + timedelta(days=days),
        )

    def operator(cc, emp, days):
        return Operator.objects.create(
            employee_id=emp,
            full_name=f"Piloto {emp}",
            cost_center=cc,
            credential_expiry=today + timedelta(days=days),
        )

    planes = [
        aircraft(a, "RPA-0001", -10),  # vencido
        aircraft(a, "RPA-0002", 5),  # ≤7
        aircraft(b, "RPA-0003", 12),  # ≤15
        aircraft(b, "RPA-0004", 70),  # 31–90
    ]
    for emp, days in (("E1", 25), ("E2", 40), ("E3", -3)):
        operator(a if emp != "E2" else b, emp, days)
    permit = FlightPermission.objects.create(
        cost_center=a,
        purpose="Survey",
        location="Sector",
        valid_from=today - timedelta(days=30),
        valid_until=today + timedelta(days=20),
    )
    permit.aircraft_fleet.add(planes[0])
    MaintenanceRecord.objects.create(
        aircraft=planes[0],
        maintenance_type="scheduled",
        status="pending",
        scheduled_date=today - timedelta(days=2),
    )
    MaintenanceRecord.objects.create(
        aircraft=planes[1],
        maintenance_type="scheduled",
        status="pending",
        scheduled_date=today + timedelta(days=40),
    )
    MaintenanceRecord.objects.create(
        aircraft=planes[2], maintenance_type="to_be_defined", status="pending"
    )
    return a, b


def _ctx(client, **params):
    return client.get(reverse(URL), params, **HX).context


def _sums(rings):
    non_maintenance = [r for r in rings if r["key"] != "maintenance"]
    overdue = sum(r["counts"]["overdue"] for r in non_maintenance)
    soon = sum(
        r["counts"]["due_7"] + r["counts"]["due_15"] + r["counts"]["due_30"]
        for r in non_maintenance
    )
    return overdue, soon


@pytest.mark.django_db
@pytest.mark.parametrize("filtered", [False, True])
def test_overdue_and_within_30_equal_the_panel_card(mix, filtered):
    """La igualdad que el diseño exige: mismas cifras que la tarjeta de arriba del panel, con los
    mismos argumentos. Si el cálculo de la sección se separara del de la tarjeta, cae."""
    a, _b = mix
    client = login_as(*ALL_SOURCES)
    params = {"cost_center": a.pk} if filtered else {}

    panel = client.get(reverse("dashboard"), params).context
    overdue, soon = _sums(_ctx(client, **params)["cx_rings"])

    assert panel["overdue_count"] >= 1 and panel["expiring_count"] >= 2  # no es vacuo
    assert overdue == panel["overdue_count"]
    assert soon == panel["expiring_count"]


@pytest.mark.django_db
def test_the_heat_map_and_the_rings_count_the_same_things(mix):
    client = login_as(*ALL_SOURCES)
    context = _ctx(client)
    for ring, row in zip(context["cx_rings"], context["cx_heat_rows"], strict=True):
        assert ring["key"] == row["key"]
        assert sum(c["n"] for c in row["wide"]) == ring["total"]
        assert sum(c["n"] for c in row["narrow"]) == ring["total"]
        assert len(row["wide"]) == 1 + WEEKS
        assert len(row["narrow"]) == 4
        assert row["wide"][0]["n"] == ring["counts"]["overdue"] == row["narrow"][0]["n"]


@pytest.mark.django_db
def test_each_category_needs_the_permission_of_its_sources(mix):
    aircraft_only = _ctx(login_as("view_aircraft"))
    assert [r["key"] for r in aircraft_only["cx_rings"]] == ["aircraft"]

    people = _ctx(login_as("view_operator", "view_flightpermission"))
    assert [r["key"] for r in people["cx_rings"]] == ["people", "permits"]

    full = _ctx(login_as(*ALL_SOURCES))
    assert [r["key"] for r in full["cx_rings"]] == [
        "papers",
        "people",
        "aircraft",
        "permits",
        "maintenance",
    ]


@pytest.mark.django_db
def test_maintenance_appears_only_with_view_maintenancerecord(mix):
    without = login_as("view_aircraft", "view_alert")
    html = without.get(reverse(URL), **HX).content.decode()
    assert 'data-cx-ring="maintenance"' not in html
    assert 'data-cx-block="maintenance"' not in html
    assert "RPA-" not in html  # y ninguna matrícula se nombra

    with_perm = login_as("view_aircraft", "view_maintenancerecord")
    html = with_perm.get(reverse(URL), **HX).content.decode()
    assert 'data-cx-ring="maintenance"' in html
    assert 'data-cx-block="maintenance"' in html


@pytest.mark.django_db
def test_maintenance_counts_dated_records_and_names_the_undated_apart(mix):
    context = _ctx(login_as("view_maintenancerecord"))
    ring = context["cx_rings"][0]
    assert ring["key"] == "maintenance"
    assert ring["counts"]["overdue"] == 1  # sin completar y con fecha pasada
    assert ring["counts"]["later"] == 1  # a 40 días
    assert ring["total"] == 2  # la sin fecha no entra al anillo
    assert context["cx_maintenance_to_define"] == 1  # `needing_planning`


@pytest.mark.django_db
def test_the_week_columns_and_the_narrow_view_partition_the_ninety_days(mix):
    today = timezone.localdate()
    user = login_as(*ALL_SOURCES).user
    data = expiry_data(user, None, today, visible_tenant_ids(user))
    assert len(data["heat_wide_columns"]) == 1 + WEEKS
    assert len(data["heat_narrow_columns"]) == 4
    # el símbolo de una semana es el del tramo de su primer día
    symbols = [c["symbol"] for c in data["heat_wide_columns"]]
    assert symbols[:2] == [LEVEL_SYMBOL["overdue"], LEVEL_SYMBOL["due_7"]]
    assert symbols[2] == LEVEL_SYMBOL["due_15"]  # S2 (días 8–14) empieza en el 8
    assert symbols[-1] == LEVEL_SYMBOL["later"]


def test_the_heat_scale():
    assert [heat_step(n) for n in (0, 1, 2, 3, 4, 6, 7, 40)] == [
        0, 1, 2, 2, 3, 3, 4, 4,
    ]  # fmt: skip


# --- alertas --------------------------------------------------------------------------------


def _alert(rule, age_days, assigned_to=None):
    aircraft = Aircraft.objects.first()
    alert = Alert.objects.create(
        alert_rule=rule,
        content_type=ContentType.objects.get_for_model(Aircraft),
        object_id=aircraft.pk if aircraft else uuid4(),
        message="x",
        assigned_to=assigned_to,
    )
    Alert.objects.filter(pk=alert.pk).update(
        triggered_at=timezone.now() - timedelta(days=age_days, hours=1)
    )
    return alert


@pytest.fixture
def rule(db):
    return AlertRule.objects.create(
        name="Seguros",
        entity_type="registry.aircraft",
        field_to_watch="insurance_expiry",
        days_before_expiry=30,
    )


@pytest.mark.django_db
def test_alerts_are_bucketed_by_age_with_a_single_aggregation(
    mix, rule, django_assert_num_queries
):
    for age in (0, 3, 7, 8, 30, 31, 90):
        _alert(rule, age)
    client = login_as("view_alert")
    context = _ctx(client)
    alerts = context["cx_alerts"]
    assert (alerts["fresh"], alerts["mid"], alerts["old"]) == (3, 2, 2)
    assert alerts["total"] == 7 == alerts["unassigned"]
    assert [b[1] for b in alerts["bars"]] == [3, 2, 2]
    # la cifra de la sección es la del panel
    assert client.get(reverse("dashboard")).context["alert_count"] == 7


@pytest.mark.django_db
def test_assigned_alerts_do_not_count_as_unowned(mix, rule):
    owner = login_as().user
    _alert(rule, 1, assigned_to=owner)
    _alert(rule, 2)
    alerts = _ctx(login_as("view_alert"))["cx_alerts"]
    assert alerts["total"] == 2 and alerts["unassigned"] == 1


@pytest.mark.django_db
def test_alerts_need_view_alert_and_a_user_with_only_alerts_sees_only_alerts(mix, rule):
    _alert(rule, 1)
    other = login_as("view_aircraft")
    assert "cx_alerts" not in _ctx(other)
    html = other.get(reverse(URL), **HX).content.decode()
    assert 'data-cx-block="alerts"' not in html

    only = login_as("view_alert")
    html = only.get(reverse(URL), **HX).content.decode()
    assert 'data-cx-block="alerts"' in html
    for block in ("rings", "heat", "maintenance"):
        assert f'data-cx-block="{block}"' not in html
    assert "<svg" in html and 'class="id-cx-fig">1<' in html


@pytest.mark.django_db
def test_alerts_of_another_tenant_are_not_counted(mix):
    mine = OperationalTenant.objects.create(name="Mine", slug="mine")
    foreign = AlertRule.objects.create(
        name="Ajena",
        entity_type="registry.aircraft",
        field_to_watch="insurance_expiry",
        days_before_expiry=30,
    )
    own = AlertRule.objects.create(
        name="Propia",
        entity_type="registry.aircraft",
        field_to_watch="insurance_expiry",
        days_before_expiry=30,
        tenant=mine,
    )
    _alert(foreign, 1)
    _alert(own, 1)
    client = login_as("view_alert", member_of=mine)
    assert _ctx(client)["cx_alerts"]["total"] == 1


# --- HTML -----------------------------------------------------------------------------------


@pytest.fixture
def section_html(mix, rule):
    _alert(rule, 2)
    return login_as(*ALL_SOURCES).get(reverse(URL), **HX).content.decode()


@pytest.mark.django_db
def test_the_heat_map_is_a_real_table_without_colspan(section_html):
    assert "colspan" not in section_html
    assert "table-normalized" not in section_html
    tables = re.findall(r"<table.*?</table>", section_html, flags=re.S)
    assert len(tables) == 2  # ancho y angosto (bajo 576 px)
    wide, narrow = tables
    for table, columns in ((wide, 1 + WEEKS), (narrow, 4)):
        assert "<caption" in table
        assert (
            table.count('scope="col"') == 1 + columns
        )  # la columna de categoría y las demás
        rows = re.findall(r"<tr>.*?</tr>", table, flags=re.S)
        assert len(rows) == 1 + 5  # encabezado + cinco categorías
        for row in rows[1:]:
            assert 'scope="row"' in row
            assert row.count("<td") == columns  # una cifra en cada celda
            assert len(re.findall(r"<td[^>]*><b>\d+</b></td>", row)) == columns


@pytest.mark.django_db
def test_every_svg_says_what_it_shows_and_prints_its_figure_beside_it(section_html):
    svgs = re.findall(r"<svg\b.*?</svg>", section_html, flags=re.S)
    assert len(svgs) == 5 + 1  # cinco anillos y las barras de alertas
    for svg in svgs:
        assert 'role="img"' in svg
        assert re.search(r"<title id=\"[^\"]+\">[^<]+</title>", svg)
        assert re.search(r"<desc id=\"[^\"]+\">[^<]+</desc>", svg)
        assert "style=" not in svg
    # la cifra de cada anillo está impresa FUERA de la imagen
    figures = re.findall(r'<b class="id-cx-fig">(\d+)</b>', section_html)
    assert len(figures) >= 5
    assert "style=" not in section_html


@pytest.mark.django_db
def test_every_level_has_a_symbol_and_a_text_and_not_only_a_color(section_html):
    for level in LEVELS:
        assert LEVEL_SYMBOL[level] in section_html
    chips = re.findall(
        r'<span class="id-chip id-chip--(\w+)">(.*?)</span></li>',
        section_html,
        flags=re.S,
    )
    assert len(chips) == 5 * 5
    for _tone, body in chips:
        assert re.search(r'aria-hidden="true">[✕▲◆●○]</span>', body)
        assert re.search(r"<b>\d+</b>\s+\S", body)  # la cifra y su rótulo


# --- consultas ------------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_data_budget_does_not_grow_with_the_data(
    mix, rule, django_assert_num_queries
):
    from apps.dashboard.test_lv359_compliance_section import (
        SECTION_QUERY_BUDGET,
        _multiply,
    )

    # con informe, como el techo medido en 	est_lv359_compliance_section: una consulta más
    ReportRun.objects.create(
        period=timezone.localdate().replace(day=1), generated_by="cron"
    )
    client = login_as(*ALL_SOURCES, "view_reportrun")
    client.get(reverse(URL), **HX)
    _multiply(15)
    for age in range(12):
        _alert(rule, age)
    with django_assert_num_queries(SECTION_QUERY_BUDGET):
        assert client.get(reverse(URL), **HX).status_code == 200


# --- contraste calculado (no leído de un navegador) ---------------------------------------


class TestContrast:
    HEAT = ("--id-cx-heat-1", "--id-cx-heat-2", "--id-cx-heat-3", "--id-cx-heat-4")

    @pytest.mark.parametrize("theme", ["light", "dark"])
    @pytest.mark.parametrize("step", HEAT)
    def test_the_figure_reaches_4_5_to_1_on_each_heat_step(self, theme, step):
        tokens = _theme_tokens(theme)
        ratio = _contrast(tokens["--id-cx-ink"], tokens[step])
        assert ratio >= 4.5, (theme, step, ratio)

    @pytest.mark.parametrize("theme", ["light", "dark"])
    def test_the_empty_cell_figure_reaches_4_5_to_1(self, theme):
        tokens = _theme_tokens(theme)
        assert _contrast(tokens["--ac-text-muted"], tokens["--ac-surface"]) >= 4.5

    @pytest.mark.parametrize("theme", ["light", "dark"])
    @pytest.mark.parametrize(
        "fill",
        [
            "--sev-critical-text",
            "--sev-warning-text",
            "--sev-caution-text",
            "--sev-advisory-text",
            "--sev-nominal-text",
        ],
    )
    def test_each_chart_fill_is_distinguishable_from_the_track_and_the_card(
        self, theme, fill
    ):
        """Gráficos: 3:1 contra la pista y contra la tarjeta (WCAG 1.4.11, objetos gráficos)."""
        tokens = _theme_tokens(theme)
        for ground in ("--id-cx-track", "--ac-surface"):
            ratio = _contrast(tokens[fill], tokens[ground])
            assert ratio >= 3.0, (theme, fill, ground, ratio)

    @pytest.mark.parametrize("theme", ["light", "dark"])
    def test_the_empty_cell_border_reaches_3_to_1(self, theme):
        tokens = _theme_tokens(theme)
        assert _contrast(tokens["--id-cx-edge"], tokens["--ac-surface"]) >= 3.0

    def test_the_dark_theme_really_redefines_the_tokens(self):
        light, dark = _theme_tokens("light"), _theme_tokens("dark")
        for token in ("--id-cx-ink", "--id-cx-heat-1", "--id-cx-heat-4"):
            assert light[token] != dark[token], token

    def test_fills_use_sev_text_never_sev_border(self):
        """Rellenos con `--sev-*-text`: el borde (1,58–1,81:1) no se distingue del fondo."""
        rules = re.findall(r"(?m)^\.id-cx-(?:seg|bar|spark)[^{]*\{([^}]*)\}", IDENTITY)
        assert rules
        for body in rules:
            assert "-border" not in body, body
            assert re.search(
                r"(?:fill|stroke):\s*var\(--(?:sev-\w+-text|ac-text-secondary)\)", body
            )

    def test_the_section_has_no_animation_and_no_new_prefix(self):
        start = IDENTITY.index("/* D3: «Cumplimiento»")
        end = IDENTITY.index("/* == E: pulido global == */")
        block = IDENTITY[start:end]
        assert not re.search(
            r"\banimation(-[a-z]+)?\s*:|@keyframes|transition\s*:", block
        )
        assert set(re.findall(r"(?m)^\s*(--[\w-]+)\s*:", block)) <= {
            f"--id-cx-{name}"
            for name in ("ink", "track", "edge", "heat-1", "heat-2", "heat-3", "heat-4")
        }

    def test_every_color_used_in_the_heat_cells_resolves_to_a_hex(self):
        tokens = _theme_tokens("light")
        for name in ("--id-cx-ink", "--id-cx-track", "--id-cx-edge", *self.HEAT):
            assert re.fullmatch(r"#[0-9a-f]{6}", _resolve(tokens[name], tokens)), name
