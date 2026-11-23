"""B7 (Manual Act. 19, Anexo D, D-3 §I): la regla de inactividad del operador.

Seis meses sin volar (según REG-016) y el operador debe repasar la teoría —el
cuestionario anual del RPA que va a operar— antes de volver a hacerlo. Con dos
años sin operar se repite el examen general y el de limitaciones y emergencias.
No hay vuelo de readaptación. La regla es **sólo de personas**.

La única fuente del último vuelo es la bitácora digital (`FlightRecord` activo,
`pilot` y `actual_date`): no se infiere nada de permisos ni de asignaciones.

Este módulo es puro: calcula y devuelve un `Recency`; quién lo aplica (y si está
encendido, `settings.INACTIVITY_RULE_ENABLED`) es de `operations.readiness` y de
la ficha del operador.

**Sin dato no hay bloqueo.** Sin ningún vuelo en la bitácora el estado es
`no_data`; el llamador decide avisar, nunca bloquear.

Un cuestionario `legacy` o de **otro** modelo no cuenta como repaso: la regla pide
el del RPA que se va a operar.
"""

from dataclasses import dataclass
from datetime import timedelta

from django.utils import timezone

INACTIVITY_MONTHS = 6
RETRAINING_MONTHS = 24
#: Mismo horizonte del aviso ámbar de «¿Puedo volar?» (`readiness`).
WARNING_HORIZON_DAYS = 30

OK = "ok"
DUE_SOON = "due_soon"
INACTIVE = "inactive"
RETRAINING = "retraining"
NO_DATA = "no_data"


@dataclass(frozen=True)
class Recency:
    last_flight: object  # date | None
    reference: object  # date | None: lo más reciente entre vuelo y repaso
    due_on: object  # date | None: fecha límite del repaso
    state: str
    needs: tuple = ()  # tipos de evaluación que hay que rendir


def last_flight_on(operator):
    """Fecha del último vuelo registrado del piloto, o `None`."""
    from django.db.models import Max

    from apps.operations.models import FlightRecord

    return FlightRecord.objects.filter(pilot=operator, is_active=True).aggregate(
        last=Max("actual_date")
    )["last"]


def _passed_dates(operator, kind, families=None):
    from apps.registry.models import KnowledgeAssessment

    rows = KnowledgeAssessment.objects.filter(
        operator=operator, is_active=True, passed=True, kind=kind
    )
    if families is not None:
        rows = rows.filter(aircraft_family__in=families)
    return [timezone.localtime(row.taken_at).date() for row in rows]


def recency(operator, today, aircraft=None):
    from apps.registry.assessments import add_months, families_for_aircraft

    last = last_flight_on(operator)
    if last is None:
        return Recency(None, None, None, NO_DATA)

    # Con aeronave, el repaso es el del modelo que va a operar; si el catálogo
    # no reconoce el modelo no se puede acotar y vale el de cualquier familia.
    families = families_for_aircraft(aircraft) if aircraft is not None else []
    scope = families or None
    reviews = _passed_dates(operator, "annual", scope)
    reference = max([last, *reviews])

    if add_months(last, RETRAINING_MONTHS) < today:
        generals = [d for d in _passed_dates(operator, "general") if d > last]
        limitations = [
            d for d in _passed_dates(operator, "limitations", scope) if d > last
        ]
        if generals and limitations:
            reference = max([reference, *generals, *limitations])
        else:
            due_on = add_months(reference, INACTIVITY_MONTHS)
            return Recency(
                last, reference, due_on, RETRAINING, ("general", "limitations")
            )

    due_on = add_months(reference, INACTIVITY_MONTHS)
    if due_on < today:
        return Recency(last, reference, due_on, INACTIVE, ("annual",))
    if due_on - today <= timedelta(days=WARNING_HORIZON_DAYS):
        return Recency(last, reference, due_on, DUE_SOON)
    return Recency(last, reference, due_on, OK)
