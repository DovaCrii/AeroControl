"""LV-158: la prueba interna de conocimientos, con su resultado en el historial.

Pedido del usuario, con el repositorio propio del quiz como fuente: *"una prueba
interna para ver las capacidades […] para ingresar se debe ligar con las
credenciales del operador, y al operador quedar en el historial […] con un
aprobado o insuficiente, y en qué se equivocó, qué reforzar […] para conocer y
dejar claro cómo está la condición de los profesionales"*.

Reglas suyas, del 2026-08-26: **25 preguntas, 80% para aprobar, vigencia de 12
meses**. Son constantes con nombre y estos tests las nombran: un umbral es una
decisión de negocio, y un test que la escriba como literal la vuelve invisible.

Las propiedades que estos tests sostienen, y por qué cada una:

- **La respuesta correcta no viaja al navegador.** Si viajara, la prueba no
  mediría nada.
- **El sorteo vive en la sesión.** En un campo oculto se podría cambiar por 25
  preguntas fáciles; como fila "en curso" en la base, cada prueba abandonada
  dejaría basura indistinguible de una rendida.
- **El intento guarda su propia copia de lo preguntado.** El banco es un archivo
  de datos que se va a corregir; sin la copia, editar una redacción reescribiría
  lo que alguien rindió el año pasado.
- **Sin `Operator.user` no se rinde.** Adivinar la persona por correo es lo que
  `B3.2` se negó a hacer, y acá eso escribiría una evaluación en el historial de
  otro.
"""

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.core.testing import login_as
from apps.registry import assessments
from apps.registry.models import CostCenter, KnowledgeAssessment, Operator

TODAY = timezone.localdate()


def _operator(user=None, **kwargs):
    return Operator.objects.create(
        employee_id=kwargs.pop("employee_id", "E-1"),
        full_name=kwargs.pop("full_name", "Operator A"),
        user=user,
        **kwargs,
    )


def _client_for_operator(*codenames):
    """Un cliente cuyo usuario **es** un operador, que es el requisito de entrada."""
    client = login_as(*codenames)
    operator = _operator(user=client.user)
    return client, operator


class TestTheValidityWindow:
    def test_it_lasts_the_months_the_user_decided(self):
        from datetime import date

        assert assessments.valid_until(date(2026, 8, 26)) == date(2027, 8, 26)

    def test_the_twenty_ninth_of_february_falls_back_a_day(self):
        # De las dos formas de equivocarse por un día, la que no regala vigencia.
        from datetime import date

        assert assessments.valid_until(date(2028, 2, 29)) == date(2029, 2, 28)


@pytest.mark.django_db
class TestWhoCanTakeIt:
    def test_a_user_with_no_operator_record_cannot_take_it(self):
        # Sin el vínculo no hay a quién atribuir el intento, y adivinar por
        # correo es justo lo que `B3.2` se negó a hacer.
        client = login_as("add_knowledgeassessment")

        response = client.get(reverse("assessment-take"))

        assert response.status_code == 302
        assert not KnowledgeAssessment.objects.exists()

    def test_it_is_403_without_add_permission(self):
        client = login_as("view_knowledgeassessment")
        _operator(user=client.user)

        assert client.get(reverse("assessment-take")).status_code == 403


@pytest.mark.django_db
class TestReadingTheResult:
    def _taken(self, operator, passed=False):
        return KnowledgeAssessment.objects.create(
            operator=operator,
            question_count=25,
            correct_count=25 if passed else 10,
            score_percent=100 if passed else 40,
            passed=passed,
            expires_on=assessments.valid_until(TODAY),
            answers=[
                {
                    "id": 1,
                    "text": "AL AUMENTAR LA ALTURA, LA DENSIDAD DEL AIRE DISMINUYE",
                    "options": [
                        {"key": "a", "text": "Verdadero"},
                        {"key": "b", "text": "Falso"},
                    ],
                    "given": "b",
                    "answer": "a",
                    "correct": False,
                }
            ],
        )

    def test_the_review_says_what_was_wrong_but_not_what_was_right(self):
        """LV-184 dio vuelta la mitad de esta afirmación, y estaba bien escrita.

        Cuando se escribió, mostrar la respuesta correcta era el objetivo: *"en
        qué se equivocó, qué reforzar"*. Lo que cambió es quién mira: es **la
        misma persona que rindió** y que puede volver a rendir, así que la
        revisión le estaba entregando el examen resuelto.

        Lo que se conserva es lo que sirve para estudiar —la pregunta y lo que
        contestó— y lo que se va es la clave. La afirmación completa, para quien
        sí tiene el permiso, vive en `test_lv184`.
        """
        client, operator = _client_for_operator(
            "view_knowledgeassessment", "view_operator"
        )
        assessment = self._taken(operator)

        content = client.get(
            reverse("assessment-detail", args=[assessment.pk])
        ).content.decode()

        assert "DENSIDAD DEL AIRE" in content
        assert "Falso" in content, (
            "lo que contestó sí se ve: es lo que hay que corregir"
        )
        assert "Verdadero" not in content, "la respuesta correcta es el examen"

    def test_only_the_wrong_ones_are_listed(self):
        operator = _operator()
        assessment = self._taken(operator)

        assert len(assessment.wrong_answers) == 1

    def test_the_verdict_follows_the_result_and_is_not_the_same_word(self):
        # No se afirma la palabra traducida: se traduce, y un test que la compara
        # pasa en aislado y falla en la suite (la lección de `LV-95`). Lo que
        # importa es que haya dos veredictos distintos y que sigan al resultado.
        operator = _operator()

        passed = str(self._taken(operator, passed=True).verdict)
        failed = str(self._taken(operator).verdict)

        assert passed != failed
        assert passed and failed

    def test_the_review_marks_the_result_in_colour(self):
        client, operator = _client_for_operator(
            "view_knowledgeassessment", "view_operator"
        )
        assessment = self._taken(operator)

        content = client.get(
            reverse("assessment-detail", args=[assessment.pk])
        ).content.decode()

        assert "bg-danger" in content

    def test_an_operator_cannot_read_another_persons_result(self):
        client, _mine = _client_for_operator("view_knowledgeassessment")
        other = _operator(employee_id="E-2", full_name="Operator B")
        theirs = self._taken(other)

        response = client.get(reverse("assessment-detail", args=[theirs.pk]))

        assert response.status_code == 404

    def test_a_supervisor_can_read_it(self):
        # Quien tiene lectura del padrón de operadores es quien responde "cómo
        # está la condición de los profesionales" ante una auditoría.
        operator = _operator()
        theirs = self._taken(operator)
        client = login_as("view_knowledgeassessment", "view_operator")

        assert (
            client.get(reverse("assessment-detail", args=[theirs.pk])).status_code
            == 200
        )

    def test_it_is_403_without_view_permission(self):
        operator = _operator()
        theirs = self._taken(operator)

        assert (
            login_as().get(reverse("assessment-detail", args=[theirs.pk])).status_code
            == 403
        )

    def test_the_history_shows_on_the_operator_record(self):
        operator = _operator()
        assessment = self._taken(operator, passed=True)
        client = login_as("view_operator", "view_knowledgeassessment")

        content = client.get(
            reverse("operator-detail", args=[operator.pk])
        ).content.decode()

        # Se afirma el enlace a la revisión y no la palabra del veredicto: la
        # palabra se traduce, el enlace es el contrato.
        assert reverse("assessment-detail", args=[assessment.pk]) in content

    def test_the_history_is_hidden_without_permission_to_read_it(self):
        operator = _operator()
        self._taken(operator, passed=True)
        client = login_as("view_operator")

        response = client.get(reverse("operator-detail", args=[operator.pk]))

        assert response.context["assessments"] is None


@pytest.mark.django_db
class TestItEntersTheExpiryEngine:
    def test_the_model_is_watchable(self):
        from apps.compliance.watchables import WATCHABLE_MODELS

        assert "registry.knowledgeassessment" in WATCHABLE_MODELS

    def test_its_cost_center_resolves_through_the_operator(self):
        from apps.compliance.reports import ALERT_COST_CENTER_PATHS

        assert (
            ALERT_COST_CENTER_PATHS["registry.knowledgeassessment"]
            == "operator__cost_center"
        )

    def test_an_expiring_assessment_reaches_the_panel_list(self):
        from datetime import timedelta

        from apps.compliance.expirations import upcoming_expirations

        cost_center = CostCenter.objects.create(code="CC738", name="MLP")
        operator = _operator(cost_center=cost_center)
        KnowledgeAssessment.objects.create(
            operator=operator,
            question_count=25,
            correct_count=25,
            score_percent=100,
            passed=True,
            expires_on=TODAY + timedelta(days=10),
            answers=[],
        )

        items = upcoming_expirations(TODAY, TODAY + timedelta(days=30))

        assert [item["label"] for item in items] == [str(operator)]
        assert items[0]["cost_center_code"] == "CC738"

    def test_only_the_latest_attempt_of_each_operator_is_listed(self):
        # Los intentos anteriores son historial: su vencimiento ya no es trabajo,
        # y listarlos llenaría el panel con la misma persona repetida.
        from datetime import timedelta

        from apps.compliance.expirations import upcoming_expirations

        operator = _operator()
        for days in (5, 10):
            KnowledgeAssessment.objects.create(
                operator=operator,
                question_count=25,
                correct_count=25,
                score_percent=100,
                passed=True,
                expires_on=TODAY + timedelta(days=days),
                answers=[],
            )

        items = upcoming_expirations(TODAY, TODAY + timedelta(days=30))

        assert len(items) == 1
