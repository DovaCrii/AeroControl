import zlib
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from apps.core.choices import PURPOSE_CHOICES
from apps.core.models import BaseModel, OperationalTenant
from apps.core.tenancy import get_default_tenant


def normalize_serial(raw):
    """The serial as ADR-0002 §2 defines it: upper-case, no whitespace.

    One function, used by `Aircraft.save()`, `Battery.save()` and the AeroLink
    sync, because a serial typed by a human, one read from a `Z:` folder name
    and one arriving from DJI telemetry all have to compare equal.

    Whitespace is stripped from **inside** the value too, not just the ends:
    two real aircraft (`RPA-4401`, `RPA-4436`) carry a spurious space mid-serial.

    Upper-casing was in the ADR from the start and only reached the code on
    2026-08-12 (X.4c) -- until then AeroControl did the whitespace half and
    would silently fail to match anything AeroLink upper-cased.

    Returns None for an empty result, so `Aircraft.serial_number` (nullable and
    unique) does not collide on the empty string. `Battery` requires it and
    coerces back to "" at the call site, where `clean()` rejects it.

    **No fuzzy matching, ever** -- ADR-0002 §2 forbids Levenshtein and O/0
    substitution by name. Two of the sixteen real aircraft differ from their
    folder by one character, and guessing which is right would attribute
    telemetry to the wrong airframe. That is resolved against the DGAC's RPAS
    certificate by a human, not here.
    """
    return "".join((raw or "").split()).upper() or None


def normalize_registration(raw):
    """La matrícula en su forma canónica: sin espacios sobrantes y en mayúsculas.

    LV-142: `registration` es `unique=True`, pero el índice distingue
    mayúsculas, así que `rpa-7126` y `RPA-7126` eran **dos aeronaves distintas**
    para la base y un duplicado escrito en minúsculas entraba sin aviso. Las 16
    filas de producción ya están en mayúsculas, así que normalizar no cambia
    ningún dato existente: sólo cierra la puerta de aquí en adelante.

    A diferencia del serial, los espacios **internos** se conservan: una
    matrícula es un rótulo que pone la empresa y podría llevarlos; lo que no
    puede es diferir sólo por caja.
    """
    return (raw or "").strip().upper()


class CostCenter(BaseModel):
    tenant = models.ForeignKey(
        OperationalTenant,
        on_delete=models.PROTECT,
        default=get_default_tenant,
        related_name="cost_centers",
    )
    # T3.2 Fase 3: unique per tenant, not globally -- two organizations may
    # reuse a cost-center code. (Global unique dropped; see Meta.constraints.)
    code = models.CharField(max_length=30)
    # LV-16: optional -- the code plus the contract administrator identify the
    # cost center; a free-text name is no longer required on the form.
    name = models.CharField(max_length=150, blank=True)
    # R3.3(b): a separate axis from `is_active` (which is this project's soft
    # delete, AGENTS.md -- never remove operative rows). A cost center whose
    # client contract ended is not an error/duplicate to archive away; it
    # should keep showing (greyed, grouped after the operative ones) so its
    # history stays reachable from the normal list, not just from "archived".
    # Constantes y no literales sueltos: `contract_status` pasó de ser un dato de
    # la ficha a **decidir quién entra en el indicador de cumplimiento**
    # (`permit_status_by_cost_center`, 2026-09-14), y un `"closed"` tecleado mal
    # en ese filtro no falla — deja de excluir y nadie se entera.
    CONTRACT_ACTIVE = "active"
    CONTRACT_CLOSED = "closed"
    CONTRACT_STATUS_CHOICES = [
        (CONTRACT_ACTIVE, _("Active")),
        (CONTRACT_CLOSED, _("Closed")),
    ]
    # blank=True: unlike R2.6's area_type, closing a contract is an
    # occasional action on an existing record, not a fact every cost center
    # needs on creation -- forcing a choice on every form would be friction
    # for no benefit when "active" is already the right default.
    contract_status = models.CharField(
        max_length=20, choices=CONTRACT_STATUS_CHOICES, default="active", blank=True
    )
    # LV-206: si en esta faena **se vuela**. Pedido del usuario mirando el estado
    # de los permisos por faena: *"el CC110 de casa matriz o 410, por ejemplo,
    # estamos a cargo más de los equipos que volar"*.
    #
    # Es un eje propio y no se deduce de nada existente: no es `is_active` (la
    # faena existe y opera), no es `contract_status` (el contrato está vigente), y
    # no es "no tiene permisos" — que es justamente la conclusión que hay que
    # evitar. Una faena que administra equipos y no vuela, listada como "sin
    # permisos vigentes", queda declarada incumplida por una operación que no le
    # toca; es el mismo error de forma que contar las aeronaves `retired` en la
    # disponibilidad de la flota, y `fleet_availability` lo evita por la misma
    # razón escrita en su comentario.
    #
    # **Campo declarado y no una lista de códigos en el código**: `CC110` y `CC410`
    # son los de hoy, y una constante con esos dos se desactualiza el día que
    # alguien abre una faena nueva de bodega — en silencio, y del lado que declara
    # incumplimientos falsos.
    #
    # `default=True` porque la mayoría vuela: el valor por defecto tiene que ser el
    # que no cambia nada para las faenas que ya existen.
    operates_flights = models.BooleanField(
        default=True,
        verbose_name=_("Flies in this cost center"),
        help_text=_(
            "Uncheck for cost centers that only hold equipment and never fly: "
            "they stay out of the flight-permit status table."
        ),
    )
    # Free-text name kept from the Chapter 1 import. It cannot be used to reach
    # anyone (the imported values do not match operator names), so notifications
    # use responsible_operator; this stays as the historical record.
    responsible = models.CharField(max_length=150, blank=True)
    responsible_operator = models.ForeignKey(
        "registry.Operator",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cost_centers_in_charge",
        help_text=_("Recipient of expiry digests for this cost center."),
    )
    # The responsible person is not always in the operator roster: it can be an
    # administrator, a secretary, or a safety officer instead of a registered
    # pilot -- and the same person may end up responsible for several cost
    # centers where staffing is thin. Forcing them into Operator would mean
    # inventing a DGAC credential and employee ID for someone who does not
    # fly, and would leak into every other view that assumes the roster is
    # flight crew. Plain contact info instead, used only when no operator is
    # reachable (see notification_email).
    # verbose_name matches the form's labels (registry/forms.py CostCenterForm)
    # so the detail page and the edit form read the same -- Django's
    # auto-derived label ("Responsible contact name") has no catalog entry and
    # rendered in English on the detail page otherwise. Case must match the
    # catalog msgid exactly ("External contact name"/"...email", already used
    # by the form) -- translate_field_label() only re-cases+relooks-up a miss,
    # so a source literal that only near-matches (wrong case) passes the
    # detail page by accident but fails test_translations' exact-match guard.
    responsible_contact_name = models.CharField(
        max_length=150, blank=True, verbose_name=_("External contact name")
    )
    responsible_contact_email = models.EmailField(
        blank=True, verbose_name=_("External contact email")
    )
    # R7.4 (ISO 9001 8.6): the acceptance criteria for a survey belong to the
    # contract, not to each deliverable. If someone types the threshold on
    # every row it is not an agreed criterion, it is an opinion per record --
    # so `Deliverable` compares against these and derives "meets / does not"
    # instead of storing a declared verdict.
    #
    # All nullable, and that is the design, not a gap: **a contract with no
    # thresholds set simply has no quality gate**, and the deliverable records
    # its metrics without a pass/fail claim. That is what makes this shippable
    # before the real contract numbers are known -- they are loaded per
    # contract, by the people who negotiated them, with no code change. An
    # invented global threshold would be worse than none: a gate the operation
    # cannot meet is a gate somebody switches off.
    required_gsd_cm = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        verbose_name=_("Required GSD (cm)"),
    )
    max_rmse_xy_cm = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        verbose_name=_("Maximum horizontal RMSE (cm)"),
    )
    max_rmse_z_cm = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        verbose_name=_("Maximum vertical RMSE (cm)"),
    )
    # R8.4: where this contract's work actually happens, so the dashboard can
    # show the weather for the site when there is no upcoming permit to take
    # coordinates from. Deliberately *here* and not on `Operator`: a person
    # moves several times a day and nobody would keep that current, while a
    # site does not move -- somebody types it once and it stays true. This is
    # also why browser geolocation was rejected (R8.4 option (b)): it would
    # send a person's position to the server, and an operator sitting in the
    # office is not where the flight is.
    #
    # Same precision and pair rule as FlightPermission's structured location
    # (OPS-4), so the two coordinate sources behave identically.
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        validators=[
            MinValueValidator(Decimal("-90")),
            MaxValueValidator(Decimal("90")),
        ],
        verbose_name=_("Site latitude"),
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
        verbose_name=_("Site longitude"),
    )

    def clean(self):
        """A lone coordinate cannot locate anything (same rule as
        FlightPermission.clean): require the pair together so a half-entered
        point does not silently fail to produce a forecast."""
        super().clean()
        if (self.latitude is None) != (self.longitude is None):
            message = _("Latitude and longitude must be entered together.")
            raise ValidationError({"latitude": message, "longitude": message})

    @property
    def coordinates(self):
        """(latitude, longitude) as floats, or None when not on file.

        Floats because the only consumer is the weather module, which rounds
        them into a cache key; `Decimal` would make that key depend on how many
        trailing zeros somebody typed.
        """
        if self.latitude is None or self.longitude is None:
            return None
        return (float(self.latitude), float(self.longitude))

    @property
    def has_quality_thresholds(self):
        """Whether this contract defines acceptance criteria at all."""
        return any(
            value is not None
            for value in (
                self.required_gsd_cm,
                self.max_rmse_xy_cm,
                self.max_rmse_z_cm,
            )
        )

    def __str__(self):
        # name is optional (LV-16): fall back to the code alone when blank.
        label = f"{self.code} - {self.name}" if self.name else self.code
        return f"{label} · {self.responsible}" if self.responsible else label

    class Meta:
        # Translated names: user-facing messages interpolate verbose_name
        # ("%(name)s archived"), and without this they said "Operator" inside
        # a Spanish sentence.
        verbose_name = _("cost center")
        verbose_name_plural = _("cost centers")
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "code"], name="registry_costcenter_tenant_code_uniq"
            )
        ]

    @property
    def day_to_day_contact(self):
        """Who to reach day-to-day, when it is not the contract administrator
        above (LV-34/LV-56): an operator from the roster, or an external
        contact. Empty when the administrator already covers it -- callers
        show this only as a supplement, not a replacement."""
        if self.responsible_operator_id:
            return self.responsible_operator.full_name
        return self.responsible_contact_name

    @property
    def notification_email(self):
        """Email to notify for this cost center, or "" when unreachable.

        An archived responsible operator does not count as reachable: mailing
        someone who left looks like the notification worked when nobody who
        can act on it will read it. Falls back to the external contact when
        the responsible person is not in the operator roster, or when the
        operator on file left and nobody replaced them there yet.
        """
        operator = self.responsible_operator
        if operator and operator.is_active and operator.email:
            return operator.email
        return self.responsible_contact_email


class Aircraft(BaseModel):
    tenant = models.ForeignKey(
        OperationalTenant,
        on_delete=models.PROTECT,
        default=get_default_tenant,
        related_name="aircraft",
    )
    STATUS_CHOICES = [
        ("active", _("Active")),
        # LV-46: an accident/incident just happened and the aircraft has not
        # yet been formally sent to maintenance -- distinct from "maintenance"
        # (already in the workflow) so the fleet list flags it at a glance.
        ("damaged", _("Damaged")),
        ("maintenance", _("Maintenance")),
        ("retired", _("Retired")),
    ]
    # LV-90: a retired aircraft left the fleet -- it is not a condition anyone
    # can act on, so it must not keep raising alerts. The old literal list in
    # generate_alerts never mentioned it (it only knew the permit's and the
    # maintenance record's vocabularies), so a rule watching `status` alerted on
    # retired airframes forever. `fleet_availability` already excludes them from
    # its denominator for exactly this reason.
    TERMINAL_STATUSES = frozenset({"retired"})
    registration = models.CharField(max_length=30, unique=True)
    type = models.CharField(max_length=100)
    model = models.CharField(max_length=100)
    manufacturer = models.CharField(max_length=100)
    year = models.PositiveIntegerField(null=True, blank=True)
    # X.1: the only key present in all three worlds (DJI, the Z: folder
    # names, the DGAC registry) -- unique now that the 4 known production
    # discrepancies are resolved (see save() and migration 0028). `null=True`
    # (not just blank) so aircraft without a serial on file yet do not
    # collide on the unique index, same pattern as
    # FlightPermission.permission_number.
    serial_number = models.CharField(max_length=100, blank=True, null=True, unique=True)
    max_takeoff_weight_kg = models.DecimalField(
        max_digits=8, decimal_places=3, null=True, blank=True
    )
    basic_weight_kg = models.DecimalField(
        max_digits=8, decimal_places=3, null=True, blank=True
    )
    vlos = models.CharField(max_length=20, blank=True, verbose_name=_("VLOS"))
    parachute = models.CharField(max_length=20, blank=True)
    # LV-29: the JAC insurance validity from the SIGO screen, as a first-class
    # field (the user enters it from the DGAC capture). This is the canonical
    # source for the list column and the alert/calendar/dashboard wiring; an
    # insurance document may still be attached as the supporting file, but the
    # date lives here (before LV-29 it was derived from an is_insurance
    # Document, which meant no expiry until a file was uploaded).
    insurance_expiry = models.DateField(
        null=True, blank=True, verbose_name=_("JAC insurance expiry")
    )
    # R5.7: a newly-registered aircraft with the JAC policy already
    # requested looked identical to one with no insurance requested at all
    # -- both showed "-" on the list, since insurance_expiry was null either
    # way. This tracks the filing itself, a separate axis from
    # insurance_expiry (same pattern as CostCenter.contract_status, R3.3b).
    #
    # LV-81 turned the two values into the **four the real cycle has**, as the
    # user described it: missing or needing renewal -> being arranged with the
    # broker -> filed in the DGAC portal, waiting for the JAC -> authorized.
    # That last distinction is not invented here: SIGO shows each aircraft as
    # "Pendiente" or "Autorizada", and the certificate the user provided
    # (policy 95131 / certificate 136) sits on the one aircraft SIGO still
    # lists as pending. Before this, "insurance bought and waiting for the
    # authority" and "no insurance at all" were the same value.
    #
    # `pending` keeps its original code on purpose: renaming it to
    # `in_progress` would buy nothing and cost a data migration over real rows.
    INSURANCE_STATUS_MISSING = "missing"
    INSURANCE_STATUS_PENDING = "pending"
    INSURANCE_STATUS_FILED = "filed"
    INSURANCE_STATUS_ACTIVE = "active"
    INSURANCE_STATUS_CHOICES = [
        (INSURANCE_STATUS_MISSING, _("Missing or to be renewed")),
        (INSURANCE_STATUS_PENDING, _("Filing in progress")),
        (INSURANCE_STATUS_FILED, _("Filed in SIGO, awaiting the JAC")),
        # Not the bare "Active" it used to share with the airframe's status and
        # the contract's: as the last step of this stepper "Activo" says nothing
        # about *what* is active, and this page carries three other statuses.
        (INSURANCE_STATUS_ACTIVE, _("Policy in force")),
    ]
    # The stepper's steps. `missing` is deliberately **not** one of them: it is
    # the state before the flow starts, so it renders as three pending steps
    # rather than as a first step already reached.
    INSURANCE_FLOW = [
        INSURANCE_STATUS_PENDING,
        INSURANCE_STATUS_FILED,
        INSURANCE_STATUS_ACTIVE,
    ]
    insurance_status = models.CharField(
        max_length=20,
        choices=INSURANCE_STATUS_CHOICES,
        # LV-81: was "active". A brand-new aircraft with nothing on file is not
        # insured, and defaulting to "active" is how three production aircraft
        # ended up reading "Vigente" with no date next to it.
        default=INSURANCE_STATUS_MISSING,
        blank=True,
        verbose_name=_("Insurance status"),
    )
    authorized_services = models.TextField(blank=True)
    cost_center = models.ForeignKey(
        CostCenter,
        on_delete=models.PROTECT,
        related_name="aircraft",
        null=True,
        blank=True,
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")

    # OPS-3: physical whereabouts, a different axis from `status` (condition).
    # An active aircraft can be at headquarters, deployed on a site, or in for
    # maintenance; tracked separately so "where is it" and "is it flyable" don't
    # get conflated into one field.
    LOCATION_CHOICES = [
        ("headquarters", _("Headquarters")),
        ("on_site", _("On site")),
        ("maintenance", _("In maintenance")),
    ]
    current_location = models.CharField(
        max_length=20, choices=LOCATION_CHOICES, default="headquarters"
    )
    current_site = models.ForeignKey(
        CostCenter,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text=_("The site this aircraft is deployed to, when on site."),
    )

    class Meta:
        verbose_name = _("aircraft")
        verbose_name_plural = _("aircraft")

    def __str__(self):
        return self.registration

    @property
    def selector_label(self):
        """R5.5: `registration` alone does not distinguish "which M300 is
        this" in a dropdown with several of the same model. Deliberately
        not folded into `__str__` -- other places (movement logs, the
        assignment tables) depend on that staying just the registration.
        Used via `label_from_instance` in every form that lets someone pick
        an aircraft (AssignmentForm, AircraftAssignmentForm,
        AircraftBulkAssignForm, FlightRecordForm,
        FlightPermissionForm.aircraft_fleet, MaintenanceRecordForm)."""
        parts = [self.registration, self.model]
        if self.serial_number:
            parts.append(f"S/N {self.serial_number}")
        return " · ".join(parts)

    @property
    def insurance_is_overdue(self):
        """LV-29: the JAC insurance lapsed (past its expiry). ``None`` expiry --
        no date on file -- is not overdue, it is simply unknown."""
        from django.utils import timezone

        return (
            self.insurance_expiry is not None
            and self.insurance_expiry < timezone.localdate()
        )

    def clean(self):
        # X.1/LV-142: normalizar **acá** y no sólo en `save()`. `full_clean`
        # corre `clean()` antes de `validate_unique()`, así que la comprobación
        # de unicidad ve el valor canónico; hacerlo en `save()` la dejaba
        # comparando el crudo, y un serial con un espacio de más pasaba la
        # validación para morir en el INSERT. Va como primera línea: si fuera
        # después del `raise` de `current_site`, un error de sitio impediría que
        # la normalización corriera. `save()` la conserva como respaldo de los
        # caminos que no llaman `full_clean` (importadores, `objects.create`).
        self.registration = normalize_registration(self.registration)
        self.serial_number = normalize_serial(self.serial_number)
        errors = {}
        if self.current_location == "on_site" and not self.current_site_id:
            errors["current_site"] = _("Select the site the aircraft is deployed to.")
        if self.current_location != "on_site" and self.current_site_id:
            errors["current_site"] = _(
                "A site only applies when the aircraft is on site."
            )
        if errors:
            raise ValidationError(errors)
        self._normalize_insurance_status()

    def _normalize_insurance_status(self):
        """Keep the filing status and the expiry date from contradicting.

        Normalizes rather than raising, the same idiom as
        `CostCenter.contract_status` (R3.3b) -- a contradiction here must not
        block someone from saving an unrelated edit on the aircraft.

        **LV-81 removed the half of R5.7's rule that was wrong**: it used to
        force `active` whenever an expiry date existed, which made a renewal
        impossible to record. Renewing is precisely the case the user asked for
        ("faltante para actualizar"): the current policy still has its end date
        on file while the next one is being arranged, so `pending`/`filed`
        alongside a date is a legitimate state, not stale data. Those two are
        never overridden now.

        The two combinations that really cannot coexist are still fixed:

        - `active` with **no** date at all -- the DGAC does not authorize a
          policy without a validity period, so this reads as nothing on file.
          This is what three production aircraft look like today.
        - `missing` while a policy is **still valid** -- "no insurance" cannot
          be true when a current one is on record. An expiry already in the
          past is left alone: that is exactly what `missing` should say.
        """
        from django.utils import timezone

        expiry = self.insurance_expiry
        if not self.insurance_status:
            self.insurance_status = (
                self.INSURANCE_STATUS_ACTIVE
                if expiry
                else self.INSURANCE_STATUS_MISSING
            )
        if self.insurance_status == self.INSURANCE_STATUS_ACTIVE and expiry is None:
            self.insurance_status = self.INSURANCE_STATUS_MISSING
        elif (
            self.insurance_status == self.INSURANCE_STATUS_MISSING
            and expiry is not None
            and expiry >= timezone.localdate()
        ):
            self.insurance_status = self.INSURANCE_STATUS_ACTIVE

    def get_absolute_url(self):
        # LV-81: added when the insurance transitions needed somewhere to send
        # the user back to. Same shape as FlightPermission/MaintenanceRecord,
        # which is what lets them share `StatusTransitionView`.
        from django.urls import reverse

        return reverse("aircraft-detail", args=[self.pk])

    def insurance_steps(self):
        """LV-81: the filing as a stepper, the same shape the permit uses.

        Not `StatusFlowMixin`: that mixin reads the model's own `status`, and on
        an aircraft `status` is the airframe's condition (active/damaged/
        maintenance), which is not a progression -- the mixin's docstring names
        this exact case as what it must not be used for.
        """
        from apps.core.models import status_steps_for

        steps = status_steps_for(
            choices=self.INSURANCE_STATUS_CHOICES,
            flow=self.INSURANCE_FLOW,
            current=self.insurance_status,
        )
        # LV-81b (la mitad de presentación): una póliza cuya fecha ya pasó no
        # está "vigente", diga lo que diga el estado guardado. La insignia
        # "Vencida" al lado ya lo decía y la escalera no, así que la misma ficha
        # afirmaba dos cosas incompatibles -- y la que se lee de un vistazo es la
        # escalera.
        #
        # Se corrige **lo que se muestra**, no el dato: mover el estado por
        # fecha es la misma decisión que `LV-83` tomó para los permisos (estado
        # terminal nuevo más un trabajo diario) y está pendiente de acordarse una
        # vez para los dos. Hasta entonces, derivarlo de la fecha no escribe nada
        # y no puede quedar desincronizado, porque se calcula al dibujar.
        # La condición se apoya en el **estado**, no en el último paso: la
        # escalera siempre dibuja los tres, así que mirar `steps[-1]` marcaría
        # como vencida la póliza de un trámite que todavía está en SIGO y nunca
        # llegó a estar vigente. Sólo puede vencer lo que dice estar en vigor.
        if (
            self.insurance_status == self.INSURANCE_STATUS_ACTIVE
            and self.insurance_is_overdue
        ):
            steps[-1] = {
                "code": self.INSURANCE_STATUS_ACTIVE,
                "label": _("Policy lapsed"),
                "state": "blocked",
            }
        return steps

    def save(self, *args, **kwargs):
        # X.1: the DJI serial never contains whitespace -- production has 2
        # aircraft with a stray internal space typed into this field
        # (confirmed against the Z: folder names, which carry the real
        # serial). `.split()`+`"".join` removes internal as well as leading/
        # trailing whitespace, unlike `.strip()`. An empty result becomes
        # `None`, not `""`, so several aircraft without a serial on file
        # do not collide on the unique index.
        self.serial_number = normalize_serial(self.serial_number)
        # LV-142: la matrícula también, por el mismo motivo y para los mismos
        # caminos que no pasan por `full_clean`.
        self.registration = normalize_registration(self.registration)
        super().save(*args, **kwargs)


class InsuranceHistory(BaseModel):
    """LV-81: append-only trace of the JAC insurance filing, per aircraft.

    Mirrors `operations.PermissionHistory` field for field, because the shared
    `track_status_changes` signal writes all of them and the shared
    `generic/_traceability.html` renders all of them -- a different shape here
    would mean a fourth variant of the same table.

    Why the trace matters beyond the current value: an auditor asking "when did
    this aircraft's policy lapse, and how long did the renewal take" cannot get
    that from a single status field, and the DGAC's own screen does not keep it
    for us either. `changed_by`/`changed_by_user` answer *who*, and the user's
    groups answer *in what capacity* (the LV-72 criterion).
    """

    # Same tie-breaker as PermissionHistory: `created_at` alone cannot order two
    # rows created moments apart, because `timezone.now()` can return the
    # identical value across rapid successive calls.
    sequence = models.PositiveBigIntegerField(editable=False, default=0)
    aircraft = models.ForeignKey(
        Aircraft, on_delete=models.PROTECT, related_name="insurance_history"
    )
    # `choices` declared, unlike the R2.5 defect: without them Django never
    # generates `get_new_status_display`, and the history table silently falls
    # through to the raw stored code ("filed") inside a Spanish page.
    previous_status = models.CharField(
        max_length=20, choices=Aircraft.INSURANCE_STATUS_CHOICES
    )
    new_status = models.CharField(
        max_length=20, choices=Aircraft.INSURANCE_STATUS_CHOICES
    )
    changed_by = models.CharField(max_length=150)
    changed_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="insurance_history_events",
    )
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = _("insurance history")
        verbose_name_plural = _("insurance histories")
        ordering = ["-sequence"]

    def __str__(self):
        return f"{self.aircraft}: {self.previous_status} → {self.new_status}"

    def save(self, *args, **kwargs):
        if self._state.adding:
            latest = InsuranceHistory.objects.order_by("-sequence").first()
            self.sequence = (latest.sequence if latest else 0) + 1
        return super().save(*args, **kwargs)


class Battery(BaseModel):
    """LiPo battery inventory and cycle count (R7.2, ISO 7.1.3).

    **A mirror, not a master.** ADR-0002 assigns battery inventory to AeroLink,
    because DJI reports cycles and health natively and a hand-kept count drifts
    from reality immediately. This table exists so the ISO 7.1.3 evidence lives
    where the auditor already looks -- next to the aircraft, the maintenance
    history and the flight hours -- while the numbers themselves come from
    AeroLink once `X.4` lands. Until then it stays empty on purpose; there is
    no create/edit form (the plan's own wording: "diseñar la forma, no llenarla
    a mano").

    That mirror role is what shapes the fields:

    - `serial_number` is the join key and is unique, exactly like
      `Aircraft.serial_number` (X.1) -- it is what DJI reports, so it is the
      only value both systems can agree on. Same whitespace normalization, so
      a serial typed by a human and one arriving from telemetry compare equal.
    - `cycle_count` / `health_percent` / `firmware_version` are the three
      things ISO 7.1.3 asks about that only the aircraft knows.
    - `synced_at` / `source` record **where a row came from and how stale it
      is**. Without them a zero cycle count is ambiguous: a new battery, or a
      sync that never ran? An auditor asking "is this current?" needs that
      answered on the record, not inferred.
    - `aircraft` is nullable and intentionally weak: batteries rotate between
      airframes, so this is "last seen on", not ownership.
    """

    SOURCE_MANUAL = "manual"
    SOURCE_AEROLINK = "aerolink"
    SOURCE_CHOICES = [
        (SOURCE_MANUAL, _("Entered by hand")),
        (SOURCE_AEROLINK, _("Synced from AeroLink")),
    ]
    STATUS_CHOICES = [
        ("active", _("Active")),
        # A LiPo past its cycle life is a safety item (ISO 45001 6.1.2), not
        # just an inventory one -- it needs to be visibly out of service.
        ("retired", _("Retired")),
    ]

    tenant = models.ForeignKey(
        OperationalTenant,
        on_delete=models.PROTECT,
        default=get_default_tenant,
        related_name="batteries",
    )
    serial_number = models.CharField(
        max_length=100, unique=True, verbose_name=_("Serial number")
    )
    manufacturer = models.CharField(max_length=100, blank=True)
    model = models.CharField(max_length=100, blank=True)
    aircraft = models.ForeignKey(
        Aircraft,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="batteries",
        verbose_name=_("Last seen on aircraft"),
    )
    cycle_count = models.PositiveIntegerField(default=0, verbose_name=_("Cycles"))
    health_percent = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name=_("Health (%)")
    )
    firmware_version = models.CharField(max_length=50, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    first_use_date = models.DateField(null=True, blank=True)
    source = models.CharField(
        max_length=20, choices=SOURCE_CHOICES, default=SOURCE_MANUAL
    )
    synced_at = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Last synced")
    )

    class Meta:
        verbose_name = _("battery")
        verbose_name_plural = _("batteries")
        ordering = ["serial_number"]
        indexes = [
            models.Index(fields=["status", "is_active"], name="reg_battery_status_idx"),
            # X.4 will resolve incoming telemetry by serial, one lookup per
            # battery per session.
            models.Index(fields=["serial_number"], name="reg_battery_serial_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(health_percent__isnull=True) | Q(health_percent__lte=100),
                name="reg_battery_health_pct_max",
            )
        ]

    def __str__(self):
        label = self.model or self.manufacturer or _("Battery")
        return f"{label} · {self.serial_number}"

    def save(self, *args, **kwargs):
        # Same normalization as Aircraft.serial_number (X.1): a serial from DJI
        # never contains whitespace, and a hand-typed one must compare equal to
        # it. Unlike Aircraft this field is required, so an empty result is a
        # validation problem rather than a legitimate NULL -- left to clean().
        self.serial_number = normalize_serial(self.serial_number) or ""
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if not "".join((self.serial_number or "").split()):
            raise ValidationError(
                {"serial_number": _("A battery needs its serial number.")}
            )


class Operator(BaseModel):
    tenant = models.ForeignKey(
        OperationalTenant,
        on_delete=models.PROTECT,
        default=get_default_tenant,
        related_name="operators",
    )
    # Acronyms are spelled out here so the label lookup matches the catalog;
    # Django's derived labels would be "Employee id"/"Dgac credential".
    # T3.2 Fase 3: unique per tenant (global unique dropped; see
    # Meta.constraints) -- an employee id is an organization-internal id.
    # LV-169: `blank=True` para que `clean_fields()` no corte antes de que
    # `clean()` pueda derivarlo del RUT. **No lo vuelve opcional**: `clean()`
    # exige que quede con valor, y la unicidad por tenant sigue en pie. El
    # cambio es de validación, no de esquema -- la migración no emite SQL.
    employee_id = models.CharField(
        max_length=50, blank=True, verbose_name=_("Employee ID")
    )
    full_name = models.CharField(max_length=150)
    # LV-177: el padrón se busca por apellido y estaba ordenado por nombre de
    # pila, porque `full_name` es un solo campo y ordenarlo alfabéticamente
    # ordena por lo primero que trae. Con 42 personas eso obliga a barrer la
    # lista entera para encontrar a alguien.
    #
    # **`full_name` sigue siendo el nombre de registro**, y estos dos son
    # auxiliares de orden y presentación. La distinción no es un matiz: el
    # nombre completo aparece en permisos, catastro, PDF y correos, y cambiarle
    # el origen habría tocado todo eso por una mejora de listado.
    #
    # Nacen **vacíos y opcionales a propósito**: dónde empieza el apellido no es
    # deducible sin equivocarse —"Bernardine Von Irmer Helle", "Jose Luis Ogalde
    # Henríquez"— y un corte inventado es peor que ninguno, porque ordena mal
    # justo los casos raros. La lista ordena por apellido cuando está cargado y
    # por nombre completo cuando no, así que nadie desaparece mientras se
    # completan. El comando `split_operator_names` propone el corte; escribirlo
    # exige `--apply`.
    given_names = models.CharField(
        max_length=100, blank=True, verbose_name=_("Given names")
    )
    surnames = models.CharField(max_length=100, blank=True, verbose_name=_("Surnames"))
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    rut = models.CharField(max_length=20, blank=True, verbose_name=_("RUT"))
    dgac_credential = models.CharField(
        max_length=30, blank=True, verbose_name=_("DGAC credential")
    )
    # LV-29: the credential's validity (the *Vigencia* column on the SIGO
    # operator screen), entered by the user from the DGAC capture. Drives the
    # list column, the alert rule, the calendar feed and the operator notice.
    credential_expiry = models.DateField(
        null=True, blank=True, verbose_name=_("DGAC credential expiry")
    )
    operator_type = models.CharField(max_length=80, blank=True)
    address = models.TextField(blank=True)
    authorizations = models.TextField(blank=True)
    cost_center = models.ForeignKey(
        CostCenter,
        on_delete=models.PROTECT,
        related_name="operators",
        null=True,
        blank=True,
    )
    # B3.2: "My work" needs to resolve the operator for the logged-in user.
    # Explicit and admin/form-set on purpose -- matching by email (like the
    # CostCenter.responsible_operator precedent avoided) could silently link
    # the wrong person if an address is stale or shared.
    user = models.OneToOneField(
        get_user_model(),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="operator_profile",
        verbose_name=_("Linked user account"),
        help_text=_('Optional. Lets this person see "My work" filtered to them.'),
    )

    class Meta:
        verbose_name = _("operator")
        verbose_name_plural = _("operators")
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "employee_id"],
                name="registry_operator_tenant_employee_uniq",
            )
        ]

    def __str__(self):
        return self.full_name

    def clean(self):
        """LV-143: el RUT se guarda canónico y se valida cuando cambia.

        Es la llave natural chilena y admitía duplicados y basura. La regla vive
        acá y no sólo en el formulario porque AGENTS.md prohíbe la validación
        forms-only: el formulario es evadible desde el admin, la API o un import.

        **Sólo cuando el valor cambia**, y eso no es una concesión: el import del
        Capítulo 1 exige RUT para leer una ficha y en producción hay operadores
        duplicados que vinieron de ahí. Exigir un RUT válido y único para guardar
        *cualquier* edición dejaría esas fichas congeladas — no se les podría
        corregir ni el teléfono. Los duplicados se resuelven con
        `find_duplicate_operators --apply`, que es una decisión de persona con el
        papel delante, no bloqueando pantallas.

        La normalización sí corre siempre: una ficha que se edita queda con el
        RUT canónico, y así el padrón converge sin migración de datos.

        **LV-169: el ID de empleado se deriva del RUT cuando está en blanco.**
        En producción convivían `RUT-192135974` y la columna de al lado diciendo
        `19213597-4` — el mismo número dos veces, tipeado a mano, con el error de
        transcripción incluido en el precio. Se rellena **sólo si está vacío**:
        un ID ya escrito es la llave con la que esa persona figura en otros
        sistemas y sobrescribirlo rompería esas referencias sin avisar.

        Y se deriva **sólo de un RUT válido**. De uno inválido saldría un ID
        inválido y único —basura que pasa la constraint— justo en el campo que es
        la llave del padrón. Sin RUT utilizable el ID se sigue pidiendo, que es
        lo que ya pasaba. **El RUT no se vuelve obligatorio**: eso congelaría las
        fichas legadas duplicadas, la trampa que `LV-143` evitó a propósito.
        """
        from .duplicates import operator_with_rut
        from .rut import employee_id_from_rut, normalize_rut, rut_is_valid

        super().clean()
        self._check_name_parts_belong_to_the_full_name()
        self.rut = normalize_rut(self.rut)
        self.employee_id = (self.employee_id or "").strip()
        if not self.employee_id and rut_is_valid(self.rut):
            self.employee_id = employee_id_from_rut(self.rut)
        if not self.employee_id:
            raise ValidationError(
                {
                    "employee_id": _(
                        "Enter the employee ID, or a valid RUT to derive it from."
                    )
                }
            )
        if not self.rut or not self._rut_changed():
            return
        if not rut_is_valid(self.rut):
            raise ValidationError(
                {"rut": _("Enter the RUT as 12345678-5, including its check digit.")}
            )
        existing = operator_with_rut(
            self.rut, tenant_id=self.tenant_id, exclude_pk=self.pk
        )
        if existing is not None:
            raise ValidationError(
                {
                    "rut": _("RUT %(rut)s already belongs to %(name)s.")
                    % {"rut": self.rut, "name": existing.full_name}
                }
            )

    def _check_name_parts_belong_to_the_full_name(self):
        """LV-177: nombres y apellidos tienen que salir del nombre de registro.

        No impone **orden ni cantidad** —eso es justamente lo que no se puede
        deducir— pero caza el caso que sí importa: que alguien escriba en estos
        campos un apellido que no está en `full_name` y la ficha quede diciendo
        dos nombres distintos para la misma persona, con la lista ordenada por
        uno y todo lo demás mostrando el otro.

        Se compara sin tildes ni caja: quien complete el corte va a tipearlo a
        mano, y rechazarlo por un acento sería convertir un guardián en un
        estorbo.
        """
        import unicodedata

        def words(text):
            plain = unicodedata.normalize("NFKD", text or "")
            plain = "".join(c for c in plain if not unicodedata.combining(c))
            return set(plain.casefold().split())

        available = words(self.full_name)
        stray = (words(self.given_names) | words(self.surnames)) - available
        if stray:
            raise ValidationError(
                {
                    # El `%` va **fuera** de `gettext`: interpolando adentro, la
                    # búsqueda se haría sobre el texto ya sustituido y jamás
                    # encontraría la entrada del catálogo — el mensaje saldría
                    # siempre en inglés y ningún test lo delataría.
                    "surnames": _("%(words)s is not part of the full name on file.")
                    % {"words": ", ".join(sorted(stray))}
                }
            )

    @property
    def listing_name(self):
        """ "Apellidos, Nombres" cuando el corte está hecho; si no, el completo.

        LV-177: la lista se lee de a filas y el apellido adelante es lo que deja
        encontrar a alguien de un vistazo. Mientras haya fichas sin cortar
        conviven las dos formas, y eso es correcto: cada fila dice la verdad de
        lo que se sabe de ese nombre, en vez de inventar un corte para que todas
        se vean iguales.
        """
        if self.surnames and self.given_names:
            return f"{self.surnames}, {self.given_names}"
        return self.full_name

    def _rut_changed(self):
        """True en un alta, o cuando el RUT guardado difiere del que se va a escribir.

        `values_list` y no `.all()`: la lección de AGENTS.md sobre chequeos que
        corren con el código nuevo sobre la base vieja vale igual acá, y de paso
        no se instancia un operador entero para leer un campo.
        """
        from .rut import normalize_rut

        if self._state.adding or self.pk is None:
            return True
        previous = (
            Operator.objects.filter(pk=self.pk).values_list("rut", flat=True).first()
        )
        return normalize_rut(previous) != self.rut

    @property
    def credential_is_overdue(self):
        """LV-29: the DGAC credential lapsed. ``None`` -- no date on file -- is
        unknown, not overdue (mirrors Aircraft.insurance_is_overdue)."""
        from django.utils import timezone

        return (
            self.credential_expiry is not None
            and self.credential_expiry < timezone.localdate()
        )


class Assignment(BaseModel):
    STATUS_CHOICES = [
        ("planned", _("Planned")),
        ("confirmed", _("Confirmed")),
        ("completed", _("Completed")),
        ("cancelled", _("Cancelled")),
    ]
    operator = models.ForeignKey(
        Operator, on_delete=models.PROTECT, related_name="assignments"
    )
    aircraft = models.ForeignKey(
        Aircraft, on_delete=models.PROTECT, related_name="assignments"
    )
    cost_center = models.ForeignKey(
        CostCenter,
        on_delete=models.PROTECT,
        related_name="assignments",
        null=True,
        blank=True,
    )
    # R3.1: same closed vocabulary as FlightPermission (apps.core.choices) --
    # optional here (blank=True), unlike the flight permit: LV-17 already
    # decided this is a supplementary note on an assignment, not a fact
    # every assignment must carry.
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES, blank=True)
    purpose_detail = models.CharField(max_length=250, blank=True, default="")
    purpose_legacy = models.CharField(
        max_length=250, blank=True, default="", editable=False
    )
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="planned")

    class Meta:
        verbose_name = _("assignment")
        verbose_name_plural = _("assignments")
        # The calendar and the overlap validation both filter by date range.
        indexes = [
            models.Index(
                fields=["start_date", "end_date"], name="reg_assignment_range_idx"
            )
        ]
        constraints = [
            models.CheckConstraint(
                condition=~Q(purpose="other") | ~Q(purpose_detail=""),
                name="reg_assignment_other_purpose_requires_detail",
            )
        ]

    def __str__(self):
        return f"{self.operator} · {self.aircraft}"

    def clean(self):
        # English source strings with the Spanish in the catalog, like the rest
        # of the project: these were hardcoded Spanish, so the English UI
        # showed Spanish errors and makemessages could not see them.
        errors = {}
        if self.end_date and self.end_date < self.start_date:
            errors["end_date"] = _("The end date cannot be before the start date.")
        if self.purpose == "other" and not self.purpose_detail:
            errors["purpose_detail"] = _(
                "Describe the purpose when 'Other' is selected."
            )
        if self.operator_id and not self.operator.is_active:
            errors["operator"] = _("The selected operator is inactive.")
        if self.aircraft_id and (
            not self.aircraft.is_active or self.aircraft.status != "active"
        ):
            errors["aircraft"] = _("The selected aircraft is not available.")
        if (
            self.cost_center_id
            and self.operator_id
            and self.operator.cost_center_id not in (None, self.cost_center_id)
        ):
            errors["cost_center"] = _("The cost center does not match the operator's.")
        if (
            self.cost_center_id
            and self.aircraft_id
            and self.aircraft.cost_center_id not in (None, self.cost_center_id)
        ):
            errors["cost_center"] = _("The cost center does not match the aircraft's.")
        if errors:
            raise ValidationError(errors)


class Aerodrome(BaseModel):
    """R9.2: el catálogo de aeródromos que SIGO ofrece en "Aeródromo más
    Cercano (AMC)".

    La solicitud de vuelo pide dos datos que hoy se sacan a mano: **cuál es el
    aeródromo más cercano** al punto centro y **a cuántos kilómetros está**.
    Para calcularlo hace falta la posición, y para ofrecer el mismo nombre que
    SIGO espera hace falta su lista — de ahí este catálogo.

    **La lista se copia de SIGO, no se inventa** (decisión del usuario,
    2026-08-20: *"son solo esas las disponibles de momento, por lo cual se debe
    respetar"*). Es una lista global: trae Abu Dhabi y Taranto junto a los
    chilenos, porque así la muestra el sistema del Estado y ofrecer un nombre
    que su selector no tiene sería inútil.

    `latitude`/`longitude` son **opcionales a propósito**. Sembrar coordenadas
    inventadas para cincuenta aeródromos produciría una distancia con dos
    decimales y ningún respaldo; el seed sólo trae las de posición verificable
    y el resto queda en blanco, visible como "sin coordenadas" y completable
    desde la ficha. Un aeródromo sin posición no participa del cálculo, y la
    pantalla dice cuántos quedaron fuera en vez de fingir que los consideró.

    La regla que gobierna todo esto, y que `LV-93` dejó escrita a golpes: **la
    app propone, el papel manda**. El AMC calculado se confirma contra la carta
    AIP antes de presentar.
    """

    code = models.CharField(
        max_length=10,
        unique=True,
        verbose_name=_("ICAO code"),
        help_text=_("As SIGO lists it, e.g. SCEL."),
    )
    name = models.CharField(max_length=150)
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        validators=[
            MinValueValidator(Decimal("-90")),
            MaxValueValidator(Decimal("90")),
        ],
        help_text=_("Leave blank if unverified: it will not be used to compute AMC."),
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

    class Meta:
        verbose_name = _("aerodrome")
        verbose_name_plural = _("aerodromes")
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.name}"

    @property
    def is_locatable(self):
        """Si puede participar del cálculo de cercanía."""
        return self.latitude is not None and self.longitude is not None


class QualificationType(BaseModel):
    """Catalog of operator qualifications (B4.3), e.g. a DGAC rating per
    aircraft family.

    Free text drifted the same way document titles did (LV-1/LV-2): "Serie
    Mavic" vs "Mavic series" vs "MAVIC" for the same rating. A catalog keeps it
    consistent and gives B4.4 a structured place to declare which aircraft a
    rating authorizes.
    """

    name = models.CharField(max_length=150)
    code = models.CharField(max_length=50, unique=True)
    # B4.4: comma-separated, case-insensitive fragments matched against
    # Aircraft.model (Aircraft.type is uniformly "RPA" in the real data and
    # carries no signal). "mavic,matrice" means this rating authorizes any
    # aircraft whose model contains "mavic" or "matrice". Blank = matches
    # nothing until configured, so B4.4 stays silent rather than guessing.
    model_keywords = models.CharField(
        max_length=250,
        blank=True,
        verbose_name=_("Aircraft model keywords"),
        help_text=_(
            "Comma-separated fragments matched against the aircraft model "
            "(e.g. 'mavic, matrice'). Used to check operator–aircraft fit."
        ),
    )

    # LV-15: theme-aware, accessible Bootstrap "subtle" pairs used to colour the
    # equipment chips so each family is visibly differentiable at a glance.
    # `bg-danger` is deliberately absent -- it is reserved for expired chips.
    CHIP_PALETTE = (
        "bg-primary-subtle text-primary-emphasis",
        "bg-success-subtle text-success-emphasis",
        "bg-info-subtle text-info-emphasis",
        "bg-warning-subtle text-warning-emphasis",
        "bg-secondary-subtle text-secondary-emphasis",
        "bg-dark-subtle text-dark-emphasis",
    )

    class Meta:
        verbose_name = _("qualification type")
        verbose_name_plural = _("qualification types")

    def __str__(self):
        return self.name

    @property
    def chip_class(self):
        """LV-15: a stable colour class for this type's chips.

        Derived from `code` with a deterministic hash (crc32, not Python's
        per-process salted `hash()`) so the colour never shifts between
        requests or restarts, and every type -- present or future -- gets one
        without a migration or manual configuration.
        """
        index = zlib.crc32(self.code.encode("utf-8")) % len(self.CHIP_PALETTE)
        return self.CHIP_PALETTE[index]

    def keyword_list(self):
        return [k.strip().lower() for k in self.model_keywords.split(",") if k.strip()]


class Qualification(BaseModel):
    operator = models.ForeignKey(
        Operator, on_delete=models.PROTECT, related_name="qualifications"
    )
    qualification_type = models.ForeignKey(
        QualificationType,
        on_delete=models.PROTECT,
        related_name="qualifications",
    )
    # LV-12a: issue date is optional -- the imported roster records what an
    # operator is rated for, not when each rating was issued. Expiry likewise
    # optional (many DGAC ratings do not expire).
    issue_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = _("qualification")
        verbose_name_plural = _("qualifications")
        # The digest, the dashboard and generate_alerts all scan expiries.
        indexes = [
            models.Index(
                fields=["expiry_date", "is_active"], name="reg_qualification_exp_idx"
            )
        ]

    def __str__(self):
        return f"{self.qualification_type} · {self.operator}"


class KnowledgeAssessment(BaseModel):
    """LV-158: una prueba interna de conocimientos rendida por un operador.

    Pedido del usuario: *"una prueba interna para ver las capacidades […] al
    operador quedar en el historial […] con un aprobado o insuficiente, y en qué
    se equivocó, qué reforzar"*. Reglas suyas, del 2026-08-26: 25 preguntas, 80%
    para aprobar, vigencia de 12 meses.

    **`answers` guarda la copia de lo que se preguntó**, con lo marcado y lo
    correcto por fila. No es redundancia: el banco de preguntas es un archivo de
    datos que se va a corregir y ampliar, y sin la copia editar una redacción
    reescribiría lo que alguien rindió el año pasado. Es la misma decisión que
    `WeatherReview`, que guarda los números tal como se leyeron.

    **Append-only en la práctica**: no hay pantalla de edición. Una prueba se
    rinde de nuevo, no se corrige — y el historial de intentos es justamente lo
    que responde "cómo está la condición del profesional".
    """

    operator = models.ForeignKey(
        Operator,
        on_delete=models.PROTECT,
        related_name="knowledge_assessments",
        verbose_name=_("Operator"),
    )
    # Quién estaba con la sesión abierta al rendirla. Casi siempre es el usuario
    # del propio operador (`Operator.user`), pero se guarda aparte: la respuesta a
    # "quién rindió esto" no puede depender de que ese vínculo no cambie después.
    taken_by_user = models.ForeignKey(
        get_user_model(),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="knowledge_assessments_taken",
        verbose_name=_("Taken by"),
    )
    taken_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Taken at"))
    question_count = models.PositiveIntegerField(verbose_name=_("Questions"))
    correct_count = models.PositiveIntegerField(verbose_name=_("Correct answers"))
    score_percent = models.DecimalField(
        max_digits=5, decimal_places=1, verbose_name=_("Score (%)")
    )
    passed = models.BooleanField(verbose_name=_("Passed"))
    # La vigencia se guarda y no se calcula al leer: si mañana la regla cambia de
    # 12 a 24 meses, lo ya rendido conserva la vigencia con que se rindió. Mismo
    # criterio con que `R7.4` congela los umbrales al validar un entregable.
    expires_on = models.DateField(verbose_name=_("Valid until"))
    answers = models.JSONField(default=list, verbose_name=_("Answers"))

    class Meta:
        verbose_name = _("knowledge assessment")
        verbose_name_plural = _("knowledge assessments")
        ordering = ["-taken_at"]
        # LV-184: ver la **clave de respuestas** es un privilegio propio, no un
        # efecto secundario de poder leer la prueba.
        #
        # Hasta acá la revisión mostraba la respuesta correcta de cada pregunta
        # fallada **a quien acababa de rendirla**. Con eso se memoriza la clave y
        # se vuelve a rendir, y la prueba deja de medir: no queda un examen sino
        # un trámite. Y como un intento aprobado alimenta el motor de
        # vencimientos (`LV-173`), lo que se degrada no es una pantalla sino el
        # estado de cumplimiento de una persona.
        #
        # **Permiso propio y no `view_operator`**: quien supervisa el padrón no
        # es necesariamente quien puede ver la clave, y colgarlo de un permiso
        # existente lo repartiría a quien nunca se lo dieron. Va a `Compliance`
        # en `bootstrap_roles` y **no a `Operations`**, que es el rol de quien
        # rinde.
        permissions = [
            ("view_assessment_answers", "Can see the assessment answer key"),
        ]
        # El motor de alertas, el panel y la ficha barren la vigencia, igual que
        # con las habilitaciones.
        indexes = [
            models.Index(
                fields=["expires_on", "is_active"], name="reg_assessment_exp_idx"
            )
        ]

    def __str__(self):
        return f"{self.operator} · {self.taken_at:%Y-%m-%d}"

    @property
    def verdict(self):
        """ "Aprobado" o "Insuficiente", que son las dos palabras que pidió el usuario."""
        return _("Passed") if self.passed else _("Insufficient")

    @property
    def is_expired(self):
        """LV-29: una vigencia vencida. Nunca hay nulo acá, así que no hay tercer caso."""
        from django.utils import timezone

        return self.expires_on < timezone.localdate()

    @property
    def wrong_answers(self):
        """Las filas incorrectas: lo que hay que reforzar.

        Es la mitad del pedido —*"en qué se equivocó, qué reforzar"*— y sale de la
        copia guardada, no de recorrer el banco: así una pregunta corregida
        después no cambia lo que la revisión dice que pasó.
        """
        return [row for row in self.answers if not row.get("correct")]


# ── BLOQUE OPS (OPS-1): per-resource assignments + movement log ───────────────
# The old `Assignment` (operator+aircraft pair) stays for now; these anchor a
# single resource to a cost center over a period, so an operator can rotate
# contracts and a cost center can hold N aircraft without duplicating operators.
# `Operator.cost_center` / `Aircraft.cost_center` become a denormalization of the
# current assignment, maintained by the signal in apps/registry/signals.py.


class ResourceAssignment(BaseModel):
    """Shared base: a resource assigned to a cost center over a period."""

    STATUS_CHOICES = [
        ("planned", _("Planned")),
        ("active", _("Active")),
        ("ended", _("Ended")),
        ("cancelled", _("Cancelled")),
    ]
    # A resource "holds" a cost center while an assignment is in one of these.
    ACTIVE_STATUSES = frozenset({"planned", "active"})

    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    # R3.1: same closed vocabulary as FlightPermission/Assignment, optional
    # here too (blank=True) -- unchanged from before this field held free
    # text (LV-17's decision that this is a supplementary note, not a
    # mandatory classification, still holds).
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES, blank=True)
    purpose_detail = models.CharField(max_length=250, blank=True, default="")
    purpose_legacy = models.CharField(
        max_length=250, blank=True, default="", editable=False
    )

    class Meta:
        abstract = True

    def _resource_id(self):
        return getattr(self, f"{self.resource_field}_id")

    def _overlapping(self):
        """Other active assignments for the same resource whose period overlaps.

        Ranges overlap iff each starts on or before the other ends; a null
        end_date is an open-ended (still current) assignment.
        """
        queryset = type(self).objects.filter(
            is_active=True,
            status__in=self.ACTIVE_STATUSES,
            **{f"{self.resource_field}_id": self._resource_id()},
        )
        if self.pk:
            queryset = queryset.exclude(pk=self.pk)
        if self.end_date is not None:
            queryset = queryset.filter(start_date__lte=self.end_date)
        return queryset.filter(
            Q(end_date__isnull=True) | Q(end_date__gte=self.start_date)
        )

    def clean(self):
        errors = {}
        if self.end_date and self.end_date < self.start_date:
            errors["end_date"] = _("The end date cannot be before the start date.")
        if self.purpose == "other" and not self.purpose_detail:
            errors["purpose_detail"] = _(
                "Describe the purpose when 'Other' is selected."
            )
        resource = getattr(self, self.resource_field, None)
        if self._resource_id() and resource and not resource.is_active:
            errors[self.resource_field] = _("The selected resource is inactive.")
        if (
            self._resource_id()
            and self.status in self.ACTIVE_STATUSES
            and self._overlapping().exists()
        ):
            errors[self.resource_field] = _(
                "This resource already has an overlapping active assignment."
            )
        if errors:
            raise ValidationError(errors)


class OperatorAssignment(ResourceAssignment):
    resource_field = "operator"
    operator = models.ForeignKey(
        Operator, on_delete=models.PROTECT, related_name="cc_assignments"
    )
    cost_center = models.ForeignKey(
        CostCenter, on_delete=models.PROTECT, related_name="operator_assignments"
    )

    class Meta:
        verbose_name = _("operator assignment")
        verbose_name_plural = _("operator assignments")
        indexes = [
            models.Index(
                fields=["cost_center", "is_active"], name="reg_opassign_cc_idx"
            ),
            models.Index(fields=["operator", "end_date"], name="reg_opassign_op_idx"),
        ]
        # R3.1: declared here, not on the abstract ResourceAssignment --
        # this Meta does not subclass the parent's, so its constraints
        # would not otherwise be created (confirmed empirically:
        # makemigrations skipped it when it only lived on the abstract).
        constraints = [
            models.CheckConstraint(
                condition=~Q(purpose="other") | ~Q(purpose_detail=""),
                name="reg_opassign_other_purpose_requires_detail",
            )
        ]

    def __str__(self):
        return f"{self.operator} → {self.cost_center}"


class AircraftAssignment(ResourceAssignment):
    resource_field = "aircraft"
    aircraft = models.ForeignKey(
        Aircraft, on_delete=models.PROTECT, related_name="cc_assignments"
    )
    cost_center = models.ForeignKey(
        CostCenter, on_delete=models.PROTECT, related_name="aircraft_assignments"
    )

    class Meta:
        verbose_name = _("aircraft assignment")
        verbose_name_plural = _("aircraft assignments")
        indexes = [
            models.Index(
                fields=["cost_center", "is_active"], name="reg_acassign_cc_idx"
            ),
            models.Index(fields=["aircraft", "end_date"], name="reg_acassign_ac_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~Q(purpose="other") | ~Q(purpose_detail=""),
                name="reg_acassign_other_purpose_requires_detail",
            )
        ]

    def __str__(self):
        return f"{self.aircraft} → {self.cost_center}"


class AppendOnlyLogQuerySet(models.QuerySet):
    """Block bulk mutation so the movement log stays append-only (like AuditEvent)."""

    def update(self, **kwargs):
        raise ValidationError("ResourceMovementLog records are append-only.")

    def delete(self):
        raise ValidationError("ResourceMovementLog records are append-only.")

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError("ResourceMovementLog records are append-only.")


class ResourceMovementLog(BaseModel):
    """Immutable trail of resource↔cost-center movements (the OPS-1 headline).

    Written by the assignment signal whenever a resource's current cost center
    changes. Not deleted or edited; that is the whole point of the trail.
    """

    RESOURCE_CHOICES = [("operator", _("Operator")), ("aircraft", _("Aircraft"))]
    MOVEMENT_CHOICES = [
        ("assigned", _("Assigned")),
        ("reassigned", _("Reassigned")),
        ("released", _("Released")),
        ("location_changed", _("Location changed")),  # OPS-3
    ]

    # `created_at` alone cannot order two rows created moments apart: on this
    # machine `timezone.now()` returns the *identical* value across rapid
    # successive calls (coarse clock resolution), and SQL gives no ordering
    # guarantee for ties on a non-unique column -- confirmed by
    # test_changing_cost_center_logs_reassigned flipping order under load.
    # `sequence` is computed in save() as "latest + 1" (same idiom as
    # GeoPlanVersion.version_number) instead of AutoField: Django requires an
    # AutoField to be the primary key, and BaseModel.id stays a UUID PK.
    sequence = models.PositiveBigIntegerField(editable=False)
    resource_kind = models.CharField(max_length=20, choices=RESOURCE_CHOICES)
    resource_id = models.UUIDField()
    movement = models.CharField(max_length=20, choices=MOVEMENT_CHOICES)
    from_cost_center = models.ForeignKey(
        CostCenter, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    to_cost_center = models.ForeignKey(
        CostCenter, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    detail = models.CharField(max_length=250, blank=True)
    changed_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    objects = AppendOnlyLogQuerySet.as_manager()

    class Meta:
        verbose_name = _("resource movement")
        verbose_name_plural = _("resource movements")
        ordering = ["-sequence"]
        indexes = [
            models.Index(fields=["-sequence"], name="reg_movement_seq_idx"),
            models.Index(
                fields=["resource_kind", "resource_id", "-sequence"],
                name="reg_movement_res_idx",
            ),
        ]

    def __str__(self):
        return f"{self.resource_kind}:{self.resource_id} {self.movement}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("ResourceMovementLog records are append-only.")
        # No uniqueness is enforced on this value: a rare race between two
        # concurrent writers computing the same "latest + 1" just means two
        # rows tie, no worse than the wall-clock collision this replaces, and
        # this app's write volume for movement events is low (docs/postgresql-
        # readiness.md: single-writer scale until real concurrency arrives).
        latest = ResourceMovementLog.objects.order_by("-sequence").first()
        self.sequence = (latest.sequence if latest else 0) + 1
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("ResourceMovementLog records are append-only.")
