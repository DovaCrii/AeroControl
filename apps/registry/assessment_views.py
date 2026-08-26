"""LV-158: rendir la prueba de conocimientos y leer su resultado.

Tres pantallas y ninguna más: rendir, ver el resultado, y el historial en la
ficha del operador (que ya existe y sólo gana una sección).

**Para entrar hay que ser el operador**, que es el pedido textual: *"para ingresar
se debe […] ligar con las credenciales del operador"*. El vínculo ya existía sin
usarse para esto: `Operator.user` es un `OneToOne` que `B3.2` creó para "Mi
trabajo". Así el intento no se puede atribuir a otra persona: no hay un selector
de operador que alguien pueda cambiar.

**El sorteo vive en la sesión, no en el formulario.** Si las 25 preguntas viajaran
en un campo oculto, cualquiera podría cambiarlas por 25 fáciles; y si se creara
una fila "en curso" en la base, cada prueba abandonada dejaría basura que después
hay que distinguir de una rendida. La sesión es de esa persona, no se puede
manipular desde el navegador, y si abandona simplemente desaparece.
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views import View
from django.views.generic import DetailView

from apps.core.audit import set_audit_context
from apps.core.views import (
    ModelPermissionRequiredMixin,
    ModelViewPermissionRequiredMixin,
)

from . import assessments
from .models import KnowledgeAssessment

SESSION_KEY = "knowledge_assessment_questions"


class OperatorSelfMixin(LoginRequiredMixin):
    """El operador de quien está con la sesión abierta, o un mensaje que lo explica.

    Sin `Operator.user` no hay a quién atribuir el intento, y adivinar por correo
    es justo lo que el modelo se negó a hacer (`B3.2`): un correo desactualizado o
    compartido enlazaría a la persona equivocada, y acá eso escribiría una
    evaluación en el historial de otro.
    """

    def operator_or_none(self):
        return getattr(self.request.user, "operator_profile", None)

    def no_operator(self):
        messages.error(
            self.request,
            _(
                "Your user is not linked to an operator record, so there is "
                "nowhere to file the result. Ask for the link to be set on the "
                "operator's record."
            ),
        )
        return redirect("dashboard")


class KnowledgeAssessmentTake(OperatorSelfMixin, ModelPermissionRequiredMixin, View):
    """La prueba en una sola página: 25 preguntas, un envío.

    Una pregunta por pantalla habría exigido guardar el avance a mitad de camino
    —o sea el estado "en curso" que esta implementación evita— y no aporta nada:
    lo que se mide es el conocimiento, no la navegación.
    """

    model = KnowledgeAssessment
    permission_action = "add"
    template_name = "registry/assessment_take.html"

    def get(self, request):
        operator = self.operator_or_none()
        if operator is None:
            return self.no_operator()
        if not assessments.bank_is_available():
            messages.error(request, _("The question bank is not available right now."))
            return redirect("dashboard")
        questions = assessments.draw_questions()
        # El sorteo se guarda para que recargar la página no cambie las preguntas
        # a mitad de prueba, y para poder corregir contra lo que de verdad se
        # preguntó.
        request.session[SESSION_KEY] = [question["id"] for question in questions]
        return render(
            request,
            self.template_name,
            {
                "title": _("Knowledge assessment"),
                "operator": operator,
                "questions": questions,
                "pass_percent": assessments.PASS_PERCENT,
                "valid_months": assessments.VALID_MONTHS,
            },
        )

    def post(self, request):
        operator = self.operator_or_none()
        if operator is None:
            return self.no_operator()
        question_ids = request.session.get(SESSION_KEY) or []
        if not question_ids:
            # La sesión expiró, o alguien llegó al POST sin pasar por el sorteo.
            # No se corrige nada a ciegas: se vuelve a sortear.
            messages.info(
                request, _("The assessment expired. Here is a new set of questions.")
            )
            return redirect("assessment-take")

        given = {
            question_id: request.POST.get(f"q{question_id}", "")
            for question_id in question_ids
        }
        rows, correct, percent, passed = assessments.grade(question_ids, given)
        assessment = KnowledgeAssessment.objects.create(
            operator=operator,
            taken_by_user=request.user,
            question_count=len(rows),
            correct_count=correct,
            score_percent=percent,
            passed=passed,
            expires_on=assessments.valid_until(timezone.localdate()),
            answers=rows,
        )
        request.session.pop(SESSION_KEY, None)
        set_audit_context(
            request,
            assessment,
            action="knowledge_assessment_taken",
            metadata={"score": str(percent), "passed": passed},
        )
        return redirect("assessment-detail", pk=assessment.pk)


class KnowledgeAssessmentDetail(ModelViewPermissionRequiredMixin, DetailView):
    """El resultado: puntaje, veredicto y **en qué se equivocó**.

    Lo que se refuerza es la lista de incorrectas con su respuesta correcta al
    lado. Sale de la copia que el intento guardó, así que sigue diciendo lo que
    pasó aunque el banco se haya corregido después.
    """

    model = KnowledgeAssessment
    template_name = "registry/assessment_detail.html"
    context_object_name = "assessment"

    def get_queryset(self):
        # Cada quien ve lo suyo; ver el historial ajeno exige el permiso de
        # lectura sobre operadores, que es el que tiene quien supervisa.
        queryset = super().get_queryset().select_related("operator", "taken_by_user")
        if self.request.user.has_perm("registry.view_operator"):
            return queryset
        operator = getattr(self.request.user, "operator_profile", None)
        return queryset.filter(operator=operator) if operator else queryset.none()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = _("Knowledge assessment")
        context["pass_percent"] = assessments.PASS_PERCENT
        return context


def assessment_rows_for(operator):
    """El historial de la ficha del operador, más reciente primero."""
    return operator.knowledge_assessments.filter(is_active=True).order_by("-taken_at")


class KnowledgeAssessmentStart(OperatorSelfMixin, View):
    """Entrada desde la ficha o el menú: manda a rendir, o explica por qué no.

    Existe para que el enlace pueda ofrecerse sin permiso de escritura y sea la
    pantalla la que explique el porqué, en vez de un 403 sin contexto.
    """

    def get(self, request):
        if not request.user.has_perm("registry.add_knowledgeassessment"):
            messages.error(
                request, _("You do not have permission to take the assessment.")
            )
            return redirect("dashboard")
        return redirect("assessment-take")
