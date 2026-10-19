from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class UserWeatherLocation(BaseModel):
    """La ciudad predeterminada del widget del tiempo de **una** persona.

    Es informativo y personal: no se cruza con permisos de vuelo ni con ninguna regla de
    cumplimiento. Sin tenant, porque la fila es de la propia persona y las vistas sólo operan
    sobre la fila de `request.user`.

    `user` es **CASCADE** (excepción documentada a PROTECT, AGENTS.md): es una preferencia sin
    valor de evidencia, como una sesión. Nadie la audita ni la cita, y que borrar a una persona
    quedara bloqueado por su ciudad favorita sería un estorbo sin beneficio. La traza de cuándo
    se cambió vive en `AuditEvent`, que no depende de esta fila.

    `cost_center` queda como referencia de origen cuando la ciudad salió de una faena. Es
    PROTECT por convención: las faenas se archivan, no se borran. Las coordenadas **se copian**
    y no se leen de la faena, de modo que editar o archivar la faena no mueve el widget de
    nadie sin que lo sepa.
    """

    SOURCE_COST_CENTER = "cost_center"
    SOURCE_SEARCH = "search"
    SOURCE_CHOICES = [
        (SOURCE_COST_CENTER, _("Site")),
        (SOURCE_SEARCH, _("Search")),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="weather_location",
    )
    label = models.CharField(max_length=120, verbose_name=_("City"))
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        validators=[
            MinValueValidator(Decimal("-90")),
            MaxValueValidator(Decimal("90")),
        ],
        verbose_name=_("Latitude"),
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        validators=[
            MinValueValidator(Decimal("-180")),
            MaxValueValidator(Decimal("180")),
        ],
        verbose_name=_("Longitude"),
    )
    timezone = models.CharField(max_length=64, blank=True, verbose_name=_("Time zone"))
    source = models.CharField(
        max_length=20, choices=SOURCE_CHOICES, verbose_name=_("Source")
    )
    cost_center = models.ForeignKey(
        "registry.CostCenter",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("Site"),
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(latitude__gte=-90, latitude__lte=90),
                name="weather_location_latitude_range",
            ),
            models.CheckConstraint(
                condition=Q(longitude__gte=-180, longitude__lte=180),
                name="weather_location_longitude_range",
            ),
            models.CheckConstraint(
                condition=Q(source="search") | Q(cost_center__isnull=False),
                name="weather_location_site_has_cost_center",
            ),
        ]

    def __str__(self):
        return f"{self.user_id}: {self.label}"

    def clean(self):
        super().clean()
        if self.source == self.SOURCE_COST_CENTER and self.cost_center_id is None:
            raise ValidationError(
                {
                    "cost_center": _(
                        "A site is required when the city comes from a site."
                    )
                }
            )
