"""R5: congelar el informe desde un trabajo, y aprobarlo desde una persona.

Lo que estos tests protegen, por orden de gravedad:

1. **Que un informe aprobado no se pueda reabrir ni re-aprobar.** Es el
   documento que se envió; mover `approved_at` borraría la evidencia de quién y
   cuándo firmó.
2. **Que el comando sea idempotente.** Corre desde un timer el último día del
   mes: un reintento del scheduler, o dos timers solapados, no pueden partir en
   dos un documento controlado.
3. **Que `--force` emita una revisión y nunca sobrescriba**, y que las
   anteriores queden `superseded` en vez de borradas — lo que se envió sigue
   siendo evidencia.
4. **Que el comando no apruebe.** Aprobar es un acto de una persona; un trabajo
   nocturno que aprobara estaría firmando en nombre de alguien.
"""

from datetime import date
from io import StringIO

import pytest
from django.contrib.auth.models import Permission, User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse

from apps.registry.models import CostCenter
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
def approver(db):
    return _user("aprobador", "view_reportrun", "change_reportrun", "add_reportrun")


@pytest.fixture
def reader(db):
    return _user("lector", "view_reportrun")


@pytest.fixture
def site(db):
    return CostCenter.objects.create(code="CC738", name="MLP", operates_flights=True)


def _run(**kwargs):
    out = StringIO()
    call_command("generate_monthly_report", stdout=out, **kwargs)
    return out.getvalue()


class TestTheCommandIsIdempotent:
    @pytest.mark.django_db
    def test_running_it_twice_does_not_create_two_reports(self, site):
        """**De esto depende que pueda ser un timer.**

        Corre el último día del mes; un reintento del scheduler o dos timers
        solapados no pueden partir en dos un documento controlado.
        """
        _run(period="2026-08")
        output = _run(period="2026-08")

        assert ReportRun.objects.filter(period=PERIOD).count() == 1
        assert "ya existe" in output

    @pytest.mark.django_db
    def test_the_second_run_is_not_an_error(self, site):
        """No sale con código distinto de cero, y es deliberado.

        Fallar acá haría que el scheduler marcara en rojo la noche en que todo
        salió bien, y un rojo que aparece todos los meses se deja de mirar.
        """
        _run(period="2026-08")

        _run(period="2026-08")  # sin CommandError

    @pytest.mark.django_db
    def test_dry_run_writes_nothing(self, site):
        output = _run(period="2026-08", dry_run=True)

        assert not ReportRun.objects.exists()
        assert "[dry-run]" in output


class TestForceIssuesARevision:
    @pytest.mark.django_db
    def test_it_never_overwrites(self, site):
        """La contradicción del SPEC, resuelta: §1.1 pedía período único y §5.1
        que `--force` creara una versión nueva."""
        _run(period="2026-08")

        _run(period="2026-08", force=True)

        revisions = list(
            ReportRun.objects.filter(period=PERIOD)
            .order_by("revision")
            .values_list("revision", "status")
        )
        assert revisions == [
            (0, ReportRun.STATUS_SUPERSEDED),
            (1, ReportRun.STATUS_DRAFT),
        ]

    @pytest.mark.django_db
    def test_an_approved_revision_is_superseded_and_keeps_who_signed_it(self, site):
        """**Lo que se envió sigue siendo evidencia.**

        La revisión 0 pasa a `superseded`, pero `approved_by` sobrevive: quién
        firmó la 0 sigue siendo un hecho después de que exista la 1.
        """
        _run(period="2026-08")
        first = ReportRun.objects.get(period=PERIOD)
        first.approve("ariel")

        _run(period="2026-08", force=True)

        first.refresh_from_db()
        assert first.status == ReportRun.STATUS_SUPERSEDED
        assert first.approved_by == "ariel"
        assert first.approved_at is not None

    @pytest.mark.django_db
    def test_the_narrative_travels_to_the_new_revision(self, site):
        """Decisión, no descuido: si las cifras se corrigen los hallazgos pueden
        quedar desactualizados, pero borrarlos obliga a reescribir de cero y ahí
        nadie nota que un hallazgo dejó de ser cierto. Copiados, quedan a la
        vista para corregirlos."""
        _run(period="2026-08")
        first = ReportRun.objects.get(period=PERIOD)
        first.findings = [{"severity": "critical", "title": "T", "text": "X"}]
        first.period_note = "La vigencia no es uniforme."
        first.save()

        _run(period="2026-08", force=True)

        second = ReportRun.objects.get(period=PERIOD, revision=1)
        assert second.findings == first.findings
        assert second.period_note == "La vigencia no es uniforme."

    @pytest.mark.django_db
    def test_the_screen_shows_the_latest_revision(self, client, reader, site):
        _run(period="2026-08")
        _run(period="2026-08", force=True)
        client.force_login(reader)

        response = client.get(reverse("monthly-report"), {"period": "2026-08"})

        assert response.context["run"].revision == 1


class TestTheCommandDoesNotApprove:
    @pytest.mark.django_db
    def test_what_it_freezes_is_a_draft(self, site):
        """Un trabajo nocturno que aprobara estaría firmando en nombre de
        alguien, y el informe va firmado ante la DGAC."""
        _run(period="2026-08")

        report = ReportRun.objects.get(period=PERIOD)
        assert report.status == ReportRun.STATUS_DRAFT
        assert report.approved_at is None
        assert report.generated_by == "generate_monthly_report"

    @pytest.mark.django_db
    def test_it_defaults_to_the_month_already_closed(self, site):
        """Sin `--period`, el mes cerrado: un informe mensual describe un mes
        terminado."""
        from django.utils import timezone

        from apps.reporting.views import previous_month

        _run()

        assert ReportRun.objects.filter(
            period=previous_month(timezone.localdate())
        ).exists()

    @pytest.mark.django_db
    @pytest.mark.parametrize("raw", ["agosto", "2026", "26-08", "2026-13"])
    def test_a_broken_period_fails_instead_of_falling_back(self, raw):
        """**Al revés que la pantalla, y a propósito.**

        Ahí el parámetro llega de un enlace pegado a mano y conviene mostrar
        algo; acá alguien tecleó `--period` con una intención concreta, y
        congelar otro mes en silencio es peor que no congelar ninguno.
        """
        with pytest.raises(CommandError):
            _run(period=raw)


class TestApprovingIsAPersonAndItCloses:
    @pytest.mark.django_db
    def test_a_reader_cannot_approve(self, client, reader, site):
        _run(period="2026-08")
        report = ReportRun.objects.get(period=PERIOD)
        client.force_login(reader)

        response = client.post(reverse("monthly-report-approve", args=[report.pk]))

        assert response.status_code == 403
        report.refresh_from_db()
        assert report.status == ReportRun.STATUS_DRAFT

    @pytest.mark.django_db
    def test_approving_records_who_and_when(self, client, approver, site):
        _run(period="2026-08")
        report = ReportRun.objects.get(period=PERIOD)
        client.force_login(approver)

        client.post(reverse("monthly-report-approve", args=[report.pk]))

        report.refresh_from_db()
        assert report.status == ReportRun.STATUS_APPROVED
        assert report.approved_by == "aprobador"
        assert report.approved_at is not None

    @pytest.mark.django_db
    def test_it_cannot_be_approved_twice(self, site):
        """**El test que más importa de este archivo.**

        Re-aprobar movería `approved_at` y `approved_by` de un documento que ya
        se envió, y con ellos la evidencia de quién y cuándo lo firmó.
        """
        _run(period="2026-08")
        report = ReportRun.objects.get(period=PERIOD)
        report.approve("ariel")
        first_time = report.approved_at

        with pytest.raises(ValidationError):
            report.approve("otro")

        report.refresh_from_db()
        assert report.approved_by == "ariel"
        assert report.approved_at == first_time

    @pytest.mark.django_db
    def test_a_superseded_revision_cannot_be_approved(self, site):
        """Una revisión reemplazada no vuelve a la vida por aprobarla."""
        _run(period="2026-08")
        _run(period="2026-08", force=True)
        old = ReportRun.objects.get(period=PERIOD, revision=0)

        with pytest.raises(ValidationError):
            old.approve("quien sea")

    @pytest.mark.django_db
    def test_the_guard_lives_in_the_model_so_every_path_hits_it(self):
        """El admin y el shell escriben igual que la vista.

        Con la comprobación sólo en la vista, aprobar dos veces desde el admin
        habría movido la fecha sin que nada avisara.
        """
        report = ReportRun(status=ReportRun.STATUS_APPROVED)

        with pytest.raises(ValidationError):
            report.approve("x")

    @pytest.mark.django_db
    def test_an_approved_report_is_no_longer_editable_from_the_screen(
        self, client, approver, site
    ):
        _run(period="2026-08")
        report = ReportRun.objects.get(period=PERIOD)
        report.approve("ariel")
        client.force_login(approver)

        body = client.get(
            reverse("monthly-report"), {"period": "2026-08"}
        ).content.decode()

        assert reverse("monthly-report-narrative", args=[report.pk]) not in body
        assert reverse("monthly-report-approve", args=[report.pk]) not in body


class TestCompletenessIsAStateNotAnInstruction:
    @pytest.mark.django_db
    def test_the_spanish_label_says_completo_and_not_completar(self):
        """**Encontrado corriendo el comando, no leyendo el código.**

        `_("Complete")` a secas comparte msgid con el **botón** de completar una
        mantención y un permiso, así que el catálogo lo traduce como *"Completar"*
        — un verbo. Acá es un estado, y el comando imprimía "0 campos sin dato al
        corte (Completar)", que se lee como una instrucción sobre un informe que
        ya está entero. Se resuelve con contexto (`pgettext_lazy`).

        Se afirma contra el objeto y no contra un texto tecleado: comparar con la
        cadena traducida a mano es cómo un test pasa por la razón vecina.
        """
        from django.utils import translation

        report = ReportRun(
            period=PERIOD, generated_by="x", completeness=ReportRun.COMPLETENESS_OK
        )

        with translation.override("es"):
            label = str(report.get_completeness_display())

        assert label == "Completo"
        assert label != "Completar"


class TestTheButtonAndTheJobFreezeTheSameWay:
    @pytest.mark.django_db
    def test_the_screen_button_goes_through_freeze(self, client, approver, site):
        """Dos caminos que congelan por separado es cómo el informe que genera
        el timer y el que genera una persona empiezan a diferir."""
        client.force_login(approver)

        client.post(reverse("monthly-report-draft"), {"period": "2026-08"})

        report = ReportRun.objects.get(period=PERIOD)
        assert report.generated_by == "aprobador"
        assert report.status == ReportRun.STATUS_DRAFT

    @pytest.mark.django_db
    def test_pressing_the_button_twice_does_not_create_a_twin(
        self, client, approver, site
    ):
        client.force_login(approver)

        client.post(reverse("monthly-report-draft"), {"period": "2026-08"})
        client.post(reverse("monthly-report-draft"), {"period": "2026-08"})

        assert ReportRun.objects.filter(period=PERIOD).count() == 1
