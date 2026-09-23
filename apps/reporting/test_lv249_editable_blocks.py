"""LV-249: los bloques del informe, editables desde la aplicación.

Pedido del usuario el 2026-09-23: *"tomar otras plantillas más fáciles de
modificar"*. Eligió **bloques editables en la app** por sobre exportar a Word. La
portada vivía en `builder.collect_meta`, las fases en la constante `PLAN_PHASES`
—con los meses de 2026 escritos— y la matriz de exigibilidad en la plantilla, con
**SEP–DIC a mano**: en enero iba a imprimirse un plan vencido como vigente.

⚠️ **La regla que estos tests existen para sostener**: un informe congelado no
cambia cuando alguien edita los bloques. Se leen al congelar y se copian al
payload; editar hoy cambia la vista previa y lo que se congele desde ahora.
"""

from datetime import date

import pytest
from django.contrib.auth.models import Permission, User
from django.urls import reverse

from apps.reporting.builder import FACTORY_COVER, build
from apps.reporting.models import ExigibilityRow, PlanPhase, ReportRun, ReportTemplate

CLOSED_MONTH = date(2026, 8, 1)


def _user_with(*codenames):
    user = User.objects.create_user("lv249", password="pw")
    for codename in codenames:
        user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="reporting", codename=codename
            )
        )
    return user


@pytest.mark.django_db
class TestTheSeedReproducesTheOldReport:
    """El primer informe después del despliegue tiene que salir idéntico."""

    def test_the_cover_matches_what_the_code_had(self):
        template = ReportTemplate.current()

        assert template is not None
        assert {field: getattr(template, field) for field in FACTORY_COVER} == (
            FACTORY_COVER
        )

    def test_the_four_phases_are_there_in_their_months(self):
        months = [
            f"{phase.month:%Y-%m}" for phase in ReportTemplate.current().active_phases()
        ]

        assert months == ["2026-09", "2026-10", "2026-11", "2026-12"]

    def test_the_matrix_keeps_its_levels(self):
        payload, _missing = build(date(2026, 9, 1), cutoff=date(2026, 9, 30))
        matrix = payload["plan"]["matrix"]

        assert matrix["columns"] == ["SEP", "OCT", "NOV", "DIC"]
        assert [row["cells"] for row in matrix["rows"]] == [
            ["due", "due", "due", "due"],
            ["info", "due", "due", "due"],
            ["na", "na", "info", "due"],
            ["na", "na", "info", "due"],
        ]


@pytest.mark.django_db
class TestEditingChangesThePreview:
    def test_the_cover_is_read_from_the_template(self):
        template = ReportTemplate.current()
        template.scope = "Alcance nuevo"
        template.save()

        payload, _missing = build(date(2026, 9, 1), cutoff=date(2026, 9, 30))

        assert payload["meta"]["scope"] == "Alcance nuevo"

    def test_a_new_phase_adds_a_matrix_column(self):
        """⚠️ **Las columnas son las fases.** El SEP–DIC escrito a mano era lo que
        iba a dejar la matriz vieja en enero; ahora una fase de enero trae su
        columna, y un mes sin nivel se dibuja «No aplica»."""
        template = ReportTemplate.current()
        PlanPhase.objects.create(
            template=template,
            month=date(2027, 1, 15),
            title="Siguiente ciclo",
            text="…",
            close="…",
        )

        payload, _missing = build(date(2027, 1, 1), cutoff=date(2027, 1, 31))
        matrix = payload["plan"]["matrix"]

        assert matrix["columns"][-1] == "ENE"
        assert all(row["cells"][-1] == "na" for row in matrix["rows"])

    def test_a_phase_month_is_stored_as_the_whole_month(self):
        phase = PlanPhase.objects.create(
            template=ReportTemplate.current(),
            month=date(2027, 2, 17),
            title="t",
            text="t",
            close="t",
        )

        assert phase.month == date(2027, 2, 1)


@pytest.mark.django_db
class TestAFrozenReportDoesNotMove:
    def test_editing_the_cover_leaves_a_frozen_report_alone(self):
        """La regla que no se negocia. Se congela agosto, se edita la portada, y el
        informe de agosto sigue diciendo lo que dijo."""
        run, _created = ReportRun.freeze(CLOSED_MONTH, generated_by="lv249")
        before = run.payload["meta"]["scope"]

        template = ReportTemplate.current()
        template.scope = "Un alcance distinto"
        template.save()
        run.refresh_from_db()

        assert run.payload["meta"]["scope"] == before

    def test_a_report_frozen_before_this_change_still_draws_its_matrix(
        self, client, admin_user
    ):
        """⚠️ Un informe congelado antes de `LV-249` no trae `matrix` en su payload:
        la matriz vivía en la plantilla. La plantilla conserva el bloque fijo para
        ese caso; si no, esos informes perderían su matriz al volver a abrirlos."""
        run, _created = ReportRun.freeze(CLOSED_MONTH, generated_by="lv249")
        payload = dict(run.payload)
        plan = dict(payload["plan"])
        plan.pop("matrix", None)
        plan.pop("lede", None)
        payload["plan"] = plan
        ReportRun.objects.filter(pk=run.pk).update(payload=payload)
        client.force_login(admin_user)

        content = client.get(
            reverse("monthly-report"), {"period": f"{CLOSED_MONTH:%Y-%m}"}
        ).content.decode()

        assert "<div>SEP</div><div>OCT</div><div>NOV</div><div>DIC</div>" in content
        assert "Cuatro fases de un mes." in content


@pytest.mark.django_db
class TestTheLevelsAreGuarded:
    def test_an_unknown_level_is_rejected_by_the_model(self):
        """En el modelo y no sólo en el formulario: el admin y una migración de
        datos también escriben acá, y un nivel mal escrito no falla al guardar — se
        dibuja como una celda sin color."""
        from django.core.exceptions import ValidationError

        row = ExigibilityRow(
            template=ReportTemplate.current(),
            label="x",
            levels={"2026-09": "exigible"},
        )

        with pytest.raises(ValidationError):
            row.full_clean()


@pytest.mark.django_db
class TestTheScreen:
    def test_without_the_permission_it_is_forbidden(self, client):
        client.force_login(_user_with("view_reportrun"))

        response = client.get(reverse("monthly-report-template"))

        assert response.status_code == 403

    def test_with_it_the_screen_opens(self, client):
        client.force_login(_user_with("view_reportrun", "change_reportrun"))

        response = client.get(reverse("monthly-report-template"))

        assert response.status_code == 200
        assert "Textos del informe" in response.content.decode()

    def test_saving_edits_the_cover_and_archives_a_removed_phase(
        self, client, admin_user
    ):
        """Un envío completo: la portada cambia, y la fase marcada para quitar se
        **archiva** —`AGENTS.md`: nunca se borran filas— en vez de desaparecer."""
        client.force_login(admin_user)
        response = client.get(reverse("monthly-report-template"))
        context = response.context
        data = {}
        for form in [context["cover_form"]]:
            for name, field in form.fields.items():
                data[form.add_prefix(name)] = form.initial.get(name, "")
        data["cover-scope"] = "Alcance editado"
        for formset in (context["phase_formset"], context["row_formset"]):
            management = formset.management_form
            for name in management.fields:
                data[management.add_prefix(name)] = management.initial.get(name, 0)
            for form in formset.forms:
                for name, field in form.fields.items():
                    value = form.initial.get(name, field.initial)
                    if name == "month" and value:
                        value = f"{value:%Y-%m}"
                    if hasattr(value, "pk"):
                        value = value.pk
                    if value is None or value is False:
                        continue
                    data[form.add_prefix(name)] = value
        first_phase = context["phase_formset"].forms[0]
        data[first_phase.add_prefix("DELETE")] = "on"

        response = client.post(reverse("monthly-report-template"), data)

        assert response.status_code == 302, response.context and [
            f.errors for f in response.context["phase_formset"]
        ]
        template = ReportTemplate.current()
        assert template.scope == "Alcance editado"
        archived = PlanPhase.objects.get(pk=first_phase.instance.pk)
        assert archived.is_active is False
        assert template.active_phases().count() == 3
