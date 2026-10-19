from django.conf import settings
from django.http import Http404
from django.shortcuts import render
from django.views.decorators.http import require_POST
from django.utils.translation import gettext as _
from django.utils.decorators import method_decorator
from django.views import View

from apps.core.views import ModelViewPermissionRequiredMixin
from apps.operations.models import FlightPermission

from .service import MAX_QUESTION_CHARS, ask
from .tools import user_has_any_tool_permission


def assistant_available():
    """Encendido **y** (desarrollo/demo **o** producción autorizada aparte).

    El acceso gratuito a los modelos de NVIDIA es sólo para prototipos y pruebas; atender a
    usuarios reales es «producción» y exige licencia. Por eso, fuera de `DEBUG`, además de
    `AI_ASSISTANT_ENABLED` hace falta `AI_ASSISTANT_ALLOW_PRODUCTION` (apagado por omisión): la
    persona lo enciende sólo cuando tiene la licencia y la llave en el entorno de la VM.
    Apagado de emergencia: `AI_ASSISTANT_ENABLED=0` y reiniciar.
    """
    return bool(
        settings.AI_ASSISTANT_ENABLED
        and (settings.DEBUG or settings.AI_ASSISTANT_ALLOW_PRODUCTION)
    )


def _question_context(user, question):
    """El contexto de una pregunta: validada, y contestada si es válida. Lo comparten la pantalla
    sin JS y el fragmento del panel, para que midan igual."""
    context = {"max_chars": MAX_QUESTION_CHARS, "question": question}
    if not question:
        context["error"] = _("Write a question first.")
    elif len(question) > MAX_QUESTION_CHARS:
        context["error"] = _("The question is too long.")
    else:
        context["answer"] = ask(user, question)
    return context


class AssistantAsk(ModelViewPermissionRequiredMixin, View):
    """Pantalla de prototipo: una pregunta, una respuesta y qué herramientas se usaron.

    Exige `view_flightpermission`, como todo lector de permisos (contrato de `LV-268`): las tres
    herramientas hablan de permisos, y quien no puede verlos no tiene por qué preguntar por ellos.
    Además cada herramienta comprueba su propio permiso al ejecutarse.
    """

    model = FlightPermission
    template_name = "assistant/ask.html"

    def dispatch(self, request, *args, **kwargs):
        # 404 y no 403: apagado, esta pantalla no existe (y no anuncia que hay un asistente).
        if not assistant_available():
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        return render(request, self.template_name, {"max_chars": MAX_QUESTION_CHARS})

    def post(self, request):
        question = (request.POST.get("question") or "").strip()
        return render(
            request, self.template_name, _question_context(request.user, question)
        )


@method_decorator(require_POST, name="dispatch")
class AssistantPanelAsk(AssistantAsk):
    """Fragmento del panel lateral (`LV-332`): misma puerta, mismo permiso y misma pregunta que
    la pantalla, pero devuelve sólo `_answer.html`. POST con CSRF normal; nada se guarda.

    `require_POST` envuelve `dispatch`: un GET es 405 sin revelar nada; el 404 de «apagado» y el
    permiso los sigue poniendo `AssistantAsk`.
    """

    template_name = "assistant/_answer.html"

    def has_permission(self):
        # `LV-340`: el panel se dibuja con el permiso de AL MENOS una herramienta, así que su
        # fragmento acepta lo mismo; cada herramienta vuelve a comprobar el suyo. La pantalla
        # completa (`AssistantAsk`) conserva `view_flightpermission` por el contrato de `LV-268`.
        return user_has_any_tool_permission(self.request.user)
