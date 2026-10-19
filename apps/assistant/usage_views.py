"""LV-341: observabilidad del uso del asistente y voto de utilidad.

Dos vistas, ninguna toca ni muestra texto de preguntas, respuestas, argumentos de herramientas
ni citas: `AssistantUsage` no los guarda y aquí sólo se cuentan filas.

- `AssistantUsageView` (`/assistant/usage/`): lectura, exige `assistant.view_assistantusage`.
  `AssistantUsage` **no tiene tenant**, así que es global para quien tenga el permiso: no hay
  nada que acotar por empresa (documentado en `docs/dev/asistente-ia.md`).
- `AssistantVote` (`/assistant/vote/`): POST con CSRF; recibe un `usage_id` **firmado** y un voto
  de +1 o -1. Sólo vota quien hizo la pregunta.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import render
from django.utils import timezone
from django.views import View
from django.views.decorators.http import require_POST
from django.utils.decorators import method_decorator

from apps.core.audit import set_audit_context
from apps.core.views import ModelViewPermissionRequiredMixin
from apps.operations.models import FlightPermission

from .models import AssistantUsage
from .tools import user_has_any_tool_permission
from .views import assistant_available

logger = logging.getLogger(__name__)

VOTE_SALT = "assistant.vote"
VOTE_MAX_AGE = 3600  # una hora para votar una respuesta
WARN_RATIO = 0.8
DAYS = 14


def sign_usage_id(usage):
    """Token firmado que el fragmento de respuesta lleva para votar esa pregunta.

    Ata el registro **y** a quien preguntó: un token filtrado no sirve a otra persona.
    """
    return signing.dumps({"u": str(usage.pk), "p": usage.user_id}, salt=VOTE_SALT)


def _gate(request):
    # 404 y no 403: apagado, esta ruta no existe.
    if not assistant_available():
        raise Http404


class AssistantUsageView(ModelViewPermissionRequiredMixin, View):
    """Cuánto se usa el asistente: por día, por persona y por resultado. Sólo lectura."""

    model = AssistantUsage
    template_name = "assistant/usage.html"

    def dispatch(self, request, *args, **kwargs):
        _gate(request)
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        now = timezone.localtime()
        today = now.date()
        since = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(
            days=DAYS - 1
        )
        rows = AssistantUsage.objects.filter(created_at__gte=since)

        by_day = {
            r["day"]: r
            for r in rows.annotate(day=TruncDate("created_at"))
            .values("day")
            .annotate(
                questions=Count("pk"),
                calls=Sum("rounds"),
                tokens=Sum("total_tokens"),
            )
        }
        days = []
        for offset in range(DAYS):
            day = today - timedelta(days=offset)
            row = by_day.get(day, {})
            days.append(
                {
                    "day": day,
                    "questions": row.get("questions", 0),
                    "calls": row.get("calls") or 0,
                    "tokens": row.get("tokens") or 0,
                }
            )
        outcomes = dict(AssistantUsage.OUTCOME_CHOICES)
        by_outcome = [
            {"label": outcomes.get(r["outcome"], r["outcome"]), "questions": r["n"]}
            for r in rows.values("outcome").annotate(n=Count("pk")).order_by("-n")
        ]
        by_user = [
            {
                "user": r["user__username"],
                "questions": r["n"],
                "calls": r["calls"] or 0,
                "tokens": r["tokens"] or 0,
            }
            for r in rows.values("user__username")
            .annotate(n=Count("pk"), calls=Sum("rounds"), tokens=Sum("total_tokens"))
            .order_by("-n")
        ]
        cap = settings.AI_ASSISTANT_DAILY_CAP
        used_today = days[0]["calls"]
        percent = round(used_today * 100 / cap) if cap else None
        warn = bool(cap) and used_today >= WARN_RATIO * cap
        if warn:
            self._warn_once(today, used_today, cap)
        return render(
            request,
            self.template_name,
            {
                "days": days,
                "by_outcome": by_outcome,
                "by_user": by_user,
                "total_tokens": sum(d["tokens"] for d in days),
                "total_questions": sum(d["questions"] for d in days),
                "cap": cap,
                "used_today": used_today,
                "percent": percent,
                "warn": warn,
                "window_days": DAYS,
            },
        )

    @staticmethod
    def _warn_once(today, used, cap):
        """Un aviso al log por día: `cache.add` es atómico y sólo el primero lo consigue.

        Con la caché por proceso (locmem) puede salir una vez por proceso y día; con una caché
        compartida, una sola. Sólo cifras: ningún texto ni persona.
        """
        if cache.add(f"assistant_daily_cap_80:{today.isoformat()}", 1, 60 * 60 * 26):
            logger.warning(
                "assistant_daily_cap_80",
                extra={"used": used, "cap": cap, "day": today.isoformat()},
            )


@method_decorator(require_POST, name="dispatch")
class AssistantVote(ModelViewPermissionRequiredMixin, View):
    """Voto de utilidad (+1/-1) sobre una respuesta propia. Sin texto, jamás.

    Misma puerta que el panel y `AssistantPanelAsk` (`LV-340`): el permiso de AL MENOS una
    herramienta; quien ve los botones de voto puede votar. Sigue bajo el mixin de `LV-268`.
    Una firma caducada o alterada, un voto fuera de ±1 o un registro de otra persona se
    rechazan; el ajeno da 404 para no confirmar que existe. El voto se puede cambiar.
    """

    model = FlightPermission

    def has_permission(self):
        return user_has_any_tool_permission(self.request.user)

    def dispatch(self, request, *args, **kwargs):
        _gate(request)
        return super().dispatch(request, *args, **kwargs)

    def post(self, request):
        try:
            payload = signing.loads(
                request.POST.get("usage_id", ""),
                salt=VOTE_SALT,
                max_age=VOTE_MAX_AGE,
            )
            vote = int(request.POST.get("vote", ""))
        except (signing.BadSignature, ValueError, TypeError):
            return HttpResponseBadRequest()
        if vote not in (AssistantUsage.VOTE_UP, AssistantUsage.VOTE_DOWN):
            return HttpResponseBadRequest()
        usage = AssistantUsage.objects.filter(
            pk=payload.get("u"), user_id=request.user.pk
        ).first()
        if usage is None or payload.get("p") != request.user.pk:
            raise Http404
        usage.vote = vote
        usage.save(update_fields=["vote", "updated_at"])
        set_audit_context(
            request, usage, action="assistant_voted", metadata={"vote": vote}
        )
        return HttpResponse(status=204)
