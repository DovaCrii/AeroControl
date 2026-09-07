"""`LV-227`: la narrativa del informe, escrita dentro de la aplicación.

Pedido del usuario: *"ver una opción del template subido dentro de la app, poder
modificarlo y que respete cambios"*, reafirmado al preguntar por herramientas de
edición.

Lo que estos tests protegen, por orden de gravedad:

1. **Que un informe aprobado no se pueda reescribir.** Es el documento que se
   envió: editarlo dejaría a la DGAC con una copia que ya no existe de este
   lado. Una corrección nace como revisión siguiente.
2. **Que esta pantalla no sea un camino a las cifras.** Se edita la redacción;
   los números salen de la base. Si un POST pudiera tocar `payload` o `status`,
   el informe dejaría de poder afirmar de dónde sale cada cifra — la garantía
   que lo hace firmable.
3. **Que sin narrativa escrita el informe diga "pendiente" y no "no hay".** Un
   resumen ejecutivo sin hallazgos afirmaría que el período no tuvo ninguno.
"""

from datetime import date

import pytest
from django.contrib.auth.models import Permission, User
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.registry.models import CostCenter
from apps.reporting.forms import FindingFormSet, PeriodNoteForm
from apps.reporting.models import ReportRun

PERIOD = date(2026, 8, 1)


def _user(name, *codenames):
    user = User.objects.create_user(name, password="x")
    for codename in codenames:
        user.user_permissions.add(
            Permission.objects.get(
                codename=codename, content_type__app_label="reporting"
            )
        )
    return user


@pytest.fixture
def writer(db):
    return _user("writer", "view_reportrun", "change_reportrun", "add_reportrun")


@pytest.fixture
def reader(db):
    return _user("reader", "view_reportrun")


@pytest.fixture
def site(db):
    return CostCenter.objects.create(code="CC738", name="MLP", operates_flights=True)


@pytest.fixture
def draft(db):
    return ReportRun.objects.create(
        period=PERIOD,
        generated_by="cron",
        payload={
            "meta": {"code": "JEJ-GTE-CT-INF-RPA-2026-08", "cutoff": "2026-08-31"}
        },
    )


def _post(count=1, actions=0, **overrides):
    data = {
        "findings-TOTAL_FORMS": str(count),
        "findings-INITIAL_FORMS": "0",
        "findings-MIN_NUM_FORMS": "0",
        "findings-MAX_NUM_FORMS": "8",
        # LV-235: la pantalla lleva ahora una segunda sección —las acciones del
        # Dato Ejecutivo— y su `management_form` viaja siempre, aunque no se
        # escriba ninguna. Sin él, Django rechaza el envío entero: es lo que la
        # plantilla dibuja, así que un `POST` sin esto no reproduce el
        # formulario real.
        "actions-TOTAL_FORMS": str(actions),
        "actions-INITIAL_FORMS": "0",
        "actions-MIN_NUM_FORMS": "0",
        "actions-MAX_NUM_FORMS": "6",
        "period_note": "",
    }
    data.update(overrides)
    return data


def _finding(
    index, severity="critical", title="Cobertura parcial", text="Siete faenas."
):
    return {
        f"findings-{index}-severity": severity,
        f"findings-{index}-title": title,
        f"findings-{index}-text": text,
    }


class TestOnlyAWriterWrites:
    @pytest.mark.django_db
    def test_a_reader_cannot_open_the_form(self, client, reader, draft):
        client.force_login(reader)

        assert (
            client.get(reverse("monthly-report-narrative", args=[draft.pk])).status_code
            == 403
        )

    @pytest.mark.django_db
    def test_a_reader_cannot_freeze_a_draft(self, client, reader, site):
        client.force_login(reader)

        response = client.post(reverse("monthly-report-draft"), {"period": "2026-08"})

        assert response.status_code == 403
        assert not ReportRun.objects.exists()

    @pytest.mark.django_db
    def test_the_writer_can(self, client, writer, draft):
        client.force_login(writer)

        assert (
            client.get(reverse("monthly-report-narrative", args=[draft.pk])).status_code
            == 200
        )


class TestAnApprovedReportIsNotRewritten:
    @pytest.mark.django_db
    def test_the_post_is_refused(self, client, writer, draft):
        """**El test que más importa de este archivo.**

        Un informe aprobado es el que se envió. Reescribirlo dejaría a la DGAC
        con una copia que ya no existe de este lado, y sin ruido: la pantalla se
        vería igual.
        """
        draft.status = ReportRun.STATUS_APPROVED
        draft.save()
        client.force_login(writer)

        client.post(
            reverse("monthly-report-narrative", args=[draft.pk]),
            _post(**_finding(0)),
        )

        draft.refresh_from_db()
        assert draft.findings == []

    @pytest.mark.django_db
    def test_it_leans_on_the_model_property_and_not_a_second_condition(self):
        """`is_editable` ya existía y es la única definición.

        Una condición nueva en la vista podría desviarse de ella, y entonces la
        pantalla y el modelo dirían cosas distintas sobre el mismo informe.
        """
        run = ReportRun(status=ReportRun.STATUS_SUPERSEDED)

        assert not run.is_editable


class TestTheNarrativeIsSavedAndDrawn:
    @pytest.mark.django_db
    def test_a_finding_reaches_the_report(self, client, writer, draft, site):
        client.force_login(writer)

        client.post(
            reverse("monthly-report-narrative", args=[draft.pk]),
            _post(
                period_note="La vigencia otorgada no es uniforme.",
                **_finding(0, title="Vencimiento inminente", text="JEJ-2026-011."),
            ),
        )

        draft.refresh_from_db()
        assert draft.findings == [
            {
                "severity": "critical",
                "title": "Vencimiento inminente",
                "text": "JEJ-2026-011.",
            }
        ]
        assert draft.period_note == "La vigencia otorgada no es uniforme."

        body = client.get(
            reverse("monthly-report"), {"period": "2026-08"}
        ).content.decode()
        assert "Vencimiento inminente" in body
        assert "La vigencia otorgada no es uniforme." in body

    @pytest.mark.django_db
    def test_without_a_narrative_the_report_says_pending_not_none(
        self, client, reader, draft, site
    ):
        """Un resumen ejecutivo sin hallazgos afirmaría que el período no tuvo
        ninguno, que es lo contrario de "todavía nadie los redactó"."""
        client.force_login(reader)

        body = client.get(
            reverse("monthly-report"), {"period": "2026-08"}
        ).content.decode()

        assert "rpt-pending-block" in body
        assert "LV-227" in body


class TestThisScreenIsNotAWayIntoTheFigures:
    def test_the_form_exposes_the_narrative_and_nothing_else(self):
        """**La afirmación directa, y la que muerde de inmediato.**

        Se comprueba acá y no sólo por el POST de abajo porque la prueba de
        extremo a extremo puede pasar por una razón vecina: con `"__all__"` el
        formulario pide además `period`, `revision`, `generated_by`, `status` y
        `completeness`, así que un POST que no los traiga sale inválido y no
        guarda nada — verde por el camino equivocado. Comprobado dejando el
        `"__all__"` puesto: este test cae y aquél no.
        """
        assert set(PeriodNoteForm().fields) == {"period_note"}

    @pytest.mark.django_db
    def test_extra_keys_in_the_post_are_ignored(self, client, writer, draft):
        """Las claves de más no llegan a la fila, y la narrativa sí.

        ⚠️ **Este test NO es el que protege del `"__all__"`**, y conviene
        decirlo para que nadie se apoye en él: con `"__all__"` puesto sigue
        verde, porque el formulario pediría además `is_active` y el POST no lo
        trae, así que sale inválido y no guarda nada — verde sin haber medido la
        filtración. Comprobado dejando el `"__all__"`. El guardián real es el
        test de arriba, que afirma sobre los campos declarados. Éste cubre la
        otra mitad: que la vista guarde lo que debe y descarte el resto.
        """
        client.force_login(writer)

        client.post(
            reverse("monthly-report-narrative", args=[draft.pk]),
            _post(
                period="2026-08-01",
                revision="0",
                generated_by="cron",
                completeness=ReportRun.COMPLETENESS_OK,
                status=ReportRun.STATUS_APPROVED,
                approved_by="quien sea",
                payload='{"kpis": {"permits_in_force": {"value": 99}}}',
                **_finding(0),
            ),
        )

        draft.refresh_from_db()
        assert draft.findings  # el POST sí fue válido: la narrativa se guardó
        assert draft.status == ReportRun.STATUS_DRAFT
        assert draft.approved_by == ""
        assert draft.payload["meta"]["code"] == "JEJ-GTE-CT-INF-RPA-2026-08"


class TestTheShapeOfAFindingIsGuarded:
    @pytest.mark.django_db
    def test_the_model_rejects_a_malformed_list(self):
        """El formulario no es el único camino a esta columna.

        El admin, un `loaddata` y una corrida de datos escriben igual, y un
        `JSONField` acepta cualquier cosa. Una lista mal formada no revienta al
        guardar: revienta al renderizar el informe.
        """
        run = ReportRun(period=PERIOD, generated_by="x", findings=["texto suelto"])

        with pytest.raises(ValidationError):
            run.clean()

    @pytest.mark.django_db
    def test_the_model_rejects_an_unknown_severity(self):
        run = ReportRun(
            period=PERIOD,
            generated_by="x",
            findings=[{"severity": "fucsia", "title": "T", "text": "X"}],
        )

        with pytest.raises(ValidationError):
            run.clean()

    def test_a_gap_between_two_findings_is_refused(self):
        """Un recuadro en blanco en medio de la página 2 de un documento que va
        a la autoridad. Se rechaza en vez de compactarlo: compactar cambiaría el
        orden que el redactor ve, y ese orden es suyo."""
        formset = FindingFormSet(
            _post(count=3, **{**_finding(0), **_finding(2)}), prefix="findings"
        )

        assert not formset.is_valid()

    def test_two_findings_in_a_row_are_fine(self):
        formset = FindingFormSet(
            _post(count=2, **{**_finding(0), **_finding(1, severity="warning")}),
            prefix="findings",
        )

        assert formset.is_valid()
        assert [entry["severity"] for entry in formset.entries] == [
            "critical",
            "warning",
        ]


class TestFreezingTheDraft:
    @pytest.mark.django_db
    def test_it_freezes_the_payload_of_the_period(self, client, writer, site):
        client.force_login(writer)

        client.post(reverse("monthly-report-draft"), {"period": "2026-08"})

        run = ReportRun.objects.get(period=PERIOD)
        assert run.status == ReportRun.STATUS_DRAFT
        assert run.generated_by == "writer"
        assert run.payload["meta"]["cutoff"] == "2026-08-31"

    @pytest.mark.django_db
    def test_a_second_press_does_not_create_a_twin(self, client, writer, site, draft):
        """La respuesta correcta a "ya existe" no es devolverlo callando.

        Quien apretó el botón dos veces tiene que saber cuál de las dos cosas
        pasó, y la restricción `(period, revision)` haría estallar el segundo
        `create` con un `IntegrityError` en la cara del usuario.
        """
        client.force_login(writer)

        client.post(reverse("monthly-report-draft"), {"period": "2026-08"})

        assert ReportRun.objects.filter(period=PERIOD).count() == 1
