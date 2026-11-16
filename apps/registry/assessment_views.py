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
from django.db.models import Count
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views import View
from django.views.generic import DetailView, ListView

from apps.core.audit import set_audit_context
from apps.core.views import (
    ModelPermissionRequiredMixin,
    ModelViewPermissionRequiredMixin,
)

from apps.core.tenancy import scope_queryset_to_tenant

from . import assessments
from .models import AssessmentQuestion, KnowledgeAssessment, QualificationType

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
    """Elegir qué rendir, y la prueba en una sola página, un envío.

    Sin `?kind=` es la pantalla de elección (examen general, limitaciones y
    emergencias por modelo, cuestionario anual). Con `?kind=` arma el sorteo.

    Una pregunta por pantalla habría exigido guardar el avance a mitad de camino
    —el estado "en curso" que esta implementación evita— y no aporta nada: lo que
    se mide es el conocimiento, no la navegación.
    """

    model = KnowledgeAssessment
    permission_action = "add"
    template_name = "registry/assessment_take.html"
    choose_template_name = "registry/assessment_choose.html"

    def _choose(self, request, operator):
        families = QualificationType.objects.filter(is_active=True).order_by("name")
        bank_loaded = AssessmentQuestion.objects.filter(is_active=True).exists()
        return render(
            request,
            self.choose_template_name,
            {
                "title": _("Knowledge assessment"),
                "operator": operator,
                "families": families,
                "bank_loaded": bank_loaded,
                "kinds": [
                    {
                        "kind": kind,
                        "label": assessments.KIND_LABELS[kind],
                        "needs_family": kind in assessments.FAMILY_KINDS,
                        "parts": assessments.plan_for(kind),
                    }
                    for kind in ("general", "limitations", "annual")
                ],
                "can_see_bank": request.user.has_perm(
                    "registry.view_assessmentquestion"
                ),
            },
        )

    def get(self, request):
        operator = self.operator_or_none()
        if operator is None:
            return self.no_operator()
        kind = request.GET.get("kind", "")
        if not kind:
            return self._choose(request, operator)
        if kind not in assessments.PLANS:
            messages.error(request, _("Unknown assessment type."))
            return redirect("assessment-take")
        family = None
        if kind in assessments.FAMILY_KINDS:
            family = QualificationType.objects.filter(
                is_active=True, pk=request.GET.get("family") or 0
            ).first()
            if family is None:
                messages.error(request, _("Choose the RPA model for this assessment."))
                return redirect("assessment-take")
        if not assessments.bank_is_available(kind, family):
            messages.error(request, _("The question bank is not loaded."))
            return redirect("assessment-take")
        drawn = assessments.draw_questions(kind, family)
        # El sorteo se guarda para que recargar la página no cambie las preguntas
        # a mitad de prueba, y para poder corregir contra lo que de verdad se
        # preguntó.
        request.session[SESSION_KEY] = {
            "kind": kind,
            "family": str(family.pk) if family else None,
            "parts": {
                part: [question["id"] for question in questions]
                for part, questions in drawn.items()
            },
        }
        number = 0
        parts = []
        for plan in assessments.plan_for(kind):
            questions = []
            for question in drawn[plan.part]:
                number += 1
                questions.append({**question, "number": number})
            parts.append(
                {"part": plan.part, "threshold": plan.threshold, "questions": questions}
            )
        return render(
            request,
            self.template_name,
            {
                "title": _("Knowledge assessment"),
                "operator": operator,
                "kind": kind,
                "kind_label": assessments.KIND_LABELS[kind],
                "family": family,
                "parts": parts,
                "total": number,
                "valid_months": assessments.VALID_MONTHS if kind == "annual" else None,
            },
        )

    def post(self, request):
        operator = self.operator_or_none()
        if operator is None:
            return self.no_operator()
        drawn = request.session.get(SESSION_KEY) or {}
        parts = drawn.get("parts") if isinstance(drawn, dict) else None
        if not parts or drawn.get("kind") not in assessments.PLANS:
            # La sesión expiró, o alguien llegó al POST sin pasar por el sorteo.
            # No se corrige nada a ciegas: se vuelve a elegir.
            messages.info(request, _("The assessment expired. Choose it again."))
            return redirect("assessment-take")
        kind = drawn["kind"]
        family = (
            QualificationType.objects.filter(pk=drawn.get("family")).first()
            if kind in assessments.FAMILY_KINDS
            else None
        )
        if kind in assessments.FAMILY_KINDS and family is None:
            messages.info(request, _("The assessment expired. Choose it again."))
            return redirect("assessment-take")

        question_ids = [qid for ids in parts.values() for qid in ids]
        given = {
            question_id: request.POST.get(f"q{question_id}", "")
            for question_id in question_ids
        }
        rows, part_scores, passed, correct, total = assessments.grade_attempt(
            kind, parts, given
        )
        percent = round(correct * 100 / (total or 1), 1)
        assessment = KnowledgeAssessment.objects.create(
            operator=operator,
            taken_by_user=request.user,
            kind=kind,
            aircraft_family=family,
            question_count=total,
            correct_count=correct,
            score_percent=percent,
            part_scores=part_scores,
            passed=passed,
            expires_on=assessments.validity_for(kind, timezone.localdate()),
            answers=rows,
        )
        request.session.pop(SESSION_KEY, None)
        set_audit_context(
            request,
            assessment,
            action="knowledge_assessment_taken",
            metadata={"kind": kind, "score": str(percent), "passed": passed},
        )
        return redirect("assessment-detail", pk=assessment.pk)


class KnowledgeAssessmentDetail(ModelViewPermissionRequiredMixin, DetailView):
    """El resultado: puntaje por parte, veredicto y **en qué se equivocó**.

    Lo que se refuerza es la lista de incorrectas. Sale de la copia que el intento
    guardó, así que sigue diciendo lo que pasó aunque el banco se haya corregido
    después.
    """

    model = KnowledgeAssessment
    template_name = "registry/assessment_detail.html"
    context_object_name = "assessment"

    def get_queryset(self):
        # Cada quien ve lo suyo; ver el historial ajeno exige el permiso de
        # lectura sobre operadores, que es el que tiene quien supervisa.
        queryset = scope_queryset_to_tenant(
            super()
            .get_queryset()
            .select_related("operator", "taken_by_user", "aircraft_family"),
            self.request.user,
            "operator__tenant_id",  # LV-372 (F-08): el intento es de la empresa de su operador
        )
        if self.request.user.has_perm("registry.view_operator"):
            return queryset
        operator = getattr(self.request.user, "operator_profile", None)
        return queryset.filter(operator=operator) if operator else queryset.none()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = _("Knowledge assessment")
        assessment = context["assessment"]
        # Un intento previo a LV-444 se evaluó con el 80 % de entonces.
        context["pass_percent"] = (
            assessments.LEGACY_PASS_PERCENT if assessment.kind == "legacy" else None
        )
        context["part_rows"] = [
            {"part": part, **score}
            for part, score in sorted((assessment.part_scores or {}).items())
        ]
        return context


class AssessmentBankList(ModelViewPermissionRequiredMixin, ListView):
    """El banco cargado: cuántas preguntas hay por tipo y modelo, y su lista.

    Lectura sólo con `view_assessmentquestion`. **La clave se ve únicamente con
    `view_assessment_answers`**: el listado sin ese permiso muestra enunciados y
    opciones, no la respuesta (LV-184: la clave es el examen). El banco es de toda
    la empresa, no de un tenant: lo carga un comando, no un usuario.
    """

    model = AssessmentQuestion
    template_name = "registry/assessment_bank_list.html"
    context_object_name = "questions"
    paginate_by = 50

    def get_queryset(self):
        queryset = super().get_queryset().select_related("aircraft_family")
        kind = self.request.GET.get("kind")
        if kind in dict(AssessmentQuestion.KIND_CHOICES):
            queryset = queryset.filter(kind=kind)
        if self.request.GET.get("archived") == "1":
            return queryset.filter(is_active=False)
        return queryset.filter(is_active=True)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = _("Question bank")
        context["show_answers"] = self.request.user.has_perm(
            "registry.view_assessment_answers"
        )
        context["kind_choices"] = AssessmentQuestion.KIND_CHOICES
        context["totals"] = [
            {
                "kind": dict(AssessmentQuestion.KIND_CHOICES)[row["kind"]],
                "family": row["aircraft_family__name"] or "",
                "count": row["count"],
            }
            for row in AssessmentQuestion.objects.filter(is_active=True)
            .values("kind", "aircraft_family__name")
            .annotate(count=Count("pk"))
            .order_by("kind", "aircraft_family__name")
        ]
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
