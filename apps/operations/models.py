from datetime import datetime, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.db.models import Q
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from apps.core.choices import PURPOSE_CHOICES
from apps.core.models import BaseModel, StatusFlowMixin
from apps.registry.models import Operator, Aircraft, CostCenter


class FlightPermission(StatusFlowMixin, BaseModel):
    """A flight authorization, mirroring the real DGAC document (OPS-4).

    A single authorization typically lists several operators and several
    aircraft over a validity range (docs/dev/ops-contract-tracking-plan.md),
    not one of each on one day -- the previous single-FK/single-date shape
    could not represent that. `cost_center` stays a single FK: the scoping
    unit is unambiguous even when the crew/fleet is a roster.
    """

    STATUS_REQUESTED = "requested"
    STATUS_APPROVED = "approved"
    STATUS_DENIED = "denied"
    STATUS_COMPLETED = "completed"
    # LV-83: the authorization's validity ran out. **Deliberately not the same
    # as "completed"**, decided with the user: completed means the authorized
    # work was flown and the signed DGAC authorization is on file (R2.4 refuses
    # the transition without it), while expired only means the window closed --
    # and a permit can expire having flown nothing at all. Merging them would
    # also break `on_time_execution`, whose whole question is which expired
    # permits had no flight against them.
    STATUS_EXPIRED = "expired"
    STATUS_CHOICES = [
        (STATUS_REQUESTED, _("Requested")),
        (STATUS_APPROVED, _("Approved")),
        (STATUS_DENIED, _("Denied")),
        (STATUS_COMPLETED, _("Completed")),
        # With context: "Expired" already exists in the catalog as the *plural*
        # count of lapsed qualifications on the operator fiche ("Vencidos"), and
        # without `msgctxt` this status would inherit that wording.
        (STATUS_EXPIRED, pgettext_lazy("permit status", "Expired")),
    ]
    # LV-72: the order the statuses actually advance in, read by
    # StatusFlowMixin.status_steps(). Declared here, next to the choices it
    # draws from, and **never as a literal list in a template** -- that is
    # precisely the R1.1 defect (the calendar carried 7 hand-written event
    # types that drifted from the 9 real ones). `denied` is deliberately out of
    # the flow: it is not a step on the way anywhere, it is where it stops.
    # LV-90: where this record stops being "open" for the alert engine. Declared
    # next to the choices, because a literal list living inside generate_alerts
    # is a list somebody has to remember to edit -- and forgetting it fails
    # silently, as alerts for an authorization that is already over.
    TERMINAL_STATUSES = frozenset({STATUS_DENIED, STATUS_COMPLETED, STATUS_EXPIRED})
    STATUS_FLOW = [STATUS_REQUESTED, STATUS_APPROVED, STATUS_COMPLETED]
    # Two terminal states now (LV-83). They differ in one way that matters for
    # the stepper: `denied` is only ever reached from the first step, while a
    # permit can expire from anywhere -- see `status_steps` below.
    STATUS_BLOCKED = [STATUS_DENIED, STATUS_EXPIRED]
    # R2.6: DAN 151 (populated area) vs DAN 91 (unpopulated) is a real
    # normative distinction (ISO 9001/45001 audit guide, clause 6.1.3), not
    # a boolean -- a single survey can cross both, which "mixed" exists to
    # record. Decided 2026-08-07: just the fact, no extra document
    # requirement yet (what DAN 151 demands beyond this is defined later,
    # once confirmed against the edition in force).
    AREA_TYPE_CHOICES = [
        ("populated", _("Populated area")),
        ("unpopulated", _("Unpopulated area")),
        ("mixed", _("Mixed (crosses both)")),
    ]
    # R2.2/R2.3: the identifier every screen actually needs is this one, not
    # the DGAC folio below -- a permit exists (and needs a title on the
    # calendar, the list, its geo plan) long before the DGAC ever assigns a
    # number. Annual correlative ("JEJ-2026-001") because the year is enough
    # to place it in time, same as the DGAC resoluciones the operation
    # already handles. Assigned once in save() below, never blank, never
    # user-editable (excluded from FlightPermissionForm).
    internal_folio = models.CharField(max_length=20, unique=True, editable=False)
    # LV-39: optional until the permit is approved, so a permit can be drafted
    # ("requested") or recorded as "denied" before the DGAC folio exists. null
    # (not "") so several folio-less permits don't collide on the unique index.
    permission_number = models.CharField(
        max_length=50, unique=True, null=True, blank=True
    )
    operators = models.ManyToManyField(Operator, related_name="flight_permissions")
    aircraft_fleet = models.ManyToManyField(Aircraft, related_name="flight_permissions")
    cost_center = models.ForeignKey(CostCenter, on_delete=models.PROTECT)
    # R3.1: closed vocabulary (the 2 SIGO procedures under DAN 137 Cap. J,
    # confirmed against real data + the user directly -- see
    # apps.core.choices) instead of free text, so a calendar/list title
    # built from `purpose` cannot drift into whatever wording someone typed
    # ("Audiovisual" told nobody which procedure it actually was).
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES)
    purpose_detail = models.CharField(max_length=250, blank=True, default="")
    # Immutable historical record of what this field held before R3.1 --
    # same criterion as CostCenter.responsible: never shown as the primary
    # value, never edited, kept only so the original SIGO wording is not
    # lost to a backfill's best-effort classification.
    purpose_legacy = models.CharField(
        max_length=250, blank=True, default="", editable=False
    )
    valid_from = models.DateField()
    valid_until = models.DateField()
    location = models.CharField(max_length=250)
    # OPS-4 structured location (docs/dev/ops-contract-tracking-plan.md §1.4),
    # deferred when the rest of OPS-4 landed and picked up here. It
    # *complements* `location` rather than replacing it: the free-text field
    # keeps the exact wording of the DGAC authorization, while these add the
    # administrative breakdown and, optionally, the point/area the flight
    # covers so it can later cross-reference the GEO plan for the same site.
    # All optional -- an older permit whose paperwork only ever said
    # "Chuquicamata" is not retroactively incomplete.
    region = models.CharField(max_length=100, blank=True)
    commune = models.CharField(max_length=100, blank=True)
    area_name = models.CharField(max_length=200, blank=True)
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        validators=[
            MinValueValidator(Decimal("-90")),
            MaxValueValidator(Decimal("90")),
        ],
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        validators=[
            MinValueValidator(Decimal("-180")),
            MaxValueValidator(Decimal("180")),
        ],
    )
    radius_km = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    max_altitude_ft = models.PositiveIntegerField(null=True, blank=True)
    # Nullable so the permissions created before this field existed are not
    # retroactively broken; the form requires it (blank=False, the default)
    # for anything created or edited from now on.
    area_type = models.CharField(max_length=20, choices=AREA_TYPE_CHOICES, null=True)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="requested"
    )

    class Meta:
        verbose_name = _("flight permission")
        verbose_name_plural = _("flight permissions")
        # The calendar filters (valid_from/valid_until, is_active) on every
        # feed request, as a range-overlap query.
        indexes = [
            models.Index(
                fields=["valid_from", "valid_until", "is_active"],
                name="ops_permission_range_idx",
            )
        ]
        # R3.1: enforced at the DB level, not just the form -- the admin,
        # a script or a future import must not be able to save "other"
        # without a detail either.
        constraints = [
            models.CheckConstraint(
                condition=~Q(purpose="other") | ~Q(purpose_detail=""),
                name="ops_flightpermission_other_purpose_requires_detail",
            )
        ]

    def __str__(self):
        # R2.3: was `permission_number or f"{status} · {purpose[:30]}"` --
        # purpose leaked into the list/calendar/geo-plan titles as a
        # de-facto identifier for any permit without a DGAC folio yet.
        # internal_folio is assigned at creation and never blank, so
        # purpose goes back to being plain data.
        return self.internal_folio

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("permission-detail", kwargs={"pk": self.pk})

    def status_steps(self):
        """LV-83: how far it got before it stopped, not just that it stopped.

        The mixin's default collapses a blocked record to "first step + where it
        stopped", which was right while `denied` was the only terminal state --
        it can only be reached from `requested`. An expired permit can have been
        approved, and showing it as "Solicitado ✕ Caducado" would hide that the
        DGAC had authorized it, which is exactly the fact an auditor is looking
        for. The history knows which status it was moved away from.
        """
        from apps.core.models import status_steps_for

        reached = None
        if self.pk and self.status in self.STATUS_BLOCKED:
            stopping_row = self.history.filter(new_status=self.status).first()
            reached = stopping_row.previous_status if stopping_row else None
        return status_steps_for(
            choices=self.STATUS_CHOICES,
            flow=self.STATUS_FLOW,
            current=self.status,
            blocked=self.STATUS_BLOCKED,
            reached=reached,
        )

    @staticmethod
    def _next_internal_folio():
        """Annual correlative, safe under concurrent creation.

        `select_for_update()` locks the current-year rows within this
        transaction so two permits created at the same moment cannot both
        compute the same next number -- the second blocks until the first
        commits. The one gap this does not close is the very first permit
        of a new year (nothing to lock yet); the `unique` constraint turns
        that rare race into a failed save instead of a silent duplicate.
        """
        prefix = f"JEJ-{timezone.now().year}-"
        last = (
            FlightPermission.objects.select_for_update()
            .filter(internal_folio__startswith=prefix)
            .order_by("-internal_folio")
            .first()
        )
        next_seq = int(last.internal_folio[len(prefix) :]) + 1 if last else 1
        return f"{prefix}{next_seq:03d}"

    def save(self, *args, **kwargs):
        if self._state.adding and not self.internal_folio:
            with transaction.atomic():
                self.internal_folio = self._next_internal_folio()
                return super().save(*args, **kwargs)
        return super().save(*args, **kwargs)

    def clean(self):
        errors = {}
        if self.valid_until and self.valid_from and self.valid_until < self.valid_from:
            errors["valid_until"] = _("The end date cannot be before the start date.")
        if self.purpose == "other" and not self.purpose_detail:
            errors["purpose_detail"] = _(
                "Describe the purpose when 'Other' is selected."
            )
        # A lone coordinate cannot be plotted; require the pair together so a
        # half-entered point does not silently fail to show on a future map.
        if (self.latitude is None) != (self.longitude is None):
            message = _("Latitude and longitude must be entered together.")
            errors["latitude"] = message
            errors["longitude"] = message
        if self.radius_km is not None and self.latitude is None:
            errors["radius_km"] = _("A radius requires a coordinate pair.")
        if errors:
            raise ValidationError(errors)


class FlightRecord(BaseModel):
    permission = models.ForeignKey(
        FlightPermission, on_delete=models.PROTECT, related_name="records"
    )
    actual_date = models.DateField()
    departure_time = models.TimeField()
    arrival_time = models.TimeField()
    pilot = models.ForeignKey(Operator, on_delete=models.PROTECT)
    aircraft = models.ForeignKey(
        Aircraft, on_delete=models.PROTECT, related_name="flight_records"
    )

    class Meta:
        # LV-80: without these the screen title falls back to Django's English
        # derivation of the class name ("Flight record" / "Flight records").
        verbose_name = _("flight record")
        verbose_name_plural = _("flight records")
        # The table that grows per flight; the calendar scans it by date.
        indexes = [
            models.Index(
                fields=["actual_date", "is_active"], name="ops_record_date_idx"
            )
        ]

    def __str__(self):
        return f"{self.aircraft} · {self.actual_date}"

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("record-detail", kwargs={"pk": self.pk})

    @property
    def duration(self):
        """LV-59: departure/arrival are stored but nothing ever computed the
        flight's actual length from them. `FlightRecordForm.clean()` rejects
        arrival <= departure at the form, but that is not a model-level
        constraint (a record created via the admin or a fixture has no such
        guard) -- an arrival not later than departure is treated as a flight
        that crossed midnight, not a negative duration."""
        anchor = datetime.combine(self.actual_date, self.departure_time)
        end = datetime.combine(self.actual_date, self.arrival_time)
        if end <= anchor:
            end += timedelta(days=1)
        return end - anchor

    @property
    def duration_display(self):
        """`duration` as "1h 05min" (or "05min" under an hour) for the list
        and detail pages -- a raw timedelta renders as "1:05:00" in a
        template, which reads as a clock, not a length."""
        from .selectors import format_duration

        return format_duration(self.duration)


class PermissionHistory(BaseModel):
    # `created_at` alone cannot order two rows created moments apart: on this
    # machine `timezone.now()` returns the *identical* value across rapid
    # successive calls, and SQL gives no ordering guarantee for ties on a
    # non-unique column. `sequence` is computed in save() as "latest + 1"
    # (same idiom as GeoPlanVersion.version_number / ResourceMovementLog).
    sequence = models.PositiveBigIntegerField(editable=False, default=0)
    permission = models.ForeignKey(
        FlightPermission, on_delete=models.PROTECT, related_name="history"
    )
    # R2.5: found while verifying the status-history table -- neither field
    # declared `choices`, so `get_previous_status_display`/
    # `get_new_status_display` were never generated by Django at all. The
    # template's `{{ h.get_previous_status_display|default:h.previous_status }}`
    # silently fell through to the raw stored value every time ("requested",
    # "denied"), which is why the history table showed English status codes
    # in an otherwise all-Spanish page.
    previous_status = models.CharField(
        max_length=20, choices=FlightPermission.STATUS_CHOICES
    )
    new_status = models.CharField(
        max_length=20, choices=FlightPermission.STATUS_CHOICES
    )
    changed_by = models.CharField(max_length=150)
    changed_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="permission_history_events",
    )
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = "Permission histories"
        ordering = ["-sequence"]

    def __str__(self):
        return f"{self.permission}: {self.previous_status} → {self.new_status}"

    def save(self, *args, **kwargs):
        if self._state.adding:
            latest = PermissionHistory.objects.order_by("-sequence").first()
            self.sequence = (latest.sequence if latest else 0) + 1
        return super().save(*args, **kwargs)


class WorkAreaType(BaseModel):
    """R9.3: "Área de Trabajo" del formulario de SIGO.

    Catálogo y no vocabulario cerrado en el código: la lista de las capturas
    del usuario **venía cortada arriba** en el desplegable, así que declararla
    como `choices` sería afirmar que está completa cuando se sabe que no. Un
    valor nuevo se agrega desde la app, sin desplegar — mismo criterio que
    `DocumentType` y `QualificationType`.

    `chapter` guarda la referencia normativa que SIGO muestra entre paréntesis
    ("Capítulo J - DAN 137"): es parte del nombre que hay que reconocer en el
    selector del Estado, no un adorno.
    """

    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=150)
    chapter = models.CharField(
        max_length=60,
        blank=True,
        verbose_name=_("Regulatory chapter"),
        help_text=_("As SIGO shows it, with its DAN 137 chapter."),
    )

    class Meta:
        verbose_name = _("work area type")
        verbose_name_plural = _("work area types")
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.chapter})" if self.chapter else self.name


class FlightObjective(BaseModel):
    """R9.3: "Objetivo del Vuelo" del formulario de SIGO.

    Catálogo por la misma razón que `WorkAreaType`: en la captura el
    desplegable estaba desplazado y "Batimetría" se leía a medias en el borde
    superior. Se siembra lo que se pudo leer y el resto se agrega al verlo.
    """

    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=150)

    class Meta:
        verbose_name = _("flight objective")
        verbose_name_plural = _("flight objectives")
        ordering = ["name"]

    def __str__(self):
        return self.name


class FlightRequest(StatusFlowMixin, BaseModel):
    """R9.3: una solicitud de vuelo de SIGO — **una circunferencia**.

    Espejo del formulario "Información Vuelo" de SIGO, que acepta un punto
    centro con su radio por solicitud. Nace de separar un KMZ multi-círculo
    (`apps.geo.sections`), y su razón de existir es que hoy ese trabajo se hace
    a mano: aislar el círculo en Google Earth, pasar el centro a GMS, estimar
    la distancia al aeródromo y transcribir doce casillas.

    **No reemplaza al permiso de vuelo.** `FlightPermission` es el espejo del
    papel que emite la DGAC (`LV-64`, `LV-101`); esto es la *preparación* de lo
    que se pide y el *seguimiento* de lo pedido. Cuando la DGAC responde, la
    solicitud se vincula al permiso y **rellena** su ubicación estructurada
    (OPS-4) en vez de duplicarla.
    """

    STATUS_PREPARED = "prepared"
    STATUS_FILED = "filed"
    STATUS_LINKED = "linked"
    STATUS_CLOSED = "closed"
    STATUS_CHOICES = [
        (STATUS_PREPARED, _("Prepared")),
        # Con contexto: "Filed in SIGO" ya existe en el catálogo como el estado
        # del **seguro** (`LV-81`), donde el sujeto es masculino ("presentado").
        # Acá el sujeto es la solicitud y sin `msgctxt` heredaría esa redacción.
        # Mismo caso que "Expired" en `FlightPermission` y "Registry" en LV-61.
        (STATUS_FILED, pgettext_lazy("flight request status", "Filed in SIGO")),
        (STATUS_LINKED, _("Linked to permit")),
        # Y "Closed" sin contexto es "Cerrado" -- el contrato de un centro de
        # costo. La no conformidad ya necesitó su propio `msgctxt` por lo
        # mismo; esta es la tercera vez que la misma palabra inglesa cae en dos
        # géneros distintos del español.
        (STATUS_CLOSED, pgettext_lazy("flight request status", "Closed")),
    ]
    STATUS_FLOW = [STATUS_PREPARED, STATUS_FILED, STATUS_LINKED, STATUS_CLOSED]
    # LV-90/LV-113: dónde deja de ser trabajo abierto, declarado junto a las
    # opciones para que el motor de alertas y el panel no lleven su propia copia.
    TERMINAL_STATUSES = frozenset({STATUS_CLOSED})
    # El contenido sólo cambia mientras nadie la haya presentado: una vez
    # ingresada en SIGO, el archivo que allá tienen ya no coincide con lo que se
    # editaría acá.
    EDITABLE_STATUSES = frozenset({STATUS_PREPARED})

    # Sólo el tipo que las capturas muestran. No se inventan los otros que SIGO
    # pueda ofrecer: lo que no se vio, no se declara.
    REQUEST_TYPE_UNPOPULATED = "unpopulated_area"
    REQUEST_TYPE_CHOICES = [
        (REQUEST_TYPE_UNPOPULATED, _("Unpopulated area operation")),
    ]

    title = models.CharField(
        max_length=200,
        help_text=_(
            "Usually the section name from the KMZ, e.g. 'Quebrada km 13.760'."
        ),
    )
    cost_center = models.ForeignKey(
        CostCenter, on_delete=models.PROTECT, related_name="flight_requests"
    )
    request_type = models.CharField(
        max_length=30,
        choices=REQUEST_TYPE_CHOICES,
        default=REQUEST_TYPE_UNPOPULATED,
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_PREPARED
    )

    # --- Lo que SIGO pide, en el orden del formulario ---
    commune = models.CharField(max_length=100, blank=True, verbose_name=_("Commune"))
    area_name = models.CharField(max_length=200, blank=True, verbose_name=_("Area"))
    amc = models.ForeignKey(
        "registry.Aerodrome",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="flight_requests",
        verbose_name=_("Nearest aerodrome (AMC)"),
        help_text=_("Proposed by distance; confirm against the AIP chart."),
    )
    # Se guarda la distancia además del aeródromo, y no se recalcula al mostrar:
    # es el número que se escribió en el formulario del Estado, y tiene que
    # seguir diciendo lo mismo aunque mañana alguien corrija la coordenada del
    # aeródromo en su ficha. Misma lección que `LV-118` dejó en las alertas.
    amc_distance_km = models.DecimalField(
        max_digits=7,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        verbose_name=_("Distance to AMC (km)"),
    )
    center_lat = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        validators=[
            MinValueValidator(Decimal("-90")),
            MaxValueValidator(Decimal("90")),
        ],
    )
    center_lon = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        validators=[
            MinValueValidator(Decimal("-180")),
            MaxValueValidator(Decimal("180")),
        ],
    )
    radius_m = models.PositiveIntegerField(
        null=True, blank=True, verbose_name=_("Radius (m)")
    )
    altitude_m = models.PositiveIntegerField(
        null=True, blank=True, verbose_name=_("Height (m)")
    )
    hour_from = models.TimeField(null=True, blank=True, verbose_name=_("From (time)"))
    hour_to = models.TimeField(null=True, blank=True, verbose_name=_("To (time)"))

    # --- Origen y destino ---
    source_plan = models.ForeignKey(
        "geo.GeoPlan",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="flight_requests",
        help_text=_("The multi-circle plan this section was split from."),
    )
    # La geometría de la sección como JSON canónico, mismo patrón que
    # `GeoPlanVersion.content`: el KMZ que se adjunta a SIGO se genera al
    # descargar. Guardar 47 archivos para 47 solicitudes sería multiplicar
    # binarios que se pueden reconstruir exactamente.
    section_content = models.JSONField(null=True, blank=True)
    flight_permission = models.ForeignKey(
        FlightPermission,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="flight_requests",
    )
    filed_on = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Filed in SIGO on"),
        help_text=_("Used to show how long it has been waiting for an answer."),
    )

    class Meta:
        verbose_name = _("flight request")
        verbose_name_plural = _("flight requests")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "is_active"], name="ops_request_status_idx"),
            models.Index(
                fields=["cost_center", "is_active"], name="ops_request_cc_idx"
            ),
        ]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("flight-request-detail", kwargs={"pk": self.pk})

    @property
    def is_editable(self):
        return self.status in self.EDITABLE_STATUSES

    def clean(self):
        errors = {}
        if self.hour_from and self.hour_to and self.hour_to <= self.hour_from:
            errors["hour_to"] = _("The end time must be after the start time.")
        # El aeródromo sin su distancia (o al revés) deja media casilla que SIGO
        # pide entera; se exigen juntos, mismo criterio que el par de
        # coordenadas de `FlightPermission`.
        if (self.amc_id is None) != (self.amc_distance_km is None):
            message = _("The aerodrome and its distance must be entered together.")
            errors["amc"] = message
            errors["amc_distance_km"] = message
        if errors:
            raise ValidationError(errors)

    def days_waiting(self):
        """Cuántos días lleva presentada sin respuesta, o None.

        El seguimiento que el usuario pidió: una solicitud "ingresada en SIGO"
        que nadie contestó es trabajo detenido y no se ve en ninguna parte
        —mismo hueco que el estado `filed` del seguro (`LV-81`) vino a tapar—.
        `None` mientras no esté presentada o ya tenga permiso: preguntar cuánto
        espera algo que ya llegó no significa nada.
        """
        if self.status != self.STATUS_FILED or not self.filed_on:
            return None
        return (timezone.localdate() - self.filed_on).days


class FlightRequestWorkItem(BaseModel):
    """Un par (Área de Trabajo, Objetivo del Vuelo) de la tabla de SIGO.

    Modelo propio y no dos FK en `FlightRequest` porque el formulario **agrega
    filas**: "Agregar" apila pares en una tabla, y una solicitud puede llevar
    varios. Dos columnas en la solicitud sólo podrían representar el primero.
    """

    request = models.ForeignKey(
        FlightRequest, on_delete=models.CASCADE, related_name="work_items"
    )
    work_area = models.ForeignKey(WorkAreaType, on_delete=models.PROTECT)
    objective = models.ForeignKey(FlightObjective, on_delete=models.PROTECT)

    class Meta:
        verbose_name = _("work item")
        verbose_name_plural = _("work items")
        constraints = [
            models.UniqueConstraint(
                fields=["request", "work_area", "objective"],
                name="ops_request_workitem_unique",
            )
        ]

    def __str__(self):
        return f"{self.work_area} · {self.objective}"


class FlightRequestNote(BaseModel):
    """R9.4: nota de cambio, append-only.

    La trazabilidad que el usuario pidió, con su límite explícito: *"no es
    necesario la comparación entre modificaciones pero sí dejar nota de los
    cambios o lo que se requiere"*. O sea: **no hay diff entre versiones** —
    hay un registro de quién anotó qué y cuándo. Construir el diff habría sido
    más código para responder una pregunta que nadie hizo.

    El historial de *estados* no vive acá: lo escribe la señal compartida en
    `FlightRequestHistory`, igual que en permiso, seguro y mantención.
    """

    # `change_notes` y no `notes`: `FlightRequestHistory` ya tiene un campo
    # `notes` (lo exige la señal compartida), y Django rechaza el choque de
    # accessors. El nombre largo además dice mejor lo que son.
    request = models.ForeignKey(
        FlightRequest, on_delete=models.PROTECT, related_name="change_notes"
    )
    text = models.TextField(verbose_name=_("Note"))
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="flight_request_notes",
    )

    class Meta:
        verbose_name = _("flight request note")
        verbose_name_plural = _("flight request notes")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.request}: {self.text[:40]}"


class FlightRequestHistory(BaseModel):
    """Historial de estados, escrito por `track_status_changes`.

    Los nombres de los campos son los que esa señal espera (`apps/core/
    signals.py`); copiarlos es lo que permite reusarla en vez de escribir un
    cuarto registrador de transiciones.
    """

    sequence = models.PositiveBigIntegerField(editable=False, default=0)
    request = models.ForeignKey(
        FlightRequest, on_delete=models.PROTECT, related_name="history"
    )
    previous_status = models.CharField(
        max_length=20, choices=FlightRequest.STATUS_CHOICES
    )
    new_status = models.CharField(max_length=20, choices=FlightRequest.STATUS_CHOICES)
    changed_by = models.CharField(max_length=150)
    changed_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="flight_request_history_events",
    )
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = _("flight request history")
        verbose_name_plural = _("flight request histories")
        ordering = ["-sequence"]

    def __str__(self):
        return f"{self.request}: {self.previous_status} → {self.new_status}"

    def save(self, *args, **kwargs):
        if self._state.adding:
            latest = FlightRequestHistory.objects.order_by("-sequence").first()
            self.sequence = (latest.sequence if latest else 0) + 1
        return super().save(*args, **kwargs)
