"""Un banco de preguntas **inventado** para los tests de las evaluaciones.

Nunca preguntas reales del REG-019: este repo es público y el banco real vive fuera
de él (`load_assessment_bank`). Los enunciados son de relleno y las respuestas
correctas rotan entre a, b y c para que un test no pase contestando siempre «a».
"""

from apps.registry.models import AssessmentQuestion, QualificationType


def make_family(code="mavic", name="Mavic series", keywords="mavic"):
    return QualificationType.objects.create(
        code=code, name=name, model_keywords=keywords
    )


def make_question(kind, number, family=None, **extra):
    options = [{"key": key, "text": f"Option {key.upper()}"} for key in "abc"]
    return AssessmentQuestion.objects.create(
        kind=kind,
        aircraft_family=family,
        number=number,
        text=extra.pop("text", f"Invented {kind} question {number}"),
        options=options,
        answer=extra.pop("answer", "abc"[number % 3]),
        **extra,
    )


def make_bank(family=None, *, general=25, limitations=18, annual=12, equipment=4):
    """Banco con de sobra para cada tipo; `family` recibe `equipment` propias."""
    for number in range(1, general + 1):
        make_question("general", number)
    for number in range(1, limitations + 1):
        make_question("limitations", number)
    for number in range(1, annual + 1):
        make_question("annual", number)
    if family is not None:
        for number in range(1, equipment + 1):
            make_question("limitations", number, family=family)


def correct_answers(session_value):
    """Las respuestas correctas de un sorteo guardado en la sesión."""
    ids = [qid for part in session_value["parts"].values() for qid in part]
    by_id = {str(pk): q for pk, q in AssessmentQuestion.objects.in_bulk(ids).items()}
    return {f"q{qid}": by_id[qid].answer for qid in ids}
