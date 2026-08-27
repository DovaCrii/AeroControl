"""Fleet and personnel roster -- the "catastro" of LV-145.

The user's words: *"que me permita sacar un catastro de todos los RPA y todos
los operadores hoy inscritos a la fecha […] lo necesito cuando me soliciten
algo"*. Before this, the closest thing was `?export=csv` on each list
separately, which also **drops `is_active`** through the export mixin's default
exclusion list -- precisely the field that says whether something is still in
inventory.

Data only, no rendering: the screen, the PDF, the spreadsheet and the CSV all
read this module, so a number cannot differ between the paper handed to a client
and the file attached to the mail. Scope, set by the user: **the two base tables
plus a totals line** -- no qualifications, no technical annexes, no separate
summary page.
"""

from dataclasses import dataclass

from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy as _lazy
from django.utils.translation import ngettext

from apps.core.tenancy import scope_queryset_to_tenant
from .models import Aircraft, CostCenter, Operator

# Ordered as they are read out loud: what identifies the airframe, then who
# made it, then its condition and where it is assigned.
AIRCRAFT_HEADERS = [
    _lazy("Registration"),
    _lazy("Type"),
    _lazy("Model"),
    _lazy("Manufacturer"),
    _lazy("Serial number"),
    _lazy("Year"),
    _lazy("Status"),
    _lazy("Cost center"),
    # LV-167: la vigencia va **última** en las dos tablas, y no es estética: así
    # su índice es `len(headers) - 1` y quien pinta el color de urgencia no
    # necesita una constante aparte que se pueda desincronizar del orden.
    _lazy("JAC insurance expiry"),
]

# Identity and credential, and nothing else. Email and phone are deliberately
# **not** here: this document is written to be handed to whoever asked for it,
# the user asked for the roster and not for a contact list, and personal contact
# details are the kind of column that is easy to add and impossible to recall.
# LV-167: se fue `Employee ID`. En producción vale `RUT-192135974` y la columna
# de al lado dice `19213597-4`: el mismo número dos veces, en dos formatos, que
# es exactamente la confusión que el usuario reportó. El RUT es la llave natural
# chilena (`LV-143`) y es el que se pide cuando alguien pregunta por una persona.
OPERATOR_HEADERS = [
    _lazy("Full name"),
    _lazy("RUT"),
    _lazy("DGAC credential"),
    _lazy("Operator type"),
    _lazy("Cost center"),
    _lazy("DGAC credential expiry"),
]

# El índice de la columna de vigencia en cada tabla, derivado y no escrito: es la
# última, así que no puede quedar apuntando a otra si mañana se agrega una
# columna en el medio.
AIRCRAFT_EXPIRY_COLUMN = len(AIRCRAFT_HEADERS) - 1
OPERATOR_EXPIRY_COLUMN = len(OPERATOR_HEADERS) - 1

BLANK = "—"


@dataclass(frozen=True)
class CatastroFilters:
    """What narrows the roster, and what each choice hides.

    Defaults are the roster as the operation understands it: everything on the
    books, retired airframes excluded, archived rows excluded. Both exclusions
    are opt-in rather than opt-out because "how many aircraft do we have" is
    almost never asked about the ones that left.
    """

    cost_center: CostCenter | None = None
    status: str = ""
    include_terminal: bool = False
    include_archived: bool = False


def _base(queryset, filters, user):
    queryset = scope_queryset_to_tenant(queryset, user)
    if not filters.include_archived:
        queryset = queryset.filter(is_active=True)
    return queryset


def build_catastro(user, filters=None):
    """The roster as of today, ready for any of the four outputs.

    Two queries -- one per table -- plus two counts **only** when a cost-center
    filter is on, because that is the case where the rows it hides are outside
    the result set and cannot be counted in Python. Pinned with
    `django_assert_num_queries` in both shapes.

    `user` is required and comes first, with no default: it is what scopes both
    tables to the tenant, and a default would make "unscoped" the thing you get
    by forgetting -- which is the shape of the F-03/F-06 findings.
    """
    filters = filters or CatastroFilters()
    as_of = timezone.localdate()

    aircraft = _base(Aircraft.objects.all(), filters, user).select_related(
        "cost_center"
    )
    if filters.status:
        aircraft = aircraft.filter(status=filters.status)
    elif not filters.include_terminal:
        # `TERMINAL_STATUSES`, never the literal "retired": the day a second
        # terminal status exists, a hard-coded string here would keep counting
        # airframes that left the fleet. An explicit status filter wins over
        # this, so asking for "Retired" still answers.
        aircraft = aircraft.exclude(status__in=Aircraft.TERMINAL_STATUSES)

    operators = _base(Operator.objects.all(), filters, user).select_related(
        "cost_center"
    )

    filtered_by_cost_center = filters.cost_center is not None
    if filtered_by_cost_center:
        # Counted before the filter narrows the set: afterwards these rows are
        # outside the queryset and there is nothing left in Python to count.
        unassigned_aircraft = aircraft.filter(cost_center__isnull=True).count()
        unassigned_operators = operators.filter(cost_center__isnull=True).count()
        aircraft = aircraft.filter(cost_center=filters.cost_center)
        operators = operators.filter(cost_center=filters.cost_center)

    aircraft = list(aircraft.order_by("registration"))
    operators = list(operators.order_by("full_name"))

    if not filtered_by_cost_center:
        # No filter, so the unassigned rows are *in* the table: counted from
        # what was already fetched, at the cost of no query at all.
        unassigned_aircraft = sum(1 for row in aircraft if row.cost_center_id is None)
        unassigned_operators = sum(1 for row in operators if row.cost_center_id is None)

    return {
        # The cut-off date is part of the answer, not decoration: a roster
        # without one cannot be filed, and the four outputs all declare it.
        "as_of": as_of,
        "filters": filters,
        "aircraft": aircraft,
        "operators": operators,
        "totals": {
            "aircraft": len(aircraft),
            "operators": len(operators),
            "aircraft_without_cost_center": unassigned_aircraft,
            "operators_without_cost_center": unassigned_operators,
            # Which of the two meanings the numbers above carry. Without this
            # the sentence would have to guess, and "3 sin faena" reads very
            # differently depending on whether those three are on the page.
            "unassigned_are_hidden": filtered_by_cost_center,
        },
    }


def aircraft_rows(catastro):
    return [
        [
            aircraft.registration,
            aircraft.type or BLANK,
            aircraft.model or BLANK,
            aircraft.manufacturer or BLANK,
            aircraft.serial_number or BLANK,
            aircraft.year or BLANK,
            aircraft.get_status_display(),
            aircraft.cost_center.code if aircraft.cost_center_id else BLANK,
            _date(aircraft.insurance_expiry),
        ]
        for aircraft in catastro["aircraft"]
    ]


def operator_rows(catastro):
    return [
        [
            operator.full_name,
            operator.rut or BLANK,
            operator.dgac_credential or BLANK,
            operator.operator_type or BLANK,
            operator.cost_center.code if operator.cost_center_id else BLANK,
            _date(operator.credential_expiry),
        ]
        for operator in catastro["operators"]
    ]


def _date(value):
    """La fecha en ISO, o un guion cuando no hay.

    LV-167: **un nulo no se convierte en nada más que un guion.** Buena parte del
    padrón no tiene la fecha cargada (el panel de producción cuenta 7 credenciales
    y 2 seguros sin fecha), y ahí la lección de `LV-29` es la que manda: un nulo
    es "nunca se ingresó", no "está vigente". No se pinta de ningún color y no
    entra en ningún tramo de urgencia.
    """
    return value.isoformat() if value else BLANK


def aircraft_expiries(catastro):
    """La fecha de vigencia de cada fila de flota, en el orden de la tabla.

    Se devuelve la **fecha** y no el tramo de urgencia: el tramo lo calcula quien
    pinta, con `bucket_for` del digest, que es el dueño de los cortes. Que este
    módulo importara `apps.compliance` para colorear una celda sería atar el
    padrón al cumplimiento por una cuestión de color.
    """
    return [aircraft.insurance_expiry for aircraft in catastro["aircraft"]]


def operator_expiries(catastro):
    return [operator.credential_expiry for operator in catastro["operators"]]


def _counted(aircraft, operators):
    """The two counted phrases, each agreeing with its own number.

    Spanish agrees the noun with its count, and every sentence here carries
    **two** independent counts -- while `ngettext` handles one. So each phrase is
    built on its own and the sentences compose them.

    Interpolating the numbers straight into one message is what the first
    version did, and the real roster in production caught it on the day it
    shipped: with a single unassigned airframe it read *"1 aeronaves"*. That is
    the kind of thing that makes a document handed to a client look careless,
    and no test of mine would have found it -- the fixtures all had two.

    In English "aircraft" is invariant, so its singular and plural msgids are
    the same string. That is not a copy-paste slip: it is exactly the case
    gettext's plural machinery exists for, a source language that does not
    inflect where the target does.
    """
    return {
        "fleet": ngettext("%(count)s aircraft", "%(count)s aircraft", aircraft)
        % {"count": aircraft},
        "personnel": ngettext("%(count)s operator", "%(count)s operators", operators)
        % {"count": operators},
    }


def totals_sentence(catastro):
    """The one line every output carries, cut-off date included.

    Returns a list of sentences rather than one string: the second only exists
    when something was left out, and gluing them would put a dangling clause on
    a roster that has nothing to disclose.
    """
    totals = catastro["totals"]
    counted = _counted(totals["aircraft"], totals["operators"])
    sentences = [
        _("%(fleet)s and %(personnel)s registered as of %(date)s.")
        % {**counted, "date": catastro["as_of"].isoformat()}
    ]
    without = (
        totals["aircraft_without_cost_center"],
        totals["operators_without_cost_center"],
    )
    if not any(without):
        return sentences

    # A cost-center filter drops everything unassigned, silently, because
    # `cost_center` is nullable on both models. The report says how much.
    #
    # The verb stays plural in both sentences even when each count is 1: two
    # subjects joined by "y" take a plural verb in Spanish, so "1 aeronave y 1
    # operador no tienen centro de costo" is right.
    hidden = _counted(*without)
    if totals["unassigned_are_hidden"]:
        sentences.append(
            _(
                "Filtered by cost center: %(fleet)s and %(personnel)s with no "
                "cost center are not listed."
            )
            % hidden
        )
    else:
        sentences.append(
            _("Of these, %(fleet)s and %(personnel)s have no cost center assigned.")
            % hidden
        )
    return sentences
