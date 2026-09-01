"""LV-226: qué permisos por vencer no tienen la carta del mandante en ficha.

Un permiso dura 3 meses (`LV-224`) y **renovarlo exige una carta nueva del
mandante** (`SPEC_REPORTE_MENSUAL_RPA.md` §4.1): no es un trámite que dependa
sólo de nosotros, hay que pedírsela a un tercero. Por eso la cadena de avisos del
motor empieza a 45 días (`seed_alert_rules`).

Pero esas tres reglas avisan **por fecha**, y lo que de verdad decide si la
renovación va a llegar a tiempo es una condición que ninguna regla de `AlertRule`
puede expresar: *si la carta está o no*. `AlertRule` vigila un campo contra una
fecha; "existe un documento de este tipo colgado de este permiso" no es un campo.

Así que el escalamiento condicional del SPEC —*"si a T-15 no hay carta
registrada, la alerta escala al Gerente de Operaciones Aéreas"*— vive acá, y
**deliberadamente no dentro del motor**: meter una condición por regla en
`generate_alerts` obligaría a que `AlertRule` supiera de documentos, y ese motor
es genérico sobre siete modelos. Es el mismo reparto que los otros `check_*`.

**Read-only.** No crea alertas ni escribe nada: informa. Crear una alerta desde
acá duplicaría la fila que la regla T-15 ya escribió por fecha, y `LV-111`/`LV-118`
son dos filas gastadas justamente en alertas repetidas.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone


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

    def handle(self, *args, **options):
        from django.contrib.contenttypes.models import ContentType

        from apps.compliance.models import Document
        from apps.operations.dossier import CLIENT_LETTER
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
                doc_type__code=CLIENT_LETTER,
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
            if days_left <= 15:
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
