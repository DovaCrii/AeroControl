"""LV-235: el Dato Ejecutivo, generado en vez de llenado a mano.

Pedido del usuario con los dos documentos base a la vista: *"el otro lo genero de
forma automática de manera diferente, yo lo voy llenando"*.

Lo que estos tests protegen, por orden de gravedad:

1. **Que sea el mismo payload que el informe de cinco páginas.** Dos
   recolecciones separadas es cómo la hoja de una página y el informe empiezan a
   decir cifras distintas del mismo mes — lo que `LV-188` costó.
2. **Que el hueco se vea como hueco**, nunca como cero.
3. **Que las acciones sean lo único manual**, y que una fila escrita a medias no
   se guarde: una acción sin responsable es una acción que nadie hace.
"""

from datetime import date, timedelta

import pytest
from django.contrib.auth.models import Permission, User
from django.urls import reverse

from apps.compliance.models import NonConformity
from apps.operations.models import FlightPermission
from apps.registry.models import CostCenter
from apps.reporting.builder import build
from apps.reporting.models import ReportRun

BRIEF = "monthly-report-brief"


@pytest.fixture
def reader(db):
    user = User.objects.create_user("reader", password="x")
    user.user_permissions.add(
        Permission.objects.get(
            codename="view_reportrun", content_type__app_label="reporting"
        )
    )
    return user


@pytest.fixture
def site(db):
    return CostCenter.objects.create(code="CC738", name="MLP", operates_flights=True)


class TestItIsTheSamePayloadAsTheFullReport:
    @pytest.mark.django_db
    def test_the_figures_come_from_the_same_place(self, client, reader, site):
        """No es un informe aparte: es otra salida del mismo dato. Si cada uno
        recolectara por su cuenta, la hoja de una página y las cinco podrían
        decir cosas distintas del mismo mes."""
        client.force_login(reader)

        brief = client.get(reverse(BRIEF), {"period": "2026-08"}).content.decode()
        full = client.get(
            reverse("monthly-report"), {"period": "2026-08"}
        ).content.decode()

        assert "JEJ-GTE-CT-INF-RPA-2026-08" in brief
        assert "JEJ-GTE-CT-INF-RPA-2026-08" in full

    @pytest.mark.django_db
    def test_it_is_gated_like_the_report(self, client, db):
        """Nombra las mismas faenas y su habilitación, así que pide el mismo
        permiso de lectura. Un `LoginRequiredMixin` a secas sería el defecto que
        `LV-191` dejó documentado."""
        outsider = User.objects.create_user("outsider", password="x")
        client.force_login(outsider)

        assert client.get(reverse(BRIEF)).status_code == 403

    @pytest.mark.django_db
    def test_a_frozen_period_draws_its_payload(self, client, reader, site):
        """Y no la base de hoy: es lo mismo que hace el informe largo, y lo que
        permite que agosto siga diciendo en diciembre lo que decía."""
        run = ReportRun.objects.create(
            period=date(2026, 8, 1),
            generated_by="test",
            payload={"meta": {"code": "CONGELADO-08"}, "kpis": {}, "cost_centres": []},
        )
        client.force_login(reader)

        body = client.get(reverse(BRIEF), {"period": "2026-08"}).content.decode()

        assert "CONGELADO-08" in body
        assert run.period.isoformat() == "2026-08-01"


class TestTheSixIndicators:
    @pytest.mark.django_db
    def test_the_incident_counter_exists_and_counts_the_period(self, db, site):
        """El indicador que los dos documentos piden y que el payload no
        producía: el informe emitido lo llevaba escrito a mano."""
        NonConformity.objects.create(
            title="Aterrizaje forzoso",
            source=NonConformity.SOURCE_INCIDENT,
            cost_center=site,
            detected_on=date(2026, 8, 12),
            description="x",
        )

        payload, _missing = build(date(2026, 8, 1))

        assert payload["kpis"]["incidents"]["value"] == 1

    @pytest.mark.django_db
    def test_a_quality_finding_is_not_an_incident(self, db, site):
        """⚠️ Sólo `source="incident"`. Un re-vuelo o un entregable rechazado son
        hallazgos de calidad; sumarlos presentaría ante la DGAC como eventos
        notificables algo que no lo es."""
        NonConformity.objects.create(
            title="Re-vuelo",
            source=NonConformity.SOURCE_REFLIGHT,
            cost_center=site,
            detected_on=date(2026, 8, 12),
            description="x",
        )

        payload, _missing = build(date(2026, 8, 1))

        assert payload["kpis"]["incidents"]["value"] == 0

    @pytest.mark.django_db
    def test_an_incident_of_another_month_does_not_count(self, db, site):
        NonConformity.objects.create(
            title="De julio",
            source=NonConformity.SOURCE_INCIDENT,
            cost_center=site,
            detected_on=date(2026, 7, 30),
            description="x",
        )

        payload, _missing = build(date(2026, 8, 1))

        assert payload["kpis"]["incidents"]["value"] == 0

    @pytest.mark.django_db
    def test_it_counts_by_detection_and_not_by_load(self, db, site):
        """Un evento del 20 de agosto cargado el 2 de septiembre pertenece a
        agosto, que es de lo que el informe habla."""
        NonConformity.objects.create(
            title="Detectado en agosto",
            source=NonConformity.SOURCE_INCIDENT,
            cost_center=site,
            detected_on=date(2026, 8, 20),
            description="x",
        )

        payload, _missing = build(date(2026, 8, 1))

        assert payload["kpis"]["incidents"]["value"] == 1


class TestTheIncidentSectionIsComputedToo:
    @pytest.mark.django_db
    def test_it_lists_the_event_with_its_dgac_report(self, db, site):
        """La plantilla en papel pedía escribir *"detalle del evento, fecha, CC,
        aeronave y estado del reporte a la DGAC"*. `NonConformity` ya lo guarda,
        incluido el folio — que para un evento notificable **es** la evidencia."""
        NonConformity.objects.create(
            title="Aterrizaje forzoso",
            source=NonConformity.SOURCE_INCIDENT,
            cost_center=site,
            detected_on=date(2026, 8, 12),
            description="x",
            reported_to_dgac_at=date(2026, 8, 13),
            dgac_report_reference="DGAC-1234",
        )

        payload, _missing = build(date(2026, 8, 1))
        row = payload["incidents"][0]

        assert row["cost_centre"] == "CC738"
        assert row["reported_to_dgac"] == "2026-08-13"
        assert row["dgac_reference"] == "DGAC-1234"

    @pytest.mark.django_db
    def test_not_reported_is_none_and_not_an_empty_string(self, db, site):
        """No reportado y reportado sin folio son dos cosas distintas."""
        NonConformity.objects.create(
            title="Sin reportar",
            source=NonConformity.SOURCE_INCIDENT,
            cost_center=site,
            detected_on=date(2026, 8, 12),
            description="x",
        )

        payload, _missing = build(date(2026, 8, 1))

        assert payload["incidents"][0]["reported_to_dgac"] is None


class TestTheActionsAreTheOnlyManualPart:
    @pytest.mark.django_db
    def test_an_action_needs_a_description_and_an_owner(self, db):
        """Una acción sin responsable es una acción que nadie hace. La plantilla
        en papel dejaba pasar las tres filas vacías."""
        from django.core.exceptions import ValidationError

        run = ReportRun(
            period=date(2026, 8, 1),
            generated_by="test",
            actions=[{"action": "Renovar CC684", "owner": "", "due": "15-09"}],
        )

        with pytest.raises(ValidationError):
            run.full_clean()

    @pytest.mark.django_db
    def test_a_deadline_is_optional(self, db):
        """Hay acciones sin fecha comprometida todavía; sin responsable no."""
        run = ReportRun(
            period=date(2026, 8, 1),
            generated_by="test",
            actions=[{"action": "Renovar CC684", "owner": "ADC", "due": ""}],
        )

        run.full_clean()

    @pytest.mark.django_db
    def test_a_row_with_another_shape_is_refused(self, db):
        """Un `JSONField` acepta cualquier cosa, y una fila mal formada no
        revienta al guardar: revienta al dibujar la hoja que se lleva a la
        reunión."""
        from django.core.exceptions import ValidationError

        run = ReportRun(
            period=date(2026, 8, 1),
            generated_by="test",
            actions=[{"accion": "Renovar", "quien": "ADC"}],
        )

        with pytest.raises(ValidationError):
            run.full_clean()

    @pytest.mark.django_db
    def test_they_reach_the_sheet(self, client, reader, site):
        ReportRun.objects.create(
            period=date(2026, 8, 1),
            generated_by="test",
            payload={"meta": {"code": "X"}, "kpis": {}, "cost_centres": []},
            actions=[
                {"action": "Renovar JEJ-2026-011", "owner": "ADC", "due": "15-09-2026"}
            ],
        )
        client.force_login(reader)

        body = client.get(reverse(BRIEF), {"period": "2026-08"}).content.decode()

        assert "Renovar JEJ-2026-011" in body
        assert "ADC" in body

    @pytest.mark.django_db
    def test_without_a_frozen_report_it_says_where_they_go(self, client, reader, site):
        """En vez de dibujar una tabla vacía con tres filas numeradas, como la
        plantilla en papel."""
        client.force_login(reader)

        body = client.get(reverse(BRIEF), {"period": "2026-08"}).content.decode()

        assert "todavía no lo está" in body


class TestThePlanPageMovesWithThePeriod:
    """⚠️ **La observación central del usuario, y era exacta para esta página.**

    Textual, mirando la página 5: *"el actual es estático, sólo cambia la fecha,
    lo cual lo vuelve inútil"*. Medido: 124 líneas de plantilla con **dos**
    interpolaciones, y las dos eran la firma. Las cuatro fases llevaban sus meses
    escritos a mano y la primera tenía `rpt-fase-now` fija, así que en enero de
    2027 el informe iba a seguir diciendo *"FASE 0 · Sep 2026"* como fase en
    curso — un plan vencido impreso como vigente.
    """

    @pytest.mark.django_db
    def test_the_current_phase_follows_the_period(self, db):
        assert [
            phase["state"] for phase in build(date(2026, 10, 1))[0]["plan"]["phases"]
        ] == ["done", "current", "pending", "pending"]

    @pytest.mark.django_db
    def test_and_a_different_period_gives_a_different_one(self, db):
        """La otra mitad, o el test anterior pasaría con las fases fijas en otro
        orden."""
        assert [
            phase["state"] for phase in build(date(2026, 12, 1))[0]["plan"]["phases"]
        ] == ["done", "done", "done", "current"]

    @pytest.mark.django_db
    def test_after_the_last_phase_it_says_the_plan_ended(self, db):
        """El caso que el plan escrito a mano no tenía. Decirlo es mejor que
        dejar la primera fase pintada como actual para siempre."""
        plan = build(date(2027, 3, 1))[0]["plan"]

        assert plan["concluded"] is True
        assert not [p for p in plan["phases"] if p["state"] == "current"]

    @pytest.mark.django_db
    def test_before_the_first_phase_it_says_so_too(self, db):
        plan = build(date(2026, 7, 1))[0]["plan"]

        assert plan["not_started"] is True
        assert [p["state"] for p in plan["phases"]] == ["pending"] * 4

    @pytest.mark.django_db
    def test_the_state_is_against_the_period_and_not_against_today(self, db):
        """Reimprimir el informe de agosto en diciembre tiene que devolver la
        página que agosto vio, no la de diciembre. Es la misma regla que el corte
        y la razón de que `collect_plan` reciba el período."""
        august = build(date(2026, 8, 1))[0]["plan"]

        # Agosto es anterior a la primera fase, pase lo que pase con el reloj.
        assert august["not_started"] is True

    @pytest.mark.django_db
    def test_the_page_no_longer_hardcodes_the_months(self, db):
        """El guardián de la fila: si alguien vuelve a escribir los meses en la
        plantilla, esto lo dice."""
        from pathlib import Path

        from django.conf import settings

        page = (
            Path(settings.BASE_DIR) / "templates" / "reporting" / "_page5_plan.html"
        ).read_text(encoding="utf-8")
        from apps.core.testing import without_template_comments

        markup = without_template_comments(page)

        assert "Sep 2026" not in markup
        assert "Dic 2026" not in markup
        assert "payload.plan.phases" in markup


class TestWhatTheSheetShowsOfThePermits:
    @pytest.mark.django_db
    def test_awaiting_uses_the_status_at_the_cutoff(self, client, reader, site):
        """`LV-233`: un permiso aprobado en septiembre sigue apareciendo como
        trámite en el informe de agosto, que es lo que ese mes decía."""
        today = date(2026, 8, 15)
        FlightPermission.objects.create(
            cost_center=site,
            purpose="photogrammetry",
            status=FlightPermission.STATUS_REQUESTED,
            location="Site",
            area_type="unpopulated",
            valid_from=today,
            valid_until=today + timedelta(days=60),
        )
        client.force_login(reader)

        body = client.get(reverse(BRIEF), {"period": "2026-08"}).content.decode()

        assert "Solicitudes en trámite" in body
