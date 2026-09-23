"""LV-233: el informe no puede fechar su corte en el futuro, ni congelarse abierto.

El usuario lo vio en pantalla el 2026-09-03, mirando la portada de septiembre
abierta el día 3: declaraba **"FECHA DE CORTE 30-09-2026"** — una fecha que no
había ocurrido, sobre datos que eran los de ese día. En un informe cuya regla es
que *nunca inventa un dato*, una fecha de corte futura es exactamente eso.

Y no era cosmético. El mismo defecto explica el 41 contra 42 del padrón de agosto
(`LV-234`): el informe emitido se hizo antes del 26 de agosto y decía "corte al
31-08", afirmando cinco días que no había mirado.

La mitad seria es la otra: **nada impedía congelar un mes en curso**, así que un
`ReportRun` de septiembre con datos de tres días podía nacer, aprobarse y
firmarse — y un `ReportRun` aprobado es el documento controlado que se emite a la
DGAC.
"""

from datetime import date, timedelta

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse
from django.utils import timezone

from apps.core.testing import login_as, pin_today_mid_month
from apps.reporting.builder import build, month_bounds
from apps.reporting.models import ReportRun


def _first_of(when):
    return when.replace(day=1)


class TestTheCutoffNeverSitsInTheFuture:
    @pytest.mark.django_db
    def test_a_month_in_progress_is_cut_today(self, db):
        today = timezone.localdate()

        payload, _missing = build(_first_of(today))

        assert payload["meta"]["cutoff"] == today.isoformat()

    @pytest.mark.django_db
    def test_and_the_payload_says_the_period_is_still_open(self, db, monkeypatch):
        """Viaja en el payload **congelado** y no se recalcula al dibujar: un
        informe que se congeló a mitad de mes tiene que seguir diciendo que se
        congeló a mitad de mes, aunque se lea en diciembre."""
        today = pin_today_mid_month(monkeypatch)
        _start, end = month_bounds(_first_of(today))

        payload, _missing = build(_first_of(today))

        assert payload["meta"]["in_progress"] is True
        assert payload["meta"]["days_remaining"] == (end - today).days

    @pytest.mark.django_db
    def test_a_closed_month_keeps_its_last_day(self, db):
        """La regla de siempre, intacta para el caso que el informe describe:
        usar "hoy" sobre un mes cerrado haría que el mismo período diera cifras
        distintas según cuándo se generara."""
        payload, _missing = build(date(2026, 8, 1))

        assert payload["meta"]["cutoff"] == "2026-08-31"
        assert payload["meta"]["in_progress"] is False
        assert payload["meta"]["days_remaining"] == 0

    @pytest.mark.django_db
    def test_a_future_month_is_also_cut_today(self, db):
        """El caso que nadie piensa, y por eso el corte es un `min` y no un `if`
        sobre el mes en curso: pedir el informe de un mes que todavía no empieza
        también tiene una sola fecha honesta."""
        today = timezone.localdate()
        far = date(today.year + 1, 1, 1)

        payload, _missing = build(far)

        assert payload["meta"]["cutoff"] == today.isoformat()

    @pytest.mark.django_db
    def test_an_explicit_cutoff_still_wins(self, db):
        """Quien pasa un corte a mano sabe lo que pide -- es como se reconstruye
        un informe viejo."""
        payload, _missing = build(date(2026, 8, 1), cutoff=date(2026, 8, 15))

        assert payload["meta"]["cutoff"] == "2026-08-15"


class TestThePermitTableDescribesTheCutoffAndNotToday:
    """⚠️ **El defecto de fondo, encontrado por el usuario en su propia página 3.**

    `collect_permits(cutoff)` usaba `cutoff` **sólo** para calcular la columna
    "Días" y no filtraba nada, así que la tabla listaba todos los permisos vivos
    *hoy* bajo un encabezado que dice "SITUACIÓN DE LOS PERMISOS AL CORTE". En el
    informe de agosto aparecían `JEJ-2026-012` y `013`, con vigencia
    **06-09 → 05-12**: permisos que el 31 de agosto no habilitaban nada.

    La confirmación fue el propio contraste con el papel emitido: 11 vigentes + 3
    en trámite = 14 en agosto; 14 vigentes + 0 en trámite en la app. **Los mismos
    catorce permisos**, con el estado de hoy en vez del de entonces.
    """

    CUTOFF = date(2026, 8, 31)

    def _permit(self, valid_from, valid_until, *, created, folio):
        from datetime import datetime, time

        from apps.operations.models import FlightPermission
        from apps.registry.models import CostCenter

        centre, _made = CostCenter.objects.get_or_create(
            code="CC738", defaults={"name": "MLP", "operates_flights": True}
        )
        permit = FlightPermission.objects.create(
            cost_center=centre,
            purpose="photogrammetry",
            status=FlightPermission.STATUS_APPROVED,
            permission_number=folio,
            location="Site",
            area_type="unpopulated",
            valid_from=valid_from,
            valid_until=valid_until,
        )
        FlightPermission.objects.filter(pk=permit.pk).update(
            created_at=timezone.make_aware(datetime.combine(created, time(12, 0)))
        )
        return permit

    @pytest.mark.django_db
    def test_a_permit_that_starts_after_the_cutoff_is_not_in_the_table(self, db):
        """El caso literal de la captura: vigencia 06-09 en el informe de agosto."""
        from apps.reporting.builder import collect_permits

        self._permit(
            date(2026, 9, 6), date(2026, 12, 5), created=date(2026, 8, 20), folio="6551"
        )

        assert collect_permits(self.CUTOFF) == []

    @pytest.mark.django_db
    def test_a_permit_created_after_the_cutoff_is_not_either(self, db):
        """Aunque su vigencia caiga dentro: el 31 de agosto no estaba en el
        sistema, así que ningún informe de agosto pudo haberlo mirado."""
        from apps.reporting.builder import collect_permits

        self._permit(
            date(2026, 8, 1), date(2026, 11, 1), created=date(2026, 9, 2), folio="6552"
        )

        assert collect_permits(self.CUTOFF) == []

    @pytest.mark.django_db
    def test_one_that_was_really_in_force_is(self, db):
        """Y la otra mitad, o el test anterior pasaría con una tabla siempre
        vacía."""
        from apps.reporting.builder import collect_permits

        self._permit(
            date(2026, 7, 1), date(2026, 10, 1), created=date(2026, 6, 20), folio="6553"
        )

        rows = collect_permits(self.CUTOFF)

        assert [row["dgac_number"] for row in rows] == ["6553"]


class TestTheStatusIsTheOneItHadAtTheCutoff:
    """El caso exacto del contraste contra el papel emitido.

    Agosto decía **11 vigentes y 3 en trámite**; la app mostraba **14 y 0**. Los
    mismos catorce permisos: los tres que en agosto esperaban a la DGAC ya fueron
    aprobados, y la tabla los listaba con su estado de hoy bajo un encabezado que
    dice "SITUACIÓN DE LOS PERMISOS AL CORTE".
    """

    CUTOFF = date(2026, 8, 31)

    def _requested_then_approved(self, *, approved_on):
        """Un permiso que al corte esperaba y hoy está aprobado."""
        from datetime import datetime, time

        from apps.operations.models import FlightPermission, PermissionHistory
        from apps.registry.models import CostCenter

        centre, _made = CostCenter.objects.get_or_create(
            code="CC738", defaults={"name": "MLP", "operates_flights": True}
        )
        permit = FlightPermission.objects.create(
            cost_center=centre,
            purpose="photogrammetry",
            status=FlightPermission.STATUS_APPROVED,
            permission_number="6600",
            location="Site",
            area_type="unpopulated",
            valid_from=date(2026, 8, 1),
            valid_until=date(2026, 11, 1),
        )
        FlightPermission.objects.filter(pk=permit.pk).update(
            created_at=timezone.make_aware(
                datetime.combine(date(2026, 7, 1), time(12, 0))
            )
        )
        entry = PermissionHistory.objects.create(
            permission=permit,
            previous_status=FlightPermission.STATUS_REQUESTED,
            new_status=FlightPermission.STATUS_APPROVED,
            changed_by="alguien",
        )
        PermissionHistory.objects.filter(pk=entry.pk).update(
            created_at=timezone.make_aware(datetime.combine(approved_on, time(12, 0)))
        )
        return permit

    @pytest.mark.django_db
    def test_approved_after_the_cutoff_still_reads_as_awaiting(self, db):
        from apps.reporting.builder import collect_permits

        self._requested_then_approved(approved_on=date(2026, 9, 2))

        rows = collect_permits(self.CUTOFF)

        assert rows[0]["status"] == "requested"
        # Y por lo tanto **no** cuenta como vigente: un trámite no habilita.
        assert rows[0]["in_force"] is False

    @pytest.mark.django_db
    def test_approved_before_the_cutoff_reads_as_approved(self, db):
        """La otra mitad, o el test anterior pasaría con "todo en trámite"."""
        from apps.reporting.builder import collect_permits

        self._requested_then_approved(approved_on=date(2026, 8, 10))

        rows = collect_permits(self.CUTOFF)

        assert rows[0]["status"] == "approved"
        assert rows[0]["in_force"] is True

    @pytest.mark.django_db
    def test_the_header_counters_agree_with_the_table(self, db):
        """⚠️ **Lo que de verdad se rompía.** Los cuatro contadores salían de
        `permit_counts` —el estado de hoy— y la tabla se reconstruye al corte, así
        que el encabezado decía "0 en trámite" sobre una tabla que listaba tres.
        Un encabezado que contradice a su propia tabla es peor que ninguno."""
        from apps.reporting.builder import build

        self._requested_then_approved(approved_on=date(2026, 9, 2))

        payload, _missing = build(date(2026, 8, 1))
        rows = payload["permits"]

        assert payload["kpis"]["permits_awaiting"]["value"] == sum(
            1 for row in rows if row["status"] == "requested"
        )
        assert payload["kpis"]["permits_in_force"]["value"] == sum(
            1 for row in rows if row["in_force"]
        )

    @pytest.mark.django_db
    def test_a_permit_that_never_moved_keeps_its_status(self, db):
        """Sin historial no hay nada que reconstruir, y el estado de hoy **es** el
        de entonces. Es el caso que se olvida y el más común."""
        from apps.reporting.builder import collect_permits

        from .test_lv233_cutoff_honesty import (
            TestThePermitTableDescribesTheCutoffAndNotToday as Table,
        )

        Table()._permit(
            date(2026, 7, 1), date(2026, 10, 1), created=date(2026, 6, 1), folio="6601"
        )

        rows = collect_permits(self.CUTOFF)

        assert rows[0]["status"] == "approved"


class TestArchivingAfterTheCutoffDoesNotEraseThePast:
    """LV-233, tercera parte. **Lo que se corrige es una omisión**, y por eso
    valía una columna nueva: un estado equivocado se ve en la fila, y una fila que
    falta no se ve en ninguna parte.

    `is_active` dice si está archivado **ahora** y no guarda cuándo dejó de
    estarlo, así que un permiso vivo en agosto y archivado en septiembre
    desaparecía del informe de agosto.
    """

    CUTOFF = date(2026, 8, 31)

    def _permit(self, *, archived_at):
        from datetime import datetime, time

        from apps.operations.models import FlightPermission
        from apps.registry.models import CostCenter

        centre, _made = CostCenter.objects.get_or_create(
            code="CC738", defaults={"name": "MLP", "operates_flights": True}
        )
        permit = FlightPermission.objects.create(
            cost_center=centre,
            purpose="photogrammetry",
            status=FlightPermission.STATUS_APPROVED,
            permission_number="6700",
            location="Site",
            area_type="unpopulated",
            valid_from=date(2026, 7, 1),
            valid_until=date(2026, 10, 1),
        )
        FlightPermission.objects.filter(pk=permit.pk).update(
            created_at=timezone.make_aware(
                datetime.combine(date(2026, 6, 1), time(12, 0))
            ),
            is_active=archived_at is None,
            archived_at=(
                timezone.make_aware(datetime.combine(archived_at, time(12, 0)))
                if archived_at
                else None
            ),
        )
        return permit

    @pytest.mark.django_db
    def test_archived_after_the_cutoff_still_appears(self, db):
        from apps.reporting.builder import collect_permits

        self._permit(archived_at=date(2026, 9, 2))

        assert len(collect_permits(self.CUTOFF)) == 1

    @pytest.mark.django_db
    def test_archived_before_the_cutoff_does_not(self, db):
        from apps.reporting.builder import collect_permits

        self._permit(archived_at=date(2026, 8, 10))

        assert collect_permits(self.CUTOFF) == []

    @pytest.mark.django_db
    def test_one_still_live_appears(self, db):
        from apps.reporting.builder import collect_permits

        self._permit(archived_at=None)

        assert len(collect_permits(self.CUTOFF)) == 1

    @pytest.mark.django_db
    def test_archiving_records_when_and_restoring_clears_it(self, db):
        """Un permiso vivo con fecha de archivo diría que sigue archivado, y el
        informe lo dejaría fuera de todo corte posterior — el defecto al revés."""

        permit = self._permit(archived_at=None)
        client = login_as(
            "delete_flightpermission",
            "change_flightpermission",
            "view_flightpermission",
        )

        client.post(
            reverse("permission-archive", args=[permit.pk]),
            {"confirm": "1", "reason": "Trámite desistido"},
        )
        permit.refresh_from_db()
        assert permit.is_active is False
        assert permit.archived_at is not None

        client.post(reverse("permission-restore", args=[permit.pk]))
        permit.refresh_from_db()
        assert permit.is_active is True
        assert permit.archived_at is None

    @pytest.mark.django_db
    def test_an_archive_without_a_date_stays_out(self, db):
        """Nulo es *no se sabe cuándo* —se archivó antes de que existiera la
        columna— y entonces queda fuera, que es lo que la consulta hacía siempre.
        La limitación está declarada en el pie del informe y **se achica sola**:
        cada archivo nuevo trae su fecha."""
        from apps.operations.models import FlightPermission
        from apps.reporting.builder import collect_permits

        permit = self._permit(archived_at=None)
        FlightPermission.objects.filter(pk=permit.pk).update(
            is_active=False, archived_at=None
        )

        assert collect_permits(self.CUTOFF) == []


class TestInForceMeansInForce:
    """`LV-233`: `permit_counts` miraba **sólo** `valid_until`.

    Para el panel de hoy era defendible —un permiso que empieza la semana que
    viene ya está autorizado— pero *vigente* significa estar en vigor, y mirando
    una fecha de corte pasada la diferencia deja de ser un matiz: se convierte en
    una afirmación falsa ante la DGAC.

    Como la función es **una sola para los dos lectores**, arreglar el informe
    obligaba a mover el panel. Lo que antes se sumaba a "vigentes" no se pierde:
    pasa a `not_started`, dicho por lo que es.
    """

    @pytest.mark.django_db
    def test_a_permit_that_has_not_started_is_not_in_force(self, db):
        from apps.compliance.kpis import permit_counts
        from apps.operations.models import FlightPermission
        from apps.registry.models import CostCenter

        centre = CostCenter.objects.create(
            code="CC738", name="MLP", operates_flights=True
        )
        today = timezone.localdate()
        FlightPermission.objects.create(
            cost_center=centre,
            purpose="photogrammetry",
            status=FlightPermission.STATUS_APPROVED,
            permission_number="7001",
            location="Site",
            area_type="unpopulated",
            valid_from=today + timedelta(days=7),
            valid_until=today + timedelta(days=97),
        )

        counts = permit_counts(today)

        assert counts["in_force"] == 0
        # No se pierde: queda contado por lo que es.
        assert counts["not_started"] == 1
        assert counts["total"] == 1

    @pytest.mark.django_db
    def test_freezing_the_current_month_is_refused(self, db, monkeypatch):
        today = pin_today_mid_month(monkeypatch)

        with pytest.raises(ValidationError):
            ReportRun.freeze(_first_of(today), "alguien")

        assert not ReportRun.objects.exists()

    @pytest.mark.django_db
    def test_the_last_day_of_the_month_is_already_closed(self, db):
        """⚠️ **El borde que importa, y el que un `>=` habría roto.** El mes
        termina el mismo día que es su último día, así que el 31 de agosto agosto
        **sí** se congela. Con la comparación mal puesta, el trabajo programado
        —que corre el último día del mes— habría quedado bloqueado justo el día
        que tiene que correr.
        """
        today = timezone.localdate()
        _start, end = month_bounds(_first_of(today))
        assert end >= today  # el mes en curso, por definición

        # El mes anterior ya cerró: su último día es pasado, y se congela.
        previous = _first_of(_first_of(today) - timedelta(days=1))
        run, created = ReportRun.freeze(previous, "alguien")

        assert created is True
        assert run.period == previous

    @pytest.mark.django_db
    def test_the_live_preview_still_works_for_the_open_month(self, db):
        """Mirar el mes en curso está bien; lo que no se puede es convertirlo en
        documento. Si `build` también se negara, la pantalla se quedaría sin
        vista previa — que es la mitad útil de tenerla."""
        today = timezone.localdate()

        payload, _missing = build(_first_of(today))

        assert payload["meta"]["period"] == f"{today:%Y-%m}"

    @pytest.mark.django_db
    def test_the_scheduled_command_refuses_it_as_an_error(self, db, monkeypatch):
        """Al revés que la pantalla, que avisa y sigue: un trabajo programado que
        se equivoca de mes tiene que **fallar**, para que el timer lo reporte, en
        vez de dejar un informe a medias que nadie sabe que está a medias. Es la
        misma asimetría que ya tiene `--period` mal escrito."""
        today = pin_today_mid_month(monkeypatch)

        with pytest.raises(CommandError):
            call_command("generate_monthly_report", f"--period={today:%Y-%m}")

    @pytest.mark.django_db
    def test_the_scheduled_command_still_does_its_normal_job(self, db):
        """Sin `--period` congela el mes recién cerrado, así que la guarda no lo
        toca. Se afirma acá porque es lo que habría roto un borde mal puesto, y
        se descubriría el día 1 del mes siguiente."""
        call_command("generate_monthly_report")

        assert ReportRun.objects.count() == 1
