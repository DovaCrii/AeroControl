from datetime import date, datetime, timedelta
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


# LV-218: el IFIS de la DGAC, donde se consultan los NOTAM vigentes.
#
# Constante y no `settings`: es una dirección pública de un organismo del Estado,
# no una configuración de despliegue — no cambia entre desarrollo y producción, y
# ponerla en el entorno obligaría a declararla en cada instalación para que el
# enlace funcione. Si algún día la DGAC la muda, se cambia acá y hay un test que
# lo nota.
NOTAM_QUERY_BASE = "https://aipchile.dgac.gob.cl/notam"


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
    # LV-155: la línea que el usuario declaró, textual: *"completado no debe
    # salir luego de aprobado; es caducado y final se archiva […] esa es la
    # línea"*. `Solicitado → Aprobado`, y de ahí caduca (lo hace solo
    # `expire_permissions`, LV-83) o se archiva.
    #
    # Revierte la mitad de `LV-83` que distinguía completado de caducado. Se
    # retira **de la pantalla, no de la base**: el valor sigue en
    # `STATUS_CHOICES` porque hay filas en producción que lo tienen
    # (`JEJ-2026-003`) y porque el filtro del listado tiene que poder
    # encontrarlas — decisión del usuario, paso 1 del retiro, igual que `LV-78`
    # y `LV-103`. Sin migración de datos y reversible.
    STATUS_FLOW = [STATUS_REQUESTED, STATUS_APPROVED]
    # LV-193: los estados que ninguna pantalla vuelve a **ofrecer**, aunque haya
    # filas que los tengan. `LV-155` sacó `completed` del flujo y del stepper y
    # **el selector de "Corregir el estado" quedó fuera**: seguía listando
    # `STATUS_CHOICES` completo, así que la pantalla que existe para arreglar un
    # estado equivocado era la que podía volver a escribir el estado retirado —
    # y el defecto que `LV-101` encontró era, textual, alguien deshaciendo un
    # "completado" puesto por error. El usuario lo vio en `JEJ-2026-003`, que es
    # justamente la fila que tiene el valor en producción.
    #
    # Declarado acá y no como un `if` en el formulario, por lo mismo que
    # `STATUS_FLOW`: el retiro de un estado toca varias pantallas y ya se
    # demostró que una se queda atrás. El día que se retire otro, esto es lo
    # único que se edita.
    #
    # Sigue siendo **retiro de pantalla y no de base**: el valor permanece en
    # `STATUS_CHOICES` para que el filtro del listado encuentre las filas que lo
    # tienen, y corregir un permiso *desde* `completed` hacia otro estado sigue
    # siendo posible — es lo único que se puede hacer con esas filas.
    RETIRED_STATUSES = frozenset({STATUS_COMPLETED})
    # LV-157: con qué estado puede **nacer** un permiso. Aprobar y completar
    # exigen la autorización firmada de la DGAC en ficha
    # (`RequireDgacPermitPdfMixin`), y en el alta esa compuerta no se puede
    # cumplir: no hay dónde adjuntar un documento a un permiso que todavía no
    # existe. Ofrecer "Aprobado" en el desplegable del alta era entonces una
    # puerta trasera alrededor de la única regla que el usuario llamó crítica --
    # exactamente la que `LV-101` cerró en la pantalla de edición y que nadie fue
    # a mirar en el alta. Aprobar es siempre la transición guardada.
    CREATABLE_STATUSES = frozenset({STATUS_REQUESTED, STATUS_DENIED})
    # LV-219: los estados en los que la vigencia **ya tiene que estar**, y por
    # contraste los dos en que puede faltar.
    #
    # Textual del usuario: *"voy a pedir un permiso pero no sé cuándo parte la
    # vigencia; ésta me la da cuando entro al SIGO de la DGAC, antes yo no lo
    # sé"*. La vigencia **no es un dato del solicitante**: la fija la DGAC al
    # responder. Exigirla en el alta obligaba a inventar dos fechas, y esas
    # fechas no se quedan quietas — alimentan el motor de vencimientos, la lista
    # del panel, el informe y `expire_permissions`, así que una invención se
    # convierte en avisos falsos y en un permiso que "caduca" sin que la DGAC lo
    # haya dicho.
    #
    # Es el mismo caso que `LV-39` resolvió para `permission_number` (opcional
    # hasta que llega el folio, porque *"un permiso se arma mientras está todavía
    # solicitado"*) y que `LV-157` resolvió para el estado de nacimiento. Las
    # fechas eran el tercer dato de ese mismo trámite y quedaron fuera.
    #
    # `denied` también admite nulos, y no por descuido: un permiso rechazado
    # **nunca tuvo vigencia**, porque no hubo autorización. Escribirle fechas
    # sería inventar una autorización que no existió.
    #
    # Declarado acá y no como un `if` en el formulario por lo que ya pasó dos
    # veces en este modelo: `LV-156` encontró que la regla del folio vivía sólo
    # en `FlightPermissionForm.clean` y el botón que aprueba de verdad no la
    # comprobaba. Una regla forms-only es una regla evadible.
    REQUIRE_VALIDITY_STATUSES = frozenset(
        {STATUS_APPROVED, STATUS_COMPLETED, STATUS_EXPIRED}
    )
    # LV-224: la DGAC autoriza **3 meses** como máximo. Dato de dominio que el
    # usuario aportó al armar el informe mensual de reportabilidad
    # (`SPEC_REPORTE_MENSUAL_RPA.md` §4.1), y que gobierna todo el calendario:
    # la renovación no es automática, exige una carta nueva del mandante.
    #
    # **Meses calendario, no 90 días.** El criterio de aceptación del informe lo
    # fija con un ejemplo —un permiso emitido el 2026-07-04 vence el
    # 2026-10-04— y eso es `+3 meses`, no `+90 días`, que caería el 02-10. La
    # diferencia son dos días de vigencia real, y con ella la fecha en que
    # `expire_permissions` cierra el permiso y en que se dispara cada alerta.
    #
    # Es el techo del **rango declarado** (`valid_until - valid_from`), no de la
    # fecha de emisión: `FlightPermission` guarda la ventana que dice la
    # autorización, y es esa ventana la que no puede pasar de tres meses.
    MAX_VALIDITY_MONTHS = 3
    # Two terminal states now (LV-83). They differ in one way that matters for
    # the stepper: `denied` is only ever reached from the first step, while a
    # permit can expire from anywhere -- see `status_steps` below.
    #
    # LV-155: `completed` se suma acá al salir de `STATUS_FLOW`. Sin esto, un
    # permiso legado que quedó completado tiene un estado que no está ni en el
    # flujo ni entre los bloqueados, y `status_steps_for` dibuja **todos** los
    # pasos en "pendiente" — la ficha diría que un permiso terminado no ha
    # empezado. Como bloqueado se dibuja lo que de verdad pasó: llegó hasta
    # aprobado y ahí se detuvo.
    STATUS_BLOCKED = [STATUS_DENIED, STATUS_EXPIRED, STATUS_COMPLETED]
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
    # LV-219: nulas mientras la DGAC no haya respondido. Ver
    # `REQUIRE_VALIDITY_STATUSES` arriba para el por qué y para dónde se exigen.
    #
    # **Un nulo acá significa "todavía no se sabe", y no es ni "vigente" ni
    # "vencido"** — el mismo tercer estado que `LV-29` fijó para una vigencia que
    # nunca se ingresó. Sale gratis en casi todos los lectores porque SQL no hace
    # coincidir un NULL en una comparación: `expire_permissions` no lo caduca,
    # `permit_counts` no lo cuenta como vigente ni como vencido (y ya tenía
    # `awaiting`, que es exactamente este grupo), el calendario no lo dibuja y la
    # lista de vencimientos no lo anuncia. Los dos sitios que **sí** hacían
    # aritmética con las fechas están tratados a mano: la validación del registro
    # de vuelo (`FlightRecordForm.clean`) y la compuerta de aprobación.
    valid_from = models.DateField(null=True, blank=True)
    valid_until = models.DateField(null=True, blank=True)
    # LV-224: la salida para el caso excepcional, con el mismo criterio que
    # `LV-101` usó para corregir un estado — lo excepcional se permite, pero deja
    # un motivo escrito.
    #
    # **Sin esto, la regla de los 3 meses obligaría a falsear una fecha** el día
    # que la DGAC otorgue un plazo distinto (una prórroga, una resolución
    # particular), que es exactamente el mal que `LV-219` acaba de quitar del
    # alta. La app registra lo que dice el papel; si el papel dice otra cosa,
    # tiene que poder cargarse y quedar dicho por qué.
    #
    # Vacío no es "no aplica" sino "no hizo falta": sólo se lee cuando el rango
    # excede el máximo. Un motivo escrito con un rango normal no cambia nada.
    validity_override_reason = models.CharField(
        max_length=250,
        blank=True,
        default="",
        verbose_name=_("Reason for exceeding the maximum validity"),
    )
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
    # LV-220: de dónde salió cada una de las dos de arriba.
    #
    # El hallazgo que obligó a esto: `fill_permission_from_plan` escribe región y
    # comuna **deducidas** de las coordenadas —punto en polígono sobre la capa de
    # la BCN— en estos mismos campos, así que una región que salió de un polígono
    # y una copiada del papel DGAC quedaban **indistinguibles** en la base y en la
    # ficha. Y la capa está simplificada a ~111 m: cerca del borde devuelve la
    # comuna vecina, y fuera de cobertura no devuelve nada. Presentar eso como si
    # lo hubiera declarado la autoridad es exactamente lo que `LV-141` vino a
    # evitar en la hoja SIGO, donde el aviso de procedencia sí está a la vista.
    #
    # Sólo estas dos llevan marcador, y no las demás que `fill_location_gaps`
    # completa, porque **sólo estas dos son una inferencia**: el centro, el radio
    # y el nombre del área se transcriben del KMZ que alguien preparó y subió, que
    # es un documento declarado. La región y la comuna no vienen en el KMZ: las
    # calcula `geo.administrative.locate()`.
    LOCATION_DECLARED = "declared"
    LOCATION_DERIVED = "derived"
    LOCATION_SOURCE_CHOICES = [
        (LOCATION_DECLARED, _("Declared")),
        (LOCATION_DERIVED, _("Derived from the coordinates")),
    ]
    # Vacío es un **tercer estado con significado: no se sabe**, y es el defecto a
    # propósito. Los permisos que ya existen se cargaron antes de que hubiera
    # marcador, así que no hay forma honesta de saber cuáles se teclearon y cuáles
    # salieron del polígono: poner `declared` en la migración inventaría una
    # procedencia para miles de filas, que es justo el defecto que esta fila
    # denuncia. Vacío se dibuja como hoy —el valor a secas, sin aviso—, así que
    # nada retrocede y lo nuevo sí queda marcado.
    region_source = models.CharField(
        max_length=10, blank=True, choices=LOCATION_SOURCE_CHOICES
    )
    commune_source = models.CharField(
        max_length=10, blank=True, choices=LOCATION_SOURCE_CHOICES
    )
    # LV-137: el aeródromo más cercano y su distancia, que hasta acá sólo existían
    # en la solicitud SIGO. Textual del usuario, sobre el expediente del permiso:
    # *"ese tiene además la información faltante para llenar el permiso, sobre
    # todo el tema de distancia punto central la distancia al aeródromo"*. El plan
    # geoespacial los calcula y la solicitud los guardaba; el permiso —que es la
    # ficha donde se consulta el trámite— no tenía dónde ponerlos, así que el dato
    # se perdía en el camino y había que volver al plan a buscarlo.
    #
    # Definidos igual que en `FlightRequest`, a propósito: dos formas distintas
    # del mismo dato en el mismo proyecto es cómo empiezan a discrepar.
    amc = models.ForeignKey(
        "registry.Aerodrome",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="flight_permissions",
        verbose_name=_("Nearest aerodrome (AMC)"),
        help_text=_("Proposed by distance; confirm against the AIP chart."),
    )
    # Se guarda además de calcularse: es el número que quedó en el papel, y tiene
    # que seguir diciendo lo mismo aunque mañana alguien corrija la coordenada del
    # aeródromo en su ficha (misma lección que `LV-118` dejó en las alertas).
    amc_distance_km = models.DecimalField(
        max_digits=7,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        verbose_name=_("Distance to AMC (km)"),
    )
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
    # LV-221: la altitud pasa a **metros**, que es como se opera. Textual del
    # usuario: *"sumar eso, la altitud es en unidad metros como trabajamos"*.
    #
    # **La unidad anterior no era un rótulo desafortunado, era una fábrica de
    # errores, y el propio repo lo tenía escrito.** El comentario de
    # `fill_location_gaps` (más abajo) advertía que copiar el número tal cual
    # *"convertiría 120 m en 120 ft, un tercio de la altura real y sin que nada
    # avise"* — y eso es exactamente lo que pasó, porque esa conversión protegía
    # la ruta del KMZ y **el formulario manual no tenía ninguna**. Medido en
    # producción: los tres permisos con el campo cargado decían `120`, y los tres
    # eran metros (confirmado por el usuario).
    #
    # Tercera señal de que la unidad estaba mal elegida: `FlightRequest.altitude_m`
    # **ya guardaba metros**, así que dos modelos que describen el mismo vuelo
    # usaban unidades distintas.
    #
    # La conversión a pies se calcula para mostrar (`max_altitude_ft_equivalent`),
    # porque el formulario del SIGO la pide así y transcribirla a mano es la clase
    # de error que `LV-171` vino a reducir. Pero lo que se **guarda** es lo que la
    # persona escribió.
    max_altitude_m = models.PositiveIntegerField(null=True, blank=True)
    # ⚠️ **Se conserva, y no es un descuido: es el valor original tal como se
    # escribió.** Retiro de pantalla y no de base, el patrón de `LV-78`, `LV-103`
    # y `LV-155`: sale del formulario y de la ficha, la migración copia su número
    # a `max_altitude_m`, y la columna queda por si alguna de las tres solicitudes
    # ya se presentó al SIGO con el valor de antes y hay que reconstruir qué se
    # declaró. Nada la vuelve a escribir.
    #
    # **CONDICIÓN DE CIERRE** (escrita el 2026-09-02, que es cuando todavía se
    # sabe por qué existe): cuando se confirme que **ninguna de las tres
    # solicitudes de `CC691` se presentó al SIGO con el valor viejo**, esta
    # columna se puede borrar con su migración. Un paso 1 sin condición de cierre
    # es deuda con intereses: el repo lleva seis retiros "de pantalla y no de
    # base" y el paso 2 no se decidió ninguna vez, porque para cuando alguien
    # mira la columna ya nadie recuerda de qué dependía.
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

    @classmethod
    def from_db(cls, db, field_names, values, **kwargs):
        """LV-220: recordar con qué región y comuna vino la fila desde la base.

        Es la mitad que hace honesto al marcador de procedencia. Marcar
        `derived` al deducir no alcanza: si después alguien **corrige a mano** una
        región mal deducida —y se deduce mal, la capa de la BCN está simplificada
        a ~111 m y cerca del borde devuelve la vecina—, el marcador viejo seguiría
        diciendo "deducido de las coordenadas" sobre un valor que ya no lo es. Un
        aviso de procedencia equivocado es peor que ninguno: el primero se cree.

        Se compara contra lo cargado y no contra un `update_fields`, porque el
        formulario, el admin y los comandos guardan de tres formas distintas y
        sólo dos de ellas lo pasan.

        `**kwargs` y no la firma explícita: Django 6.1 le sumó `fetch_mode`, y
        copiar la firma de esta versión es cómo el próximo parámetro que agreguen
        rompe cada lectura de permisos con un `TypeError`.
        """
        instance = super().from_db(db, field_names, values, **kwargs)
        for name in ("region", "commune"):
            if name in field_names:
                setattr(instance, f"_loaded_{name}", getattr(instance, name))
        return instance

    def _reconcile_location_sources(self):
        """Un valor cambiado a mano deja de ser deducido.

        Devuelve qué columnas de procedencia tocó, porque quien guarda con
        `update_fields` tiene que sumarlas: sin eso el marcador se corrige en
        memoria y no llega a la base, que es la clase de falla que no se nota
        hasta que alguien lee la ficha meses después.
        """
        touched = []
        for name in ("region", "commune"):
            value = getattr(self, name)
            # Un permiso recién creado con región **no puede** traerla deducida:
            # `fill_location_gaps` sólo rellena huecos de permisos que ya
            # existen, así que lo único que escribe una región al crear es
            # alguien copiándola del papel o un importador que lee ese papel. Sin
            # esto quedarían todos en blanco —"no se sabe"— cuando sí se sabe.
            if self._state.adding:
                if value and not getattr(self, f"{name}_source"):
                    setattr(self, f"{name}_source", self.LOCATION_DECLARED)
                continue
            loaded = getattr(self, f"_loaded_{name}", None)
            if loaded is None or value == loaded:
                continue
            # Vaciarlo no es declararlo: un campo en blanco no tiene procedencia,
            # y dejarle `declared` afirmaría que alguien declaró la nada.
            setattr(
                self,
                f"{name}_source",
                self.LOCATION_DECLARED if getattr(self, name) else "",
            )
            setattr(self, f"_loaded_{name}", getattr(self, name))
            touched.append(f"{name}_source")
        return touched

    def save(self, *args, **kwargs):
        touched = self._reconcile_location_sources()
        update_fields = kwargs.get("update_fields")
        if touched and update_fields is not None:
            kwargs["update_fields"] = list(dict.fromkeys([*update_fields, *touched]))
        if self._state.adding and not self.internal_folio:
            with transaction.atomic():
                self.internal_folio = self._next_internal_folio()
                return super().save(*args, **kwargs)
        return super().save(*args, **kwargs)

    @property
    def notam_url(self):
        """LV-218, paso (a): la consulta de NOTAM del IFIS para este permiso.

        Idea del usuario: *"no sé si existe una forma de cruzar el clima con las
        NOTAM y el sector del permiso para informar la situación"*.

        **Devuelve un enlace y no un resultado, y eso es la decisión de la fila.**
        Investigado el 2026-09-01: el IFIS de la DGAC
        (`aipchile.dgac.gob.cl`, Symfony operado por VIA56) **no tiene API ni
        feed** — todo son `GET` con respuesta HTML. Consultar y parsear es
        posible, y de hecho cada NOTAM trae centro y radio en su campo `Q)`
        (`3324S07048W005` son 33°24'S, 70°48'W y radio 5 NM), así que el cruce
        geométrico contra la coordenada del permiso se puede calcular.

        Lo que hace preferible el enlace **primero** es el riesgo asimétrico: un
        parseo que falla —porque el sitio cambió su HTML, o no respondió— se lee
        con demasiada facilidad como *"no hay avisos"*, y esta fila declaró desde
        el principio que eso es lo que no puede pasar. Un enlace no afirma nada:
        lleva a la fuente oficial y quien decide vuela mirándola. Además evita
        consultar un servicio público del Estado en cada carga de página, que es
        una cuestión de trato y no sólo de rendimiento.

        Se apoya en el aeródromo que el permiso **ya declara** (`amc`, de
        `LV-137`) porque la búsqueda del IFIS es por designador OACI y no por
        coordenadas: `Aerodrome.code` es exactamente lo que el formulario pide.
        Sin aeródromo declarado no hay enlace — devuelve `None` y la ficha no lo
        dibuja, en vez de mandar a una búsqueda vacía.
        """
        if self.amc_id is None:
            return None
        code = (self.amc.code or "").strip()
        if not code:
            return None
        # `quote` aunque un designador OACI sea alfanumérico: el día que alguien
        # cargue un código con un espacio, esto no arma una URL rota.
        from urllib.parse import quote

        return f"{NOTAM_QUERY_BASE}?designador={quote(code)}&metodo=designador"

    @property
    def max_altitude_ft_equivalent(self):
        """LV-221: la altitud en pies, para transcribir al formulario del SIGO.

        Se **calcula** y no se guarda: el dato es el que la persona escribió en
        metros, y una segunda columna con el mismo hecho en otra unidad es dos
        columnas que se desincronizan. La app tenía justamente ese problema al
        revés —`FlightPermission` en pies y `FlightRequest.altitude_m` en metros—
        y de ahí salió esta fila.

        Se muestra al lado del valor en metros porque el trámite pide pies, y
        calcularlo a mano cada vez es la clase de error que `LV-171` vino a
        reducir. `round` porque la casilla del SIGO no admite decimales.

        1 m = 3.28084 ft, el mismo factor que usaba la conversión que esta fila
        eliminó y que `check_altitudes` usa para el diagnóstico.
        """
        if self.max_altitude_m is None:
            return None
        return round(self.max_altitude_m * 3.28084)

    def latest_allowed_valid_until(self):
        """La última fecha de término que la DGAC podría haber autorizado (LV-224).

        `valid_from` más `MAX_VALIDITY_MONTHS` meses **calendario**. Devuelve
        `None` si no hay fecha de inicio, porque sin ella no hay techo que medir —
        y eso pasa a menudo desde `LV-219`.

        **Suma de meses a mano, con `calendar`, y no `relativedelta`.**
        `python-dateutil` está en el árbol pero sólo de forma transitiva (lo trae
        `openpyxl`), así que usarlo obligaría a declararlo — que es lo que se hizo
        con `lxml` cuando el parser de KML pasó a depender de él. Para **una**
        operación, seis líneas de biblioteca estándar cuestan menos que una
        dependencia declarada más, y es el mismo criterio con el que este repo
        eligió `reportlab` sobre `weasyprint`.

        El recorte del día (`min` contra el último del mes) da el mismo resultado
        que `relativedelta`: el 30 de noviembre más tres meses es el 28 (o 29) de
        febrero, no un 30 que no existe.
        """
        import calendar

        if self.valid_from is None:
            return None
        month_index = self.valid_from.month - 1 + self.MAX_VALIDITY_MONTHS
        year = self.valid_from.year + month_index // 12
        month = month_index % 12 + 1
        day = min(self.valid_from.day, calendar.monthrange(year, month)[1])
        return date(year, month, day)

    def clean(self):
        errors = {}
        # LV-157: espejo en el modelo de la regla del formulario, como exige
        # AGENTS.md. `objects.create()` sigue libre a propósito -- no llama
        # `full_clean`, y es el camino de los importadores y de los tests que
        # necesitan montar un permiso ya aprobado sin simular el trámite.
        if self._state.adding and self.status not in self.CREATABLE_STATUSES:
            errors["status"] = _(
                "A new permit starts as requested or denied. Approving requires "
                "the signed DGAC authorization on file, which can only be "
                "attached once the permit exists."
            )
        if self.valid_until and self.valid_from and self.valid_until < self.valid_from:
            errors["valid_until"] = _("The end date cannot be before the start date.")
        # LV-224: el techo de 3 meses, y su salida.
        if (
            self.valid_from
            and self.valid_until
            and self.valid_until > self.latest_allowed_valid_until()
            and not self.validity_override_reason.strip()
        ):
            errors["valid_until"] = _(
                "The DGAC authorises three months at most, so this window cannot "
                "end after %(limit)s. If the authorisation really says otherwise, "
                "write the reason in the field below and it will be recorded."
            ) % {"limit": self.latest_allowed_valid_until().isoformat()}
        # LV-219: la vigencia puede faltar mientras la DGAC no responda, pero un
        # permiso autorizado sin vigencia sería una autorización sin plazo — y el
        # motor de vencimientos no tendría de dónde agarrarse para cerrarlo.
        if self.status in self.REQUIRE_VALIDITY_STATUSES:
            for field in ("valid_from", "valid_until"):
                if getattr(self, field) is None:
                    errors[field] = _(
                        "An approved permit needs its validity window: it is "
                        "on the DGAC authorization."
                    )
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

    def fill_location_gaps(
        self,
        *,
        latitude=None,
        longitude=None,
        radius_m=None,
        commune="",
        region="",
        area_name="",
        altitude_m=None,
        amc=None,
        amc_distance_km=None,
        save=True,
    ):
        """R10: completar la ubicación con lo que trae el KMZ, sin pisar nada.

        Vive en el modelo porque es **el permiso rellenándose a sí mismo**, y
        porque la regla que lo restringe —`clean()`, tres líneas más arriba: la
        latitud y la longitud van juntas, y un radio sin par de coordenadas es
        error— tiene que quedar a la vista de quien toque esto.

        `R10.2`: se extrajo de `link_to_permission`, que lo hacía sólo para una
        solicitud SIGO. Ahora las dos fuentes que existen —la solicitud, y el
        plan geoespacial que se vincula directamente— llaman acá, en vez de
        llevar cada una su copia de la aritmética. Una segunda copia es
        exactamente cómo una de las dos habría dejado de convertir los metros.

        **Rellenar y no pisar**: si el permiso ya trae una coordenada, la que
        manda es la suya — puede venir del papel DGAC, que es de más autoridad
        que lo que se preparó antes de presentar. Devuelve la lista de campos
        que completó, para que la pantalla diga qué cambió en vez de dejar a la
        persona comparando.

        Las coordenadas se escriben **de a par** (`clean()` lo exige), así que
        se completan sólo cuando faltan las dos: media coordenada nueva sobre
        media vieja sería un punto que no existe.
        """
        from decimal import Decimal

        filled = []
        if (
            self.latitude is None
            and self.longitude is None
            and latitude is not None
            and longitude is not None
        ):
            self.latitude = latitude
            self.longitude = longitude
            filled += ["latitude", "longitude"]
        # El radio va después y mira `self.latitude`, no el argumento: si el
        # permiso no quedó con coordenadas, guardar un radio lo dejaría
        # inválido para su propio `clean()`.
        if self.radius_km is None and radius_m and self.latitude is not None:
            self.radius_km = Decimal(radius_m) / Decimal(1000)
            filled.append("radius_km")
        # LV-220: la procedencia se marca **en el mismo lugar donde se escribe el
        # valor**. Separarlas es cómo una de las dos se olvida.
        #
        # `_loaded_*` se pone al día junto con el valor para que
        # `_reconcile_location_sources` no lea esta escritura como una corrección
        # a mano y le dé vuelta el marcador que acabamos de poner. Y las dos
        # columnas viajan aparte de `filled`, porque `filled` es lo que la
        # pantalla le enumera a la persona: un "se completó region_source" no le
        # dice nada a nadie.
        sources = []

        def _mark_derived(name):
            setattr(self, f"{name}_source", self.LOCATION_DERIVED)
            setattr(self, f"_loaded_{name}", getattr(self, name))
            sources.append(f"{name}_source")

        if not self.commune and commune:
            self.commune = commune
            filled.append("commune")
            _mark_derived("commune")
        # LV-141: la región, que existía como campo desde OPS-4 y **nunca se
        # rellenaba** porque no había de dónde sacarla. Ahora sale del mismo
        # polígono administrativo que la comuna, así que van a la par -- pero cada
        # una respeta lo que ya estuviera escrito, por separado: un permiso puede
        # traer la región del papel y la comuna en blanco.
        if not self.region and region:
            self.region = region
            filled.append("region")
            _mark_derived("region")
        if not self.area_name and area_name:
            self.area_name = area_name
            filled.append("area_name")
        if self.max_altitude_m is None and altitude_m:
            # LV-221: **ya no hay conversión que hacer, y eso es el punto.**
            #
            # Acá vivía `round(altitude_m * 3.28084)` con un comentario que
            # explicaba que la conversión era obligatoria porque copiar el número
            # tal cual "convertiría 120 m en 120 ft, un tercio de la altura real y
            # sin que nada avise". El razonamiento era correcto y la defensa
            # funcionaba — en este camino. El del formulario manual no la tenía, y
            # por ahí entraron los tres `120` que producción tenía cargados.
            #
            # Con el permiso guardando metros, el plan trae metros y el permiso
            # los recibe sin tocar: la clase de error desaparece en vez de quedar
            # cubierta en una ruta y descubierta en la otra.
            self.max_altitude_m = altitude_m
            filled.append("max_altitude_m")
        # LV-137: el aeródromo y su distancia van **de a par**, por la misma razón
        # que las coordenadas: una distancia sin aeródromo no se puede leer, y un
        # aeródromo sin distancia obliga a recalcularla para saber qué declarar.
        if (
            self.amc_id is None
            and self.amc_distance_km is None
            and amc is not None
            and amc_distance_km is not None
        ):
            self.amc = amc
            self.amc_distance_km = amc_distance_km
            filled += ["amc", "amc_distance_km"]
        if filled and save:
            self.save(update_fields=filled + sources + ["updated_at"])
        return filled


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
