"""LV-114: avisar cuando un trabajo programado dejó de correr.

El centro de administración **ya sabía** qué trabajo estaba atrasado: lo dibuja
en su panel de situación desde hace tiempo. El problema es que hay que **entrar
a mirarlo**, y nadie entra a mirar cuando todo parece bien -- que es exactamente
cuando un timer lleva tres días caído.

Es la lección que `AGENTS.md` ya escribió con sangre: *"el gate verifica código,
nadie verifica el cableado de producción... tres funciones con tests verdes no
llegaban a nadie porque el grupo destinatario no tenía correos y un trabajo
programado nunca se registró"*. Detectarlo estaba resuelto; **contarlo** no.

Silencio cuando todo está al día: un vigilante que escribe todos los días
enseña a archivar sus correos sin leerlos, y entonces deja de ser un vigilante.
Sólo escribe cuando hay algo que arreglar.

**Este trabajo no puede vigilarse a sí mismo.** Si la máquina está apagada, no
corre y no avisa -- ningún vigilante interno puede cubrir ese caso, y decir lo
contrario sería peor que no tenerlo. Cubre lo que sí ocurre en la práctica: un
timer que falló, un comando que revienta cada noche, o uno que nunca se instaló.
"""

import logging

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.translation import gettext as _

from apps.core.groups import REPORT_RECIPIENTS
from apps.core.jobs import failing_jobs, record_job_run
from apps.core.mail import warn_undelivered_mail

logger = logging.getLogger("aerocontrol.notifications")


class Command(BaseCommand):
    help = "Warn Dirección when a scheduled job is overdue or failing."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report without sending mail.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        with record_job_run("check_scheduled_jobs") as run:
            failing = failing_jobs()
            mailed = self._notify(failing, dry_run) if failing else False
            # LV-119: este vigilante calla cuando todo está al día, así que sólo
            # se marca el día que de verdad tenía algo que avisar. Y es el peor
            # de los nueve para tener el correo cortado: existe precisamente
            # para que nadie tenga que entrar a mirar.
            run["mailed"] = mailed and not dry_run
            run["summary"] = f"{'[dry-run] ' if dry_run else ''}" + (
                f"{len(failing)} job(s) need attention{', mailed' if mailed else ''}"
                if failing
                else "every watched job is current"
            )
        if failing:
            for row in failing:
                self.stdout.write(
                    self.style.WARNING(
                        f"{row['command']}: "
                        + (
                            "never ran"
                            if row["never_ran"]
                            else f"{row['result']}, last {row['when']:%Y-%m-%d %H:%M}"
                        )
                    )
                )
        else:
            self.stdout.write(self.style.SUCCESS("Every watched job is current."))

    def _notify(self, failing, dry_run):
        recipients = list(
            Group.objects.filter(name=REPORT_RECIPIENTS)
            .values_list("user__email", flat=True)
            .exclude(user__email="")
            .exclude(user__email=None)
        )
        if not recipients:
            # El caso que AGENTS.md nombra: la función existía y no llegaba a
            # nadie. Se dice en voz alta en vez de dar por enviado.
            logger.warning(
                "scheduled_jobs_no_recipients",
                extra={"recipient": "", "item_count": len(failing)},
            )
            self.stdout.write(
                self.style.WARNING(
                    f"{len(failing)} job(s) need attention but no recipients in the "
                    f"{REPORT_RECIPIENTS!r} group; nothing sent."
                )
            )
            return False
        context = {
            "rows": failing,
            "base_url": settings.SITE_BASE_URL,
            "administration_path": reverse("administration"),
        }
        if not dry_run:
            warn_undelivered_mail(self)  # LV-119
            EmailMessage(
                subject=_("AeroControl · a scheduled job needs attention"),
                body=render_to_string("core/email/scheduled_jobs.txt", context),
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=recipients,
            ).send()
        logger.info(
            "scheduled_jobs_reported",
            extra={
                "recipient": ", ".join(recipients),
                "item_count": len(failing),
                "send_result": "dry_run" if dry_run else "sent",
            },
        )
        return True
