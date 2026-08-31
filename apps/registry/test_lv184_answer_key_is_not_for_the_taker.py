"""LV-184: la clave de respuestas no se le muestra a quien rindió la prueba.

Reportado por el usuario mirando la revisión de un intento: *"al momento de
revisar los resultados, no mostrar los resultados de la respuesta correcta a los
operadores"*.

**Por qué es más que una pantalla.** La revisión listaba, para cada pregunta
fallada, la respuesta correcta al lado — o sea el examen resuelto, entregado a
quien acaba de rendirlo y puede volver a rendirlo. Con eso la prueba deja de
medir: se memoriza y se aprueba. Y como **un intento aprobado alimenta el motor
de vencimientos** (`LV-173` lo verificó), lo que se degrada no es la pantalla
sino el estado de cumplimiento de una persona frente a la DGAC.

**Se resuelve con un permiso propio y no nombrando personas.** El usuario dijo
"sólo yo, Ariel Ortega y root": eso es un rol, no una lista de nombres — una
lista en el código se desactualiza el día que alguien entra o sale, y en
silencio. `view_assessment_answers` va a `Compliance` y **no a `Operations`**,
que es el rol de quien rinde.

**Y tampoco se cuelga de `view_operator`**, que es lo que la vista ya usa para
decidir de quién se ven los intentos: poder leer el padrón y poder ver la clave
de un examen son cosas distintas, y unirlas repartiría la clave a quien nunca se
la dieron.

Lo que **sí** sigue viendo quien rindió: qué preguntas falló y qué contestó. Eso
es "en qué se equivocó, qué reforzar" —el pedido original de `LV-158`— sin
entregar el examen: alcanza para saber qué estudiar y no para aprobar de memoria.
"""

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.core.testing import login_as
from apps.registry.models import KnowledgeAssessment, Operator

TODAY = timezone.localdate()
CORRECT = "OPERACIÓN CON VISIBILIDAD DIRECTA VISUAL (VLOS)"
WRONG = "OPERACIÓN MÁS ALLÁ DE LA LÍNEA VISUAL (BVLOS)"


@pytest.fixture
def attempt(db, django_user_model):
    user = django_user_model.objects.create_user("piloto", password="x")
    operator = Operator.objects.create(
        employee_id="E-1", full_name="Ana Rivas", user=user
    )
    return KnowledgeAssessment.objects.create(
        operator=operator,
        taken_by_user=user,
        question_count=1,
        correct_count=0,
        score_percent=0,
        passed=False,
        expires_on=TODAY + timezone.timedelta(days=365),
        answers=[
            {
                "id": 1,
                "text": "¿QUÉ ES VLOS?",
                "options": [
                    {"key": "A", "text": CORRECT},
                    {"key": "B", "text": WRONG},
                ],
                "given": "B",
                "answer": "A",
                "correct": False,
            }
        ],
    )


def test_the_taker_does_not_get_the_answer_key(attempt):
    """Es el examen resuelto, y esta prueba se puede volver a rendir."""
    client = login_as("view_knowledgeassessment", "view_operator")

    body = client.get(reverse("assessment-detail", args=[attempt.pk])).content.decode()

    assert CORRECT not in body


def test_the_taker_still_sees_what_they_got_wrong(attempt):
    """ "En qué se equivocó, qué reforzar" sin entregar la clave."""
    client = login_as("view_knowledgeassessment", "view_operator")

    body = client.get(reverse("assessment-detail", args=[attempt.pk])).content.decode()

    assert "¿QUÉ ES VLOS?" in body
    assert WRONG in body, "lo que contestó sí se ve: es lo que hay que corregir"


def test_it_says_why_the_answers_are_not_there(attempt):
    """Un dato ausente sin explicación se lee como una pantalla rota."""
    client = login_as("view_knowledgeassessment", "view_operator")

    body = client.get(reverse("assessment-detail", args=[attempt.pk])).content.decode()

    assert "no se muestran" in body or "not shown" in body


def test_whoever_holds_the_permission_does_see_it(attempt):
    """Compliance responde ante una auditoría y necesita el examen entero."""
    client = login_as(
        "view_knowledgeassessment", "view_operator", "view_assessment_answers"
    )

    body = client.get(reverse("assessment-detail", args=[attempt.pk])).content.decode()

    assert CORRECT in body


def test_the_permission_is_not_implied_by_reading_the_roster(attempt):
    """`view_operator` es "supervisa el padrón", no "puede ver el examen"."""
    client = login_as("view_knowledgeassessment", "view_operator")

    assert not client.user.has_perm("registry.view_assessment_answers")


@pytest.mark.django_db
def test_the_role_that_takes_the_test_does_not_get_the_key():
    """La fila entera: `Operations` rinde, y por eso no ve la clave."""
    from apps.core.management.commands.bootstrap_roles import ROLE_PERMISSIONS

    assert "view_assessment_answers" not in ROLE_PERMISSIONS["Operations"]
    assert "view_assessment_answers" in ROLE_PERMISSIONS["Compliance"]
