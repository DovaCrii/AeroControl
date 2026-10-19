from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class AssistantUsage(BaseModel):
    """Un registro por pregunta al asistente: quién, qué herramientas, cuánto costó, cómo terminó.

    **No guarda la pregunta ni la respuesta**: una pregunta puede nombrar a alguien. Por eso no
    hay ningún campo de texto libre (`notes`, heredado de `BaseModel`, no se escribe nunca).
    Sirve además de contador de los topes por usuario/hora y global/día, compartido por todos
    los procesos (reemplaza la caché por proceso del PR 1).

    `rounds` cuenta las llamadas al servicio de esta pregunta (lo que se cobra contra el tope);
    se devuelve una cuando la llamada falló por red antes de responder.

    `vote` (LV-341) es el único juicio que se guarda sobre una respuesta: +1 o -1, nunca texto.

    `user` es SET_NULL (excepción documentada a PROTECT): el registro de uso debe sobrevivir a
    la persona, y archivar usuarios no es el único camino de borrado (el admin puede borrar).
    """

    OUTCOME_PENDING = "pending"
    OUTCOME_OK = "ok"
    OUTCOME_LIMIT = "limit"
    OUTCOME_429 = "error-429"
    OUTCOME_AUTH = "auth"
    OUTCOME_UNREACHABLE = "unreachable"
    OUTCOME_TOO_MANY_STEPS = "too-many-steps"
    OUTCOME_EMPTY = "empty"
    OUTCOME_ERROR = "error"
    OUTCOME_CHOICES = [
        (OUTCOME_PENDING, _("In progress")),
        (OUTCOME_OK, _("Answered")),
        (OUTCOME_LIMIT, _("Usage cap reached")),
        (OUTCOME_429, _("Service rate limit")),
        (OUTCOME_AUTH, _("Key not accepted")),
        (OUTCOME_UNREACHABLE, _("Service unreachable")),
        (OUTCOME_TOO_MANY_STEPS, _("Too many steps")),
        (OUTCOME_EMPTY, _("Empty answer")),
        (OUTCOME_ERROR, _("Other error")),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assistant_usages",
        verbose_name=_("User"),
    )
    tools = models.JSONField(default=list, blank=True, verbose_name=_("Tools used"))
    rounds = models.PositiveIntegerField(default=0, verbose_name=_("Service calls"))
    ms = models.PositiveIntegerField(default=0, verbose_name=_("Duration (ms)"))
    total_tokens = models.PositiveIntegerField(
        null=True, blank=True, verbose_name=_("Total tokens")
    )
    model = models.CharField(max_length=100, blank=True, verbose_name=_("Model"))
    outcome = models.CharField(
        max_length=20,
        choices=OUTCOME_CHOICES,
        default=OUTCOME_PENDING,
        verbose_name=_("Outcome"),
    )

    VOTE_UP = 1
    VOTE_DOWN = -1
    vote = models.SmallIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Vote"),
        help_text=_("+1 helpful, -1 not helpful. Never accompanied by free text."),
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("assistant usage")
        verbose_name_plural = _("assistant usage")
        indexes = [
            models.Index(fields=["user", "created_at"], name="assistant_user_time")
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    outcome__in=[
                        "pending",
                        "ok",
                        "limit",
                        "error-429",
                        "auth",
                        "unreachable",
                        "too-many-steps",
                        "empty",
                        "error",
                    ]
                ),
                name="assistant_usage_outcome_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(vote__isnull=True) | models.Q(vote__in=[-1, 1]),
                name="assistant_usage_vote_valid",
            ),
        ]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.outcome}"
