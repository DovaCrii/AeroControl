"""Las evaluaciones teóricas del Manual de Operaciones (Act. 19, REG-019).

Origen: LV-158 (la prueba única de 25 preguntas y 80 %) y LV-444, que la
reemplaza por los tres tipos del Manual:

| Tipo | Partes | Umbral |
|---|---|---|
| Examen general (instrucción inicial) | 20 preguntas | 75 % |
| Limitaciones y emergencias, **por modelo de RPA** | 15 comunes + 3 del equipo | 100 % |
| Cuestionario anual (cada 12 meses) | A: 10 preguntas · B: limitaciones del modelo | A 75 % · B 100 % |

Un intento aprueba cuando **todas** sus partes alcanzan su umbral: 99 % en la
parte B reprueba aunque la A sea perfecta.

**El banco es dato y no vive en el repositorio.** Es público y las preguntas con
su clave son el examen. Se guarda en la base (`AssessmentQuestion`) y se carga con
`load_assessment_bank` desde un archivo fuera del repo; ver
`docs/assessment-bank-format.md`. Sin banco cargado la pantalla de rendir lo dice
(«El banco de preguntas no está cargado»), no falla.

**La corrección es del lado del servidor y el intento guarda su propia copia de
lo preguntado.** Si la respuesta correcta viajara al navegador la prueba no
mediría nada; y si el intento sólo guardara el puntaje, editar el banco
reescribiría lo que alguien rindió el año pasado — el error que `WeatherReview`
evita guardando los números tal como se leyeron.
"""

import calendar
import random
import re
import uuid
from dataclasses import dataclass

from django.utils.translation import gettext_lazy as _

# Decisiones del Manual (REG-019, Rev. 0). AGENTS.md: un umbral inventado
# convierte un control en un estorbo que alguien desactiva, así que cada número
# vive acá con nombre para que un test pueda nombrarlo.
GENERAL_QUESTIONS = 20
GENERAL_THRESHOLD = 75
LIMITATIONS_COMMON_QUESTIONS = 15
LIMITATIONS_EQUIPMENT_QUESTIONS = 3
LIMITATIONS_THRESHOLD = 100
ANNUAL_A_QUESTIONS = 10
ANNUAL_A_THRESHOLD = 75
ANNUAL_B_THRESHOLD = LIMITATIONS_THRESHOLD
ANNUAL_VALID_MONTHS = 12
VALID_MONTHS = ANNUAL_VALID_MONTHS

#: Los intentos anteriores a LV-444 (`kind="legacy"`) se rindieron con 80 %; el
#: umbral con que se evaluaron queda guardado en su `part_scores`.
LEGACY_PASS_PERCENT = 80

#: Un tipo de evaluación que se rinde con modelo de RPA.
FAMILY_KINDS = frozenset({"limitations", "annual"})

#: La instrucción inicial (examen general aprobado) vale como mantención de
#: eficiencia por este tiempo, igual que el cuestionario anual.
INITIAL_INSTRUCTION_MONTHS = ANNUAL_VALID_MONTHS

#: Tipo de documento (`DocumentType.reference_code`) con que se registra la
#: convalidación por credencial o fabricante: cuenta como examen general.
CONVALIDATION_REFERENCE_CODE = "REG-018"


@dataclass(frozen=True)
class PartPlan:
    """Una parte de un intento: de qué banco sale, cuántas preguntas y el umbral."""

    part: str
    source_kind: str
    common: int
    equipment: int
    threshold: int


PLANS = {
    "general": (PartPlan("A", "general", GENERAL_QUESTIONS, 0, GENERAL_THRESHOLD),),
    "limitations": (
        PartPlan(
            "A",
            "limitations",
            LIMITATIONS_COMMON_QUESTIONS,
            LIMITATIONS_EQUIPMENT_QUESTIONS,
            LIMITATIONS_THRESHOLD,
        ),
    ),
    "annual": (
        PartPlan("A", "annual", ANNUAL_A_QUESTIONS, 0, ANNUAL_A_THRESHOLD),
        PartPlan(
            "B",
            "limitations",
            LIMITATIONS_COMMON_QUESTIONS,
            LIMITATIONS_EQUIPMENT_QUESTIONS,
            ANNUAL_B_THRESHOLD,
        ),
    ),
}

KIND_LABELS = {
    "legacy": _("Previous assessment"),
    "general": _("General exam"),
    "limitations": _("Limitations and emergencies"),
    "annual": _("Annual questionnaire"),
}


def _unwrapped(text):
    """El texto con los espacios colapsados, **sin cambiar una sola palabra**.

    LV-163: los bancos se extraen de documentos y traen saltos de línea a mitad
    de frase. Colapsar espacios es la **única** normalización que se les hace
    (el comando de carga la aplica una vez): no toca ninguna palabra. Bajar las
    mayúsculas está descartado a propósito — el banco lleva siglas, METAR y
    números de norma, y un normalizador que les baje la caja le cambia el sentido
    a una pregunta de examen.
    """
    return " ".join(text.split())


# La enumeración romana tal como la escribe el banco, y el orden en que tiene que
# aparecer para que se la trate como enumeración.
_ROMAN_SEQUENCE = ("I.", "II.", "III.", "IV.", "V.", "VI.", "VII.", "VIII.")
_ENUMERATOR = re.compile(r"(?<=\s)(?:I{1,3}|IV|VI{0,3})\.(?=\s)")


def enumerated_lines(text):
    """El enunciado partido en renglones cuando enumera `I.`/`II.`/`III.`.

    LV-168. Se parte **en presentación y no en el dato**: lo que se corrige y la
    copia que el intento archiva en `answers` siguen siendo la línea colapsada,
    así que esto también arregla los intentos ya rendidos. No se toca una sola
    palabra ni la caja: unir lo que devuelve esta función con un espacio
    reproduce el texto de entrada.

    El disparo es conservador a propósito: hacen falta **dos marcadores o más y
    en orden desde `I.`**. Con un solo `I.` suelto no parte nada, porque un
    número romano puede aparecer en una frase sin ser una enumeración.
    """
    matches = list(_ENUMERATOR.finditer(text))
    markers = tuple(match.group(0) for match in matches)
    if len(markers) < 2 or markers != _ROMAN_SEQUENCE[: len(markers)]:
        return [text]
    starts = [match.start() for match in matches]
    bounds = [0, *starts, len(text)]
    segments = (text[start:end].strip() for start, end in zip(bounds, bounds[1:]))
    return [segment for segment in segments if segment]


def plan_for(kind):
    """Las partes de un tipo de evaluación (`KeyError` si el tipo no se rinde)."""
    return PLANS[kind]


def _questions(source_kind, family):
    from .models import AssessmentQuestion

    return AssessmentQuestion.objects.filter(
        is_active=True, kind=source_kind, aircraft_family=family
    )


def part_availability(plan, family):
    """Cuántas preguntas hay para una parte: `(comunes, del equipo)`."""
    common = _questions(plan.source_kind, None).count()
    equipment = (
        _questions(plan.source_kind, family).count()
        if plan.equipment and family is not None
        else 0
    )
    return common, equipment


def bank_is_available(kind, family=None):
    """Si hay con qué armar el intento: al menos una pregunta común por parte.

    No se exige el número completo del Manual (15 + 3): con menos preguntas el
    intento se arma con las que hay y la pantalla dice cuántas son. Exigir el
    total dejaría sin rendir todo un tipo porque falta cargar tres preguntas de
    un equipo, y lo que el Manual pide —umbrales por parte— se cumple igual.
    """
    if kind not in PLANS:
        return False
    return all(part_availability(plan, family)[0] > 0 for plan in PLANS[kind])


def planned_counts(kind, family=None):
    """Cuántas preguntas tendrá cada parte con el banco cargado hoy."""
    counts = {}
    for plan in PLANS[kind]:
        common, equipment = part_availability(plan, family)
        counts[plan.part] = min(plan.common, common) + min(plan.equipment, equipment)
    return counts


def draw_questions(kind, family=None, seed=None):
    """El sorteo de un intento: `{parte: [preguntas]}`, **sin la respuesta**.

    Lo que sale de acá es lo que se le muestra a la persona, así que la clave
    correcta no viaja: se resuelve al corregir, contra la base. Es la diferencia
    entre una prueba y un formulario.

    `seed` existe sólo para los tests: una prueba que sortea distinto en cada
    corrida no se puede afirmar. El sorteo real usa `SystemRandom`, y no por
    criptografía: es lo que hace que dos personas rindiendo a la vez no reciban
    el mismo juego.

    `nosec B311`: lo que bandit marca es usar `random` donde hace falta
    imprevisibilidad garantizada —tokens, contraseñas—. Acá la aleatoriedad
    reparte, no protege.
    """
    chooser = random.Random(seed) if seed is not None else random.SystemRandom()  # nosec B311
    drawn = {}
    for plan in PLANS[kind]:
        common = list(_questions(plan.source_kind, None).order_by("number"))
        equipment = (
            list(_questions(plan.source_kind, family).order_by("number"))
            if plan.equipment and family is not None
            else []
        )
        picked = chooser.sample(common, min(plan.common, len(common)))
        picked += chooser.sample(equipment, min(plan.equipment, len(equipment)))
        drawn[plan.part] = [
            {
                "id": str(question.pk),
                "text": question.text,
                "options": question.options,
            }
            for question in picked
        ]
    return drawn


def score_part(correct, total, threshold):
    """El puntaje de una parte. Aprueba con `porcentaje >= umbral`, exacto.

    Se compara con enteros (`correctas * 100 >= umbral * total`) y no con el
    porcentaje redondeado: 74,96 % redondeado a una cifra daría 75,0 y aprobaría
    por redondeo. El borde es el punto del umbral: 74 % reprueba, 75 % aprueba.
    """
    total_safe = total or 1
    return {
        "correct": correct,
        "total": total,
        "percent": round(correct * 100 / total_safe, 1),
        "threshold": threshold,
        "passed": total > 0 and correct * 100 >= threshold * total,
    }


def _as_uuids(values):
    """Los ids de sesión como UUID, descartando los que no lo son (no se corrigen)."""
    found = []
    for value in values:
        try:
            found.append(uuid.UUID(str(value)))
        except ValueError:
            continue
    return found


def grade_attempt(kind, ids_by_part, given):
    """Corregir un intento: `(filas, part_scores, aprobado, correctas, total)`.

    `filas` es la copia que el intento guarda: cada pregunta con su enunciado,
    sus opciones, lo que la persona marcó y lo que correspondía, más su parte.
    Es lo que después responde *"en qué se equivocó, qué reforzar"* sin depender
    de que el banco no haya cambiado.

    Una pregunta sin responder cuenta como incorrecta y se dice (`given: ""`), no
    se descuenta del total: el total es lo que se preguntó.
    """
    from .models import AssessmentQuestion

    by_id = {
        str(pk): question
        for pk, question in AssessmentQuestion.objects.in_bulk(
            _as_uuids(qid for ids in ids_by_part.values() for qid in ids)
        ).items()
    }
    thresholds = {plan.part: plan.threshold for plan in PLANS[kind]}
    rows = []
    part_scores = {}
    for part, ids in ids_by_part.items():
        part_rows = []
        for question_id in ids:
            question = by_id.get(question_id)
            answered = given.get(question_id, "")
            if question is None:
                # Una pregunta que ya no está: se conserva la marca para que el
                # total no cambie de forma silenciosa, y no se cuenta como buena.
                part_rows.append(
                    {
                        "id": question_id,
                        "part": part,
                        "text": str(_("This question is no longer in the bank.")),
                        "options": [],
                        "given": answered,
                        "answer": "",
                        "correct": False,
                    }
                )
                continue
            part_rows.append(
                {
                    "id": str(question.pk),
                    "part": part,
                    "text": question.text,
                    "options": question.options,
                    "given": answered,
                    "answer": question.answer,
                    "correct": answered == question.answer,
                }
            )
        rows.extend(part_rows)
        part_scores[part] = score_part(
            sum(1 for row in part_rows if row["correct"]),
            len(part_rows),
            thresholds[part],
        )
    passed = bool(part_scores) and all(
        score["passed"] for score in part_scores.values()
    )
    correct = sum(score["correct"] for score in part_scores.values())
    total = sum(score["total"] for score in part_scores.values())
    return rows, part_scores, passed, correct, total


def label_for(option_key, options):
    """El texto de una opción por su clave, para mostrar lo marcado en la revisión."""
    for option in options:
        if option["key"] == option_key:
            return option["text"]
    return ""


def add_months(day, months):
    """`day` más `months` meses, a mano y sin `dateutil`.

    El proyecto tiene política de dependencias mínimas y el gate corre
    `pip-audit`, así que una librería entera para sumar meses no se justifica. El
    29 de febrero cae al 28: la alternativa —el 1 de marzo— alargaría la
    vigencia un día, y de las dos formas de equivocarse por un día conviene la que
    no regala vigencia.
    """
    total = day.month - 1 + months
    year = day.year + total // 12
    month = total % 12 + 1
    return day.replace(
        year=year, month=month, day=min(day.day, calendar.monthrange(year, month)[1])
    )


def valid_until(taken_on):
    """La fecha en que el cuestionario anual deja de estar vigente."""
    return add_months(taken_on, VALID_MONTHS)


def validity_for(kind, taken_on):
    """La vigencia de un intento nuevo: sólo el cuestionario anual vence."""
    return valid_until(taken_on) if kind == "annual" else None


def families_for_aircraft(aircraft):
    """Los modelos del catálogo (`QualificationType`) que cubren esta aeronave.

    Mismo mecanismo que la compatibilidad operador–aeronave: fragmentos de
    `model_keywords` contra el modelo de la aeronave. Puede devolver varios (se
    acepta el que tenga la evaluación) o ninguno (no se puede comprobar).
    """
    from .models import QualificationType

    model = (getattr(aircraft, "model", "") or "").lower()
    return [
        qualification_type
        for qualification_type in QualificationType.objects.filter(is_active=True)
        if any(keyword in model for keyword in qualification_type.keyword_list())
    ]
