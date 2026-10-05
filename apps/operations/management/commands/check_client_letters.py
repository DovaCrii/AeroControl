"""LV-226: qué permisos por vencer no tienen la carta del mandante en ficha.

Un permiso dura 3 meses (`LV-224`) y **renovarlo exige una carta nueva del
mandante** (`SPEC_REPORTE_MENSUAL_RPA.md` §4.1): no es un trámite que dependa
sólo de nosotros, hay que pedírsela a un tercero. Por eso la cadena de avisos del
motor empieza a 45 días (`seed_alert_rules`).

Pero esas reglas avisan **por fecha**, y lo que de verdad decide si la renovación
va a llegar a tiempo es una condición que ninguna regla de `AlertRule` puede
expresar: *si la carta está o no*. `AlertRule` vigila un campo contra una fecha;
"existe un documento de este tipo colgado de este permiso" no es un campo.

Así que el escalamiento condicional del SPEC —*"si a T-15 no hay carta
registrada, la alerta escala al Gerente de Operaciones Aéreas"*— vive acá, y
**deliberadamente no dentro del motor**: meter una condición por regla en
`generate_alerts` obligaría a que `AlertRule` supiera de documentos, y ese motor
es genérico sobre siete modelos. Es el mismo reparto que los otros `check_*`.

⚠️ **Desde `LV-232`, este comando es el único lugar donde vive ese escalamiento.**
`LV-226` había sembrado además una regla de `AlertRule` a 15 días para el mismo
propósito, y era ruido: repetía la fecha que ya decía la regla de 30 días y sólo
cambiaba el destinatario, así que un permiso próximo a vencer acumulaba cuatro o
cinco filas en la bandeja para un solo hecho. La regla se retiró; la pregunta
condicional se queda acá, que es donde se podía responder de verdad.

**No crea alertas.** Crear una alerta desde acá volvería a poner en la bandeja lo
que `LV-232` acaba de sacar, y `LV-111`/`LV-118` son dos filas gastadas justamente
en alertas repetidas.

⚠️ **LV-267: antes sólo imprimía, y nadie lo corría.** El informe emitido le dice
a la DGAC que *«sin carta, se escala al Gerente de Operaciones Aéreas»*, y el
único lugar donde eso existía era la salida de este comando — sin timer, sin
correo y sin registro de ejecución (comprobado en `p340` el 2026-10-05: no estaba
entre los 12 timers ni entre los trabajos con historial). Ahora, **sólo para lo que
escala** (15 días o menos), escribe al grupo Dirección; los de 45 días siguen
siendo trabajo del ADC en la bandeja, donde ya hay una alerta, y repetirlos por
correo cada día enseñaría a no leerlo. Calla cuando no hay nada que escalar, y
deja constancia en `JobRun` para que el vigilante note si dejó de correr.
"""

from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core.groups import REPORT_RECIPIENTS, direction_emails
from apps.core.jobs import record_job_run
from apps.core.mail import warn_undelivered_mail

ESCALATE_DAYS = 15


class Command(BaseCommand):
    help = "Report permits nearing expiry with no client authorization letter on file."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=45,
            help=(
                "Horizon in days (default 45, when the chain starts asking for "
                "the letter)."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report without sending mail.",
        )

    def handle(self, *args, **options):
        with record_job_run("check_client_letters") as run:
            escalated = self._report(options)
            mailed = self._notify(escalated, options["dry_run"]) if escalated else False
            run["mailed"] = mailed and not options["dry_run"]
            run["summary"] = (
                f"{'[dry-run] ' if options['dry_run'] else ''}"
                f"{len(escalated)} to escalate"
                + (", mailed" if mailed and not options["dry_run"] else "")
            )

    def _notify(self, escalated, dry_run):
        recipients = direction_emails()
        if not recipients:
            self.stdout.write(
                self.style.WARNING(
                    f"{len(escalated)} permit(s) to escalate but no recipients in "
                    f"the {REPORT_RECIPIENTS!r} group; nothing sent."
                )
            )
            return False
        if not dry_run:
            warn_undelivered_mail(self)
            EmailMessage(
                subject=_("AeroControl · permits expiring without the client letter"),
                body=render_to_string(
                    "operations/email/client_letters.txt",
                    {"rows": escalated, "base_url": settings.SITE_BASE_URL},
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=recipients,
            ).send()
        return True

    def _report(self, options):
        """Imprime el informe de siempre y devuelve lo que escala a Gerencia."""
        from django.contrib.contenttypes.models import ContentType

        from apps.compliance.models import Document

        # LV-230: la carta del mandante es `PERMIT_LETTER`. `CLIENT_LETTER` era el
        # tipo duplicado que `LV-225` creó para este mismo papel.
        from apps.operations.dossier import PERMIT_LETTER
        from apps.operations.models import FlightPermission

        horizon = options["days"]
        today = timezone.localdate()
        # `valid_until__isnull=False` es lo que deja fuera los permisos todavía
        # solicitados (`LV-219`): sin vigencia no hay renovación que preparar, y
        # listarlos como "sin carta" sería reprochar algo que no toca todavía.
        permits = (
            FlightPermission.objects.filter(
                is_active=True,
                valid_until__isnull=False,
                valid_until__lte=today + timedelta(days=horizon),
            )
            .exclude(status__in=FlightPermission.TERMINAL_STATUSES)
            .select_related("cost_center")
            .order_by("valid_until")
        )
        # Una consulta para todas las cartas, no una por permiso: este trabajo
        # corre a diario y el motor de alertas ya pagó esa lección
        # ("one query instead of an EXISTS per candidate record").
        with_letter = set(
            Document.objects.filter(
                content_type=ContentType.objects.get_for_model(FlightPermission),
                object_id__in=permits.values("pk"),
                doc_type__code=PERMIT_LETTER,
                is_current_version=True,
                is_active=True,
            ).values_list("object_id", flat=True)
        )
        missing = []
        for permit in permits:
            if permit.pk in with_letter:
                continue
            missing.append((permit, (permit.valid_until - today).days))
        total = len(permits)
        self.stdout.write(
            f"Client authorization letters, permits expiring within {horizon} "
            f"days ({total} permits):\n"
        )
        escalated = []
        for permit, days_left in missing:
            label = f"{permit.internal_folio} {permit.cost_center.code}".strip()
            when = (
                f"expired {abs(days_left)}d ago"
                if days_left < 0
                else f"{days_left}d left"
            )
            # El escalamiento del SPEC es por umbral, y se dice en la salida en
            # vez de decidirse en silencio: quien lee el trabajo diario ve a
            # quién le toca.
            if days_left <= ESCALATE_DAYS:
                escalated.append(
                    {
                        "label": label,
                        "valid_until": permit.valid_until,
                        "days_left": days_left,
                        "days_left_abs": abs(days_left),
                        "path": reverse("permission-detail", args=[permit.pk]),
                    }
                )
                self.stdout.write(
                    self.style.ERROR(f"  ESCALATE  {label:28} {when}  → Gerencia")
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f"  MISSING   {label:28} {when}  → ADC")
                )
        summary = f"\n{total - len(missing)} with letter, {len(missing)} missing."
        self.stdout.write(
            self.style.SUCCESS(summary) if not missing else self.style.WARNING(summary)
        )
        if missing:
            self.stdout.write(
                "Upload it from the permit's dossier (Carta del mandante). "
                "Renewal needs it; the DGAC does not renew without it."
            )
        return escalated
