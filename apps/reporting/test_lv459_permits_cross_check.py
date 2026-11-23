"""LV-459: el informe mensual cruzado contra lo que la app muestra de los trámites.

Una auditoría encontró ocho defectos (A1–A8) en los que el informe y el panel decían
cosas distintas del mismo permiso o de la misma solicitud. Cada prueba de esta hoja
**falla con el código anterior** (las pruebas de la auditoría afirmaban el defecto) y
pasa con el arreglo. Datos ficticios; fechas fijas (la fecha es andamio: lección
LV-223), salvo el guardián M6, que compara contra el panel **de hoy** y fija la fecha
de los datos en relación a «hoy» a propósito.
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.compliance.kpis import permit_counts, permit_status_by_cost_center
from apps.operations.models import (
    FlightPermission,
    FlightRecord,
    FlightRequest,
    FlightRequestHistory,
    PermissionHistory,
)
from apps.registry.models import Aircraft, CostCenter, Operator
from apps.reporting.builder import build, collect_permits
from apps.reporting.groups import permit_groups
from apps.reporting.invariants import violations
from apps.reporting.manual import collect_maintenance, collect_mission_records
from apps.reporting.templatetags.report_svg import (
    coverage_bar,
    coverage_state,
    coverage_word,
)

pytestmark = pytest.mark.django_db

PERIOD = date(2026, 11, 1)
CUTOFF = date(2026, 11, 23)


def _aware(day, hour=12):
    return timezone.make_aware(datetime.combine(day, time(hour)))


def _centre(code, **kw):
    kw.setdefault("operates_flights", True)
    return CostCenter.objects.create(code=code, name=f"Faena {code}", **kw)


def _permit(centre, *, status="requested", start=None, end=None, created=None, **kw):
    permit = FlightPermission.objects.create(
        cost_center=centre,
        permission_number=None if status == "requested" else f"N-{centre.code}-{start}",
        purpose="photogrammetry",
        status=status,
        location="Sector ficticio",
        area_type="unpopulated",
        valid_from=start,
        valid_until=end,
        **kw,
    )
    FlightPermission.objects.filter(pk=permit.pk).update(
        created_at=_aware(created or date(2026, 11, 5))
    )
    permit.refresh_from_db()
    return permit


def _move(permit, new_status, on, **fields):
    """Cambia el estado y fecha el movimiento de historial en `on`."""
    for name, value in fields.items():
        setattr(permit, name, value)
    permit.status = new_status
    permit.save()
    last = PermissionHistory.objects.filter(permission=permit).order_by("-sequence")[0]
    PermissionHistory.objects.filter(pk=last.pk).update(created_at=_aware(on))


def _row(payload, code):
    return next(r for r in payload["cost_centres"] if r["code"] == code)


def _request(centre, status="filed", filed_on=date(2026, 11, 12), **kw):
    item = FlightRequest.objects.create(
        title="Sección ficticia",
        cost_center=centre,
        center_lat=Decimal("-23.5"),
        center_lon=Decimal("-70.4"),
        status=status,
        filed_on=filed_on if status != "prepared" else None,
        **kw,
    )
    FlightRequest.objects.filter(pk=item.pk).update(
        created_at=_aware(date(2026, 11, 3))
    )
    item.refresh_from_db()
    return item


# -- A1 / A2 / A3: el estado AL CORTE decide, no la vigencia ni el estado de hoy ------


def test_a1_a_request_with_a_requested_window_after_the_cutoff_still_counts():
    centre = _centre("CC801")
    _permit(centre, start=date(2026, 12, 1), end=date(2027, 2, 28))

    rows = collect_permits(CUTOFF)
    payload, _missing = build(PERIOD, cutoff=CUTOFF)

    assert permit_counts(CUTOFF)["awaiting"] == 1
    assert [r["status"] for r in rows] == ["requested"]
    assert payload["kpis"]["permits_awaiting"]["value"] == 1
    assert _row(payload, "CC801")["permits_awaiting"] == 1
    # Aún sin vigencia: un trámite no habilita, tenga fechas pedidas o no.
    assert rows[0]["in_force"] is False
    assert payload["kpis"]["permits_in_force"]["value"] == 0
    assert violations(payload) == []


def test_a2_approved_after_the_cutoff_for_a_future_window_is_a_request_at_the_cutoff():
    centre = _centre("CC802")
    permit = _permit(centre)
    _move(
        permit,
        FlightPermission.STATUS_APPROVED,
        date(2026, 11, 26),
        permission_number="N-802",
        valid_from=date(2026, 12, 1),
        valid_until=date(2027, 2, 28),
    )

    rows = collect_permits(CUTOFF)
    payload, _missing = build(PERIOD, cutoff=CUTOFF)

    assert len(rows) == 1
    # Estado al corte, y la vigencia de hoy (que se fijó al aprobar, después) no
    # se dibuja: el corte no la conocía.
    assert rows[0]["status"] == "requested"
    assert rows[0]["valid_from"] is None and rows[0]["days_remaining"] is None
    assert payload["kpis"]["permits_awaiting"]["value"] == 1
    # Y no es «aprobado, aún no vigente»: al corte no estaba aprobado.
    assert payload["upcoming_permits"] == []
    assert violations(payload) == []


@pytest.mark.parametrize(
    "terminal",
    [
        FlightPermission.STATUS_DENIED,
        FlightPermission.STATUS_COMPLETED,
        FlightPermission.STATUS_EXPIRED,
    ],
)
def test_a3_a_request_that_reached_a_terminal_state_later_is_rebuilt(terminal):
    centre = _centre("CC803")
    permit = _permit(centre)
    _move(permit, terminal, date(2026, 11, 27))

    rows = collect_permits(CUTOFF)

    assert [r["status"] for r in rows] == ["requested"]


def test_a3_a_terminal_permit_with_no_later_movement_stays_out():
    centre = _centre("CC803")
    permit = _permit(centre)
    _move(permit, FlightPermission.STATUS_DENIED, date(2026, 11, 10))

    assert collect_permits(CUTOFF) == []


# -- A4: la renovación en trámite -----------------------------------------------------


def _expiring(centre, days=10, folio_created=date(2026, 9, 1)):
    return _permit(
        centre,
        status="approved",
        start=date(2026, 9, 3) + timedelta(days=days),
        end=CUTOFF + timedelta(days=days),
        created=folio_created,
    )


def test_a4_the_rows_carry_the_folio_they_renew_and_the_chip_says_so():
    centre = _centre("CC804")
    old = _expiring(centre)
    renewal = _permit(centre, renews=old)

    payload, _missing = build(PERIOD, cutoff=CUTOFF)
    rows = {r["folio"]: r for r in payload["permits"]}
    row = _row(payload, "CC804")

    assert rows[renewal.internal_folio]["renews"] == old.internal_folio
    assert rows[old.internal_folio]["renews"] is None
    assert coverage_state(row) == "renewing"
    assert coverage_word("renewing") == "Renovación en trámite"
    assert violations(payload) == []


def test_a4_without_the_renewal_it_still_says_renew_now():
    centre = _centre("CC804")
    _expiring(centre)
    _permit(centre)  # una solicitud cualquiera, que no renueva nada

    payload, _missing = build(PERIOD, cutoff=CUTOFF)

    assert coverage_state(_row(payload, "CC804")) == "renew"


def test_a4_a_second_expiring_permit_without_renewal_keeps_renew_now():
    centre = _centre("CC804")
    old = _expiring(centre)
    _expiring(centre, days=12)
    _permit(centre, renews=old)

    payload, _missing = build(PERIOD, cutoff=CUTOFF)

    assert coverage_state(_row(payload, "CC804")) == "renew"


def test_a4_the_bar_counts_the_renewal_in_progress_as_critical_and_names_it():
    centre = _centre("CC804")
    _permit(centre, renews=_expiring(centre))
    payload, _missing = build(PERIOD, cutoff=CUTOFF)

    svg = coverage_bar(payload["cost_centres"], "t")

    assert "1 crítico: 0 sin habilitación, 1 con permiso a ≤30 d" in svg


# -- A5 / M4: aprobado que empieza después del corte ----------------------------------


def test_a5_an_approved_permit_that_starts_later_is_its_own_block_and_never_enables():
    centre = _centre("CC805")
    _permit(centre, status="approved", start=date(2026, 12, 5), end=date(2027, 3, 4))

    app = next(
        r
        for r in permit_status_by_cost_center(CUTOFF)
        if r["cost_center"].code == "CC805"
    )
    payload, _missing = build(PERIOD, cutoff=CUTOFF)
    row = _row(payload, "CC805")

    assert app["not_started"] == 1
    assert payload["kpis"]["permits_not_started"]["value"] == 1
    assert [u["valid_from"] for u in payload["upcoming_permits"]] == ["2026-12-05"]
    # No habilita ni cuenta en «X de N con permiso vigente».
    assert payload["permits"] == []
    assert payload["kpis"]["permits_in_force"]["value"] == 0
    assert payload["kpis"]["cost_centres_without_permit"]["value"] == 1
    assert row["permits_in_force"] == 0 and row["permits_not_started"] == 1
    assert row["next_start"] == "2026-12-05"
    assert permit_groups(payload)["upcoming"] == payload["upcoming_permits"]
    assert violations(payload) == []


def test_a5_the_coverage_tells_it_apart_from_no_authorisation():
    pending = _centre("CC805")
    nothing = _centre("CC806")
    _permit(pending, status="approved", start=date(2026, 12, 5), end=date(2027, 3, 4))

    payload, _missing = build(PERIOD, cutoff=CUTOFF)

    assert coverage_state(_row(payload, "CC805")) == "upcoming"
    assert coverage_state(_row(payload, nothing.code)) == "none"


def test_a5_a_broken_upcoming_block_trips_invariant_i8():
    centre = _centre("CC805")
    _permit(centre, status="approved", start=date(2026, 12, 5), end=date(2027, 3, 4))
    payload, _missing = build(PERIOD, cutoff=CUTOFF)

    payload["kpis"]["permits_not_started"]["value"] = 5

    assert [code for code, _data in violations(payload)] == ["I8"]


def test_a5_a_permit_that_started_before_the_cutoff_is_not_upcoming():
    centre = _centre("CC805")
    _permit(centre, status="approved", start=date(2026, 11, 1), end=date(2027, 1, 30))

    payload, _missing = build(PERIOD, cutoff=CUTOFF)

    assert payload["upcoming_permits"] == []
    assert payload["kpis"]["permits_in_force"]["value"] == 1


def test_m4_a_site_with_only_a_request_says_in_progress_not_no_authorisation():
    centre = _centre("CC806")
    _permit(centre)

    payload, _missing = build(PERIOD, cutoff=CUTOFF)

    assert coverage_state(_row(payload, "CC806")) == "awaiting"
    assert coverage_word("awaiting") == "En trámite"


# -- A6: el Total de «En trámite» suma lo que las filas muestran ----------------------


def test_a6_the_total_row_is_what_the_visible_rows_add_up_to():
    _centre("CC806")
    closed = _centre("CC807", contract_status=CostCenter.CONTRACT_CLOSED)
    _permit(closed)

    payload, _missing = build(PERIOD, cutoff=CUTOFF)
    rows_sum = sum(r["permits_awaiting"] for r in payload["cost_centres"])

    assert rows_sum == 0
    assert payload["kpis"]["permits_awaiting_operating"]["value"] == rows_sum
    # El total legal sigue contando la faena cerrada, y la línea «+ Sin operación» la
    # dibuja.
    assert payload["kpis"]["permits_awaiting"]["value"] == 1
    assert payload["outside_centres"][0]["permits_awaiting"] == 1
    assert violations(payload) == []


def test_a6_invariant_i4_compares_the_total_against_the_visible_rows():
    _centre("CC806")
    closed = _centre("CC807", contract_status=CostCenter.CONTRACT_CLOSED)
    _permit(closed)
    payload, _missing = build(PERIOD, cutoff=CUTOFF)

    payload["kpis"]["permits_awaiting_operating"]["value"] = 1

    assert [code for code, _data in violations(payload)] == ["I4"]


def test_a6_the_outside_line_is_drawn_for_a_request_only_centre(
    client, django_user_model
):
    from django.template.loader import render_to_string

    _centre("CC806")
    closed = _centre("CC807", contract_status=CostCenter.CONTRACT_CLOSED)
    _permit(closed)
    payload, _missing = build(PERIOD, cutoff=CUTOFF)

    html = render_to_string(
        "reporting/v2/_page4_coverage.html",
        {"payload": payload, "run": None, "coverage_section": "coverage_v2"},
    )

    assert "+ Sin operación:" in html
    assert "CC807" in html and "1 en trámite" in html


# -- A7: las misiones son de la faena del permiso -------------------------------------


def test_a7_a_mission_belongs_to_the_centre_of_the_permit_it_flew_under():
    home = _centre("CC808")
    site = _centre("CC809")
    pilot = Operator.objects.create(
        employee_id="P8",
        full_name="Operador Ficticio",
        cost_center=site,
        email="p8@test.com",
    )
    tail = Aircraft.objects.create(
        registration="RPA-8800",
        type="RPA",
        model="Modelo",
        manufacturer="Fab",
        cost_center=home,
    )
    permit = _permit(
        site,
        status="approved",
        start=date(2026, 11, 1),
        end=date(2027, 1, 31),
        created=date(2026, 10, 20),
    )
    FlightRecord.objects.create(
        permission=permit,
        actual_date=date(2026, 11, 15),
        departure_time=time(10),
        arrival_time=time(11),
        pilot=pilot,
        aircraft=tail,
    )
    window = (date(2026, 11, 10), CUTOFF)

    at_site = collect_mission_records(PERIOD, window, [site], None, False)
    at_home = collect_mission_records(PERIOD, window, [home], None, False)

    assert at_site["kpis"]["missions_flown"]["value"] == 1
    assert at_home["kpis"]["missions_flown"]["value"] is None


# -- A8: las solicitudes SIGO presentadas ---------------------------------------------


def test_a8_a_filed_request_without_a_permit_counts_as_in_progress():
    centre = _centre("CC810")
    _request(centre)

    payload, _missing = build(PERIOD, cutoff=CUTOFF)

    assert payload["kpis"]["permits_awaiting"]["value"] == 1
    assert payload["kpis"]["permits_awaiting_requests"]["value"] == 1
    assert _row(payload, "CC810")["permits_awaiting"] == 1
    assert coverage_state(_row(payload, "CC810")) == "awaiting"
    assert [f["cost_centre"] for f in payload["filed_requests"]] == ["CC810"]
    assert violations(payload) == []


def test_a8_a_prepared_request_does_not_count():
    _request(_centre("CC810"), status="prepared")

    payload, _missing = build(PERIOD, cutoff=CUTOFF)

    assert payload["kpis"]["permits_awaiting"]["value"] == 0
    assert payload["filed_requests"] == []


def test_a8_a_filed_request_linked_to_a_requested_permit_is_not_counted_twice():
    centre = _centre("CC810")
    permit = _permit(centre)
    _request(centre, flight_permission=permit)

    payload, _missing = build(PERIOD, cutoff=CUTOFF)

    assert payload["kpis"]["permits_awaiting"]["value"] == 1
    assert payload["filed_requests"] == []
    assert violations(payload) == []


def test_a8_a_filed_request_whose_permit_is_not_alive_still_counts():
    centre = _centre("CC810")
    dead = _permit(centre)
    _move(dead, FlightPermission.STATUS_DENIED, date(2026, 11, 10))
    _request(centre, flight_permission=dead)

    payload, _missing = build(PERIOD, cutoff=CUTOFF)

    assert payload["kpis"]["permits_awaiting"]["value"] == 1
    assert len(payload["filed_requests"]) == 1


def test_a8_the_request_status_is_the_one_it_had_at_the_cutoff():
    """Presentada antes del corte y cerrada después: al corte estaba en trámite."""
    centre = _centre("CC810")
    item = _request(centre, status="prepared")
    for new_status, day in (
        ("filed", date(2026, 11, 12)),
        ("closed", date(2026, 11, 28)),
    ):
        item.status = new_status
        item.save()
        last = FlightRequestHistory.objects.filter(request=item).order_by("-sequence")[
            0
        ]
        FlightRequestHistory.objects.filter(pk=last.pk).update(created_at=_aware(day))

    payload, _missing = build(PERIOD, cutoff=CUTOFF)

    assert payload["kpis"]["permits_awaiting"]["value"] == 1


def test_a8_a_filed_request_after_the_cutoff_does_not_exist_yet():
    centre = _centre("CC810")
    item = _request(centre, status="prepared")
    item.status = "filed"
    item.save()
    last = FlightRequestHistory.objects.filter(request=item).order_by("-sequence")[0]
    FlightRequestHistory.objects.filter(pk=last.pk).update(
        created_at=_aware(date(2026, 11, 28))
    )

    payload, _missing = build(PERIOD, cutoff=CUTOFF)

    assert payload["kpis"]["permits_awaiting"]["value"] == 0


# -- M6: el guardián contra el panel --------------------------------------------------


def test_m6_with_the_cutoff_today_the_report_matches_the_panel():
    """Con corte = hoy, el informe y el panel cuentan lo mismo.

    Equivalencia exacta: `kpis.permits_awaiting` del informe = `permit_counts["awaiting"]`
    (permisos solicitados) + las solicitudes SIGO **presentadas** del panel (las que
    «esperan respuesta»), siempre que ninguna tenga vinculado un permiso vivo (esas ya
    son una fila de permiso y el informe no las cuenta dos veces). Y los aprobados aún
    no vigentes del panel (`not_started`) son el bloque `upcoming_permits`.
    """
    today = timezone.localdate()
    period = today.replace(day=1)
    centre = _centre("CC811")
    other = _centre("CC812")
    created = today - timedelta(days=40)
    _permit(centre, created=created)
    _permit(
        other,
        created=created,
        start=today + timedelta(days=40),
        end=today + timedelta(days=100),
    )
    _permit(
        centre,
        status="approved",
        start=today + timedelta(days=9),
        end=today + timedelta(days=99),
        created=created,
    )
    _permit(
        other,
        status="approved",
        start=today - timedelta(days=9),
        end=today + timedelta(days=99),
        created=created,
    )
    item = _request(centre, filed_on=today - timedelta(days=2))
    FlightRequest.objects.filter(pk=item.pk).update(created_at=_aware(created))
    _request(other, status="prepared")

    counts = permit_counts(today)
    panel_filed = FlightRequest.objects.filter(
        is_active=True, status=FlightRequest.STATUS_FILED
    ).count()
    payload, _missing = build(period, cutoff=today)

    assert (
        payload["kpis"]["permits_awaiting"]["value"] == counts["awaiting"] + panel_filed
    )
    assert payload["kpis"]["permits_awaiting"]["value"] == 3
    assert payload["kpis"]["permits_not_started"]["value"] == counts["not_started"] == 1
    assert payload["kpis"]["permits_in_force"]["value"] == counts["in_force"] == 1
    assert violations(payload) == []


# -- M2 / M3: la sección 5 -------------------------------------------------------------


def test_m2_the_review_total_is_the_denominator_of_reviewed_in_24h():
    from apps.reporting.manual_case import centre as site_of
    from apps.reporting.manual_case import doc_types, document, at

    types = doc_types()
    site = site_of("CC901")
    from apps.compliance.models import MissionReview

    for mission, reviewed in ((date(2026, 11, 12), True), (date(2026, 11, 16), False)):
        document(types["flight-log"], site, issue=mission, loaded=at(mission))
        review = MissionReview.objects.get(document__issue_date=mission)
        if reviewed:
            review.mark("reviewed", None, when=_aware(mission + timedelta(days=1), 9))

    payload, missing = build(PERIOD, cutoff=date(2026, 11, 30))
    kpis = payload["manual"]["missions"]["kpis"]

    assert kpis["reviewed_within_24h"]["value"] == 1
    assert kpis["reviews_total"]["value"] == 2


def test_m2_without_reviews_the_total_is_pending_not_zero():
    from apps.reporting.manual_case import centre as site_of

    site_of("CC901")
    payload, missing = build(PERIOD, cutoff=date(2026, 11, 30))

    assert payload["manual"]["missions"]["kpis"]["reviews_total"]["value"] is None
    assert "manual.missions.kpis.reviews_total" in missing


def test_m2_the_sheet_says_x_of_n(client):
    import re

    from apps.reporting.manual_case import make_manual_case
    from apps.reporting.test_lv445_manual_render import _page, _user

    make_manual_case()
    payload = build(PERIOD, cutoff=date(2026, 11, 30))[0]
    payload["manual"]["missions"]["kpis"]["reviewed_within_24h"]["value"] = 1
    payload["manual"]["missions"]["kpis"]["reviews_total"]["value"] = 4
    client.force_login(_user("reader459", "view_reportrun"))

    html = " ".join(_page(client, payload).content.decode().split())

    assert re.search(r"1 de 4 revisados en 24 h", re.sub(r"<[^>]+>", "", html))


def test_m3_maintenance_is_limited_to_the_report_fleet():
    from apps.maintenance.models import MaintenanceRecord
    from apps.reporting.manual_case import aircraft, born
    from apps.reporting.manual_case import centre as site_of

    site = site_of("CC901")
    mine = aircraft("RPA-9001", site)
    retired = aircraft("RPA-9002", site)
    Aircraft.objects.filter(pk=retired.pk).update(status="retired")
    window = (date(2026, 11, 10), date(2026, 11, 30))
    for tail in (mine, retired):
        born(
            MaintenanceRecord.objects.create(
                aircraft=tail,
                maintenance_type="preventive",
                description="x",
                status="completed",
                completed_date=date(2026, 11, 15),
            )
        )
        born(
            MaintenanceRecord.objects.create(
                aircraft=tail,
                maintenance_type="preventive",
                description="x",
                status="pending",
            )
        )
    fleet = [(mine.pk, "RPA-9001")]

    scoped = collect_maintenance(window, date(2026, 11, 30), fleet)["kpis"]
    unscoped = collect_maintenance(window, date(2026, 11, 30))["kpis"]

    assert scoped["completed_in_window"]["value"] == 1
    assert scoped["open_at_cutoff"]["value"] == 1
    assert unscoped["completed_in_window"]["value"] == 2


def test_m3_an_early_cutoff_ignores_what_was_created_after_it():
    from apps.maintenance.models import MaintenanceRecord
    from apps.reporting.manual_case import aircraft
    from apps.reporting.manual_case import centre as site_of

    site = site_of("CC901")
    tail = aircraft("RPA-9001", site)
    fleet = [(tail.pk, "RPA-9001")]
    row = MaintenanceRecord.objects.create(
        aircraft=tail,
        maintenance_type="preventive",
        description="x",
        status="completed",
        completed_date=date(2026, 11, 15),
    )
    MaintenanceRecord.objects.filter(pk=row.pk).update(
        created_at=_aware(date(2026, 11, 20))
    )
    window = (date(2026, 11, 10), date(2026, 11, 18))

    early = collect_maintenance(window, date(2026, 11, 18), fleet, True)["kpis"]
    closing = collect_maintenance(window, date(2026, 11, 18), fleet, False)["kpis"]

    assert early["completed_in_window"]["value"] == 0
    assert closing["completed_in_window"]["value"] == 1
