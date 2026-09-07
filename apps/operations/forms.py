from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.core.forms import AeroModelForm
from apps.geo.models import GeoPlan
from apps.registry.models import Aircraft, Operator
from .models import (
    FlightPermission,
    FlightRecord,
    FlightRequest,
    FlightRequestNote,
    FlightRequestWorkItem,
    NotamReview,
)


class FlightPermissionForm(AeroModelForm):
    # LV-153: el alta pedía a mano las ocho casillas de geografía que el plan
    # geoespacial ya sabe. Textual del usuario: *"el permiso de vuelo: estos
    # datos debe extraerlos desde el KMZ […] para que saque esta información
    # faltante"*. La mitad existía y llegaba tarde: `R10.2`/`LV-137` rellenan
    # esos huecos **al vincular un plan**, pero eso ocurre en la ficha del
    # permiso ya creado.
    #
    # Se elige un plan **ya subido**, no se sube un KMZ: la dirección la fijó el
    # propio usuario en `LV-137` — *"el plan geoespacial no se debe importar, se
    # debe llamar desde el geoespacial que se crea dentro de la app"*.
    #
    # El relleno ocurre **al guardar**, no al elegir. Recargar la página para
    # rellenar habría borrado todo lo demás que la persona ya tipeó, que es
    # justamente lo que `LV-154` viene a evitar.
    source_plan = forms.ModelChoiceField(
        queryset=None,
        required=False,
        label=_("Bring the data from a geospatial plan"),
        help_text=_(
            "On save, the boxes you leave empty are filled from that plan's "
            "KMZ: centre point, radius, commune, region and nearest aerodrome. "
            "Nothing you typed is overwritten."
        ),
    )

    class Meta:
        model = FlightPermission
        # LV-39: status first, then the number -- a permit is built while it is
        # still "requested" (or "denied"), before it has a DGAC folio.
        fields = [
            "status",
            "permission_number",
            "operators",
            "aircraft_fleet",
            "cost_center",
            "purpose",
            "purpose_detail",
            "valid_from",
            "valid_until",
            # LV-224: va **inmediatamente después** de las dos fechas, porque el
            # mensaje de error remite a "el campo de abajo". Un campo de escape
            # separado de la regla que lo activa es un campo que nadie encuentra.
            "validity_override_reason",
            "location",
            "region",
            "commune",
            "area_name",
            "latitude",
            "longitude",
            "radius_km",
            # LV-221: metros, no pies. `max_altitude_ft` sale del formulario y se
            # queda en la base como el valor original (ver el modelo).
            "max_altitude_m",
            "area_type",
        ]
        # LV-22: without explicit labels the auto-generated English ones ("Permission
        # number", "Valid from"…) fell through the catalog and rendered in English
        # inside the Spanish UI.
        labels = {
            "status": _("Status"),
            "permission_number": _("Permission number"),
            "operators": _("Operators"),
            "aircraft_fleet": _("Aircraft fleet"),
            "cost_center": _("Cost center"),
            "purpose": _("Purpose"),
            "purpose_detail": _("Purpose detail"),
            "valid_from": _("Valid from"),
            "valid_until": _("Valid until"),
            "validity_override_reason": _("Reason for exceeding the maximum validity"),
            "location": _("Location"),
            "region": _("Region"),
            "commune": _("Commune"),
            "area_name": _("Area or site name"),
            "latitude": _("Latitude"),
            "longitude": _("Longitude"),
            "radius_km": _("Radius (km)"),
            "max_altitude_m": _("Maximum altitude (m)"),
            "area_type": _("Area type"),
        }
        help_texts = {
            # LV-156: dice **de dónde sale** el número, no sólo que hace falta.
            # Es el folio de la autorización firmada que la DGAC devuelve, el
            # mismo PDF que la compuerta de aprobación exige tener en ficha.
            "permission_number": _(
                "Optional until the permission is approved. It is the folio on "
                "the signed DGAC authorization."
            ),
            # LV-219: mismo criterio que el folio de arriba — dice **de dónde
            # sale** la fecha, no sólo que puede quedar vacía. La entrega la DGAC
            # al responder, y hasta entonces nadie la sabe.
            "valid_from": _(
                "Optional until the permission is approved. The DGAC sets the "
                "validity window on the authorization it issues."
            ),
            # LV-224: el máximo se dice **siempre**, no sólo cuando alguien se
            # equivoca. Un tope que se aprende chocando con un error de validación
            # es un tope que ya costó un intento.
            "valid_until": _(
                "Optional until the permission is approved. The DGAC authorises "
                "three months at most, counted from the start date."
            ),
            "validity_override_reason": _(
                "Only if the DGAC granted a different term. Leave it empty for a "
                "normal three-month permit."
            ),
            # LV-221: dice la unidad **y** el techo, que es el otro dato que
            # alguien necesita al escribir acá. 130 m es el tope de la DAN 151.
            "max_altitude_m": _(
                "In metres, as flown. The DAN 151 ceiling is 130 m AGL. The permit "
                "fiche shows the equivalent in feet for the SIGO form."
            ),
            "area_type": _("DAN 151 (populated) vs. DAN 91 (unpopulated)."),
            "purpose_detail": _("Required when purpose is 'Other'."),
            "region": _(
                "Structured location, in addition to the free-text location "
                "above -- optional."
            ),
            "latitude": _("Decimal degrees. Enter together with longitude."),
            "longitude": _("Decimal degrees. Enter together with latitude."),
        }
        widgets = {
            # A roster of several, not one pick from a dropdown (OPS-4).
            "operators": forms.CheckboxSelectMultiple,
            "aircraft_fleet": forms.CheckboxSelectMultiple,
        }

    # LV-166: los campos de ubicación que un plan geoespacial **provee de
    # verdad**. Salen de `link_to_permission` (`operations/views.py`), que es la
    # única fuente: latitud, longitud, radio, nombre del área, comuna y región.
    #
    # `max_altitude_ft` NO está en la lista y eso es el punto: el KMZ no trae
    # altitud, así que esconderlo lo dejaría sin ninguna forma de cargarse. Y
    # `location` tampoco -- es el texto libre obligatorio, y el usuario no lo
    # pidió. Una lista escrita de memoria en vez de leída de quien rellena es
    # cómo se esconde un campo que nada llena.
    PLAN_PROVIDED_FIELDS = (
        "region",
        "commune",
        "area_name",
        "latitude",
        "longitude",
        "radius_km",
    )

    def __init__(self, *args, user=None, manual_location=False, **kwargs):
        super().__init__(*args, **kwargs)
        # Siempre presentes para que la plantilla no tenga que preguntar si
        # existen: sin plan vinculado quedan vacíos y el formulario es el de
        # antes, campo por campo.
        self.plan_providing_location = None
        self.hidden_plan_fields = []
        if not manual_location:
            self._hide_what_the_plan_provides()
            self._hide_at_creation()
        # LV-153: sólo los planes que no están ya vinculados a otro permiso --
        # reasignar un plan es un movimiento distinto y tiene su propia puerta en
        # la ficha (`R10.2`). Y sólo con `geo.change_geoplan`, porque vincular
        # **modifica el plan**: es el mismo permiso que exige
        # `GeoPlanLinkToPermission`, y ofrecer un selector que después va a
        # fallar es lo que `LV-130` llama enseñar a desconfiar de la pantalla.
        # Sin `user` (tests, shell) no se recorta: la vista es la que decide.
        plans = GeoPlan.objects.filter(is_active=True, flight_permission__isnull=True)
        if user is not None and not user.has_perm("geo.change_geoplan"):
            plans = plans.none()
        self.fields["source_plan"].queryset = plans.select_related(
            "cost_center"
        ).order_by("-folio")
        self.fields["source_plan"].label_from_instance = lambda plan: (
            f"{plan.folio} · {plan.title}"
        )
        # LV-39: the folio is only demanded once approved (see clean); until then
        # the permit can be assembled without it.
        self.fields["permission_number"].required = False
        # R5.5: registration alone doesn't distinguish "which M300" in a
        # roster with several of the same model.
        self.fields["aircraft_fleet"].label_from_instance = lambda obj: (
            obj.selector_label
        )
        # LV-151: el roster se ofrecía **en el orden en que la base devolvía las
        # filas**. Ni `Operator` ni `Aircraft` declaran `Meta.ordering`, así que
        # con 41 operadores el formulario era una grilla sin orden que sólo se
        # puede recorrer a ojo -- el pedido textual fue "tengo problemas a buscar
        # los operadores". Y el queryset por defecto **no filtra `is_active`**:
        # un operador archivado y una aeronave dada de baja seguían ofreciéndose
        # para un permiso nuevo.
        #
        # Lo ya elegido se conserva aunque hoy no calificaría: si una aeronave se
        # retiró después de que el permiso la incluyó, sacarla del queryset la
        # borraría del permiso al guardar cualquier otra edición. Misma
        # normalización blanda que `AircraftForm._make_choice_field` (LV-25).
        # LV-157: el alta ofrece sólo los estados con los que un permiso puede
        # nacer. Ver `FlightPermission.CREATABLE_STATUSES`: aprobar exige la
        # autorización firmada de la DGAC, y en el alta no hay dónde adjuntarla.
        if "status" in self.fields:
            self.fields["status"].choices = [
                (value, label)
                for value, label in FlightPermission.STATUS_CHOICES
                if value in FlightPermission.CREATABLE_STATUSES
            ]
        self.fields["operators"].queryset = self._roster(
            Operator.objects.filter(is_active=True), "operators"
        ).order_by("full_name")
        self.fields["aircraft_fleet"].queryset = self._roster(
            Aircraft.objects.filter(is_active=True).exclude(
                status__in=Aircraft.TERMINAL_STATUSES
            ),
            "aircraft_fleet",
        ).order_by("registration")

    def _hide_what_the_plan_provides(self):
        """Sacar del formulario los datos de ubicación que ya vienen del plan.

        LV-166, pedido del usuario: *"en el permiso de vuelo quitar región,
        comuna, nombre, latitud, longitud, radio, altitud; toda información la
        debe sacar sí o sí al momento de vincular el plan de vuelo, así
        ahorramos espacio y mejoramos el permiso"*.

        **Se esconde un campo sólo si el permiso ya tiene ese valor**, y no por
        estar en una lista. Suena más tímido y es lo contrario: una lista fija
        habría escondido casillas que nada rellena, y hay dos casos reales donde
        eso pasa. Un plan con **varias** circunferencias no rellena coordenadas
        —elegir una sería inventar cuál manda, ver `link_to_permission`— y la
        altitud máxima no está en ningún KMZ. Con la regla atada al valor, esos
        campos siguen a la vista porque siguen haciendo falta.

        En el **alta** nunca actúa: no hay `pk`, y el plan se elige en el mismo
        formulario, así que todavía no hay nada de dónde sacar el dato. Es la
        pantalla de edición la que se limpia, que es donde el usuario los estaba
        viendo de más.

        Lo escondido **no se pierde de vista**: la ficha ya muestra los siete
        datos, y ahora dice de qué plan salieron. Y queda la puerta para el papel
        de la DGAC (`?ubicacion=manual`), que es la razón por la que
        `fill_location_gaps` rellena sin pisar: una resolución puede traer otra
        coordenada, y tiene más autoridad que lo que se preparó antes.
        """
        if not self.instance.pk:
            return
        plan = self.instance.geo_plans.filter(is_active=True).first()
        if plan is None:
            return
        self.plan_providing_location = plan
        for name in self.PLAN_PROVIDED_FIELDS:
            value = getattr(self.instance, name, None)
            if name in self.fields and value not in (None, ""):
                del self.fields[name]
                self.hidden_plan_fields.append(name)

    def _hide_at_creation(self):
        """LV-197: y en el **alta** tampoco se piden.

        Segunda mitad del mismo pedido de `LV-166`, hecha cuando el usuario volvió
        a mirar el formulario de alta: *"quitar esos elementos del permiso […] ya
        que saldrán automáticos […] que el operador no la llene, pero que siempre
        se llene con el geoespacial es clave, así ahorra espacio en la propuesta"*.

        `LV-166` había excluido el alta **a propósito**, y su razón era buena en su
        momento: no hay `pk`, el plan se elige en este mismo formulario, así que al
        dibujarlo todavía no hay nada de dónde sacar el dato. Lo que cambia no es
        esa observación sino la política que se deduce de ella: que el dato no esté
        *todavía* no es razón para pedirlo a mano, porque **hay tres caminos para
        llenarlo y ninguno es tipearlo** — elegir el plan acá mismo (`source_plan`,
        que rellena al guardar), vincularlo después en la ficha (`R10.2`), o
        editar el permiso, que es donde `_hide_what_the_plan_provides` los deja a
        la vista mientras sigan vacíos.

        Esa última es la que hace que esto no cierre ninguna puerta: si el plan no
        trajo la comuna, la pantalla de edición la pide. Y queda además el escape
        explícito de `LV-166`, `?ubicacion=manual`, para el caso que lo motivó — una
        resolución de la DGAC que trae otra coordenada y tiene más autoridad que lo
        que se preparó antes.

        **`max_altitude_ft` y `location` no se tocan**, por lo que `LV-166` ya
        escribió y sigue valiendo: ningún KMZ trae altitud, así que esconderla la
        dejaría sin forma de cargarse, y `location` es el texto libre obligatorio —
        con él, un permiso nunca nace sin decir dónde vuela.

        ⚠️ **`_state.adding` y no `not self.instance.pk`**, que es lo que estaba
        escrito dos métodos más arriba y no comprueba lo que parece: `BaseModel.id`
        es un `UUIDField` con `default=uuid.uuid4`, así que **una instancia nueva
        ya tiene `pk`** antes de guardarse y esa guarda nunca se cumple. Escrita
        así, esta función no habría escondido nada y el test lo dijo de inmediato.
        `_hide_what_the_plan_provides` y `_roster` llevan la misma comprobación y
        siguen siendo correctas **por otra razón** —una instancia sin guardar no
        tiene `geo_plans` ni rosters que traer—, así que no se tocan; queda dicho
        acá para que el próximo no deduzca de ellas que la guarda funciona.
        """
        if not self.instance._state.adding:
            return
        for name in self.PLAN_PROVIDED_FIELDS:
            if name in self.fields:
                del self.fields[name]
                self.hidden_plan_fields.append(name)

    def _roster(self, queryset, field_name):
        """`queryset`, más lo que este permiso ya tiene elegido en ese campo."""
        if not self.instance.pk:
            return queryset
        chosen = getattr(self.instance, field_name).values_list("pk", flat=True)
        return (
            queryset.model.objects.filter(Q(pk__in=queryset) | Q(pk__in=chosen))
        ).distinct()

    def clean(self):
        cleaned = super().clean()
        # LV-153/LV-137: un plan alimenta un permiso **de su misma faena**. Es la
        # regla que `GeoPlanLinkToPermission` ya aplica al vincular; sin ella el
        # alta podría cruzar la geografía de un contrato con otro.
        plan = cleaned.get("source_plan")
        cost_center = cleaned.get("cost_center")
        if plan is not None and cost_center is not None:
            if plan.cost_center_id != cost_center.pk:
                self.add_error(
                    "source_plan",
                    _(
                        "That plan belongs to cost center %(code)s. A plan can "
                        "only fill in a permit of its own cost center."
                    )
                    % {"code": plan.cost_center.code},
                )
        status = cleaned.get("status")
        number = (cleaned.get("permission_number") or "").strip()
        if status == "approved" and not number:
            self.add_error(
                "permission_number",
                _("An approved permission needs its DGAC number."),
            )
        # Store null (not "") so several folio-less permits don't collide on the
        # unique index.
        cleaned["permission_number"] = number or None
        self.instance.permission_number = cleaned["permission_number"]
        # LV-219: espejo de `REQUIRE_VALIDITY_STATUSES`. Mientras el permiso está
        # solicitado la vigencia puede faltar —la DGAC no la ha dado—, pero un
        # permiso aprobado sin vigencia es una autorización sin plazo.
        #
        # El estado se lee de `cleaned_data` **o de la instancia**, y eso no es
        # defensa de más: `FlightPermissionUpdateForm` saca `status` de los
        # campos, así que acá llega vacío al editar. La regla del folio, unas
        # líneas arriba, resolvió lo mismo repitiéndose en la subclase; leer de
        # las dos fuentes evita que un día se edite una copia y no la otra, que es
        # el defecto que `LV-156` encontró en esta misma regla.
        # LV-224: espejo del techo de 3 meses. Se calcula sobre los valores del
        # formulario y no sobre la instancia, porque acá lo que se juzga es lo que
        # la persona acaba de escribir.
        start, end = cleaned.get("valid_from"), cleaned.get("valid_until")
        reason = (cleaned.get("validity_override_reason") or "").strip()
        if start and end and not reason:
            probe = FlightPermission(valid_from=start)
            limit = probe.latest_allowed_valid_until()
            if end > limit:
                self.add_error(
                    "valid_until",
                    _(
                        "The DGAC authorises three months at most, so this window "
                        "cannot end after %(limit)s. If the authorisation really "
                        "says otherwise, write the reason in the field below and "
                        "it will be recorded."
                    )
                    % {"limit": limit.isoformat()},
                )
        effective_status = cleaned.get("status") or self.instance.status
        if effective_status in FlightPermission.REQUIRE_VALIDITY_STATUSES:
            for field in ("valid_from", "valid_until"):
                if cleaned.get(field) is None:
                    self.add_error(
                        field,
                        # Mismo literal que el `clean()` del modelo, a propósito:
                        # dos redacciones para la misma regla son dos entradas de
                        # catálogo que se traducen distinto y se desincronizan.
                        _(
                            "An approved permit needs its validity window: it is "
                            "on the DGAC authorization."
                        ),
                    )
        return cleaned


class FlightPermissionUpdateForm(FlightPermissionForm):
    """LV-101: the same form, minus the status.

    Editing a permit used to offer `status` as a free dropdown, which made the
    edit screen a **back door around every guard the status flow has**: it could
    reach "approved" without the signed DGAC authorization that
    `RequireDgacPermitPdfMixin` demands, walk backwards through the flow, and --
    because `FlightPermissionUpdate` never set `_changed_by` -- write the
    resulting history row attributed to `"system"`. Found in production on
    `JEJ-2026-001`: *"Aprobado desde Completado · system"*.

    Creation keeps the field (LV-39's reason still holds: a permit is assembled
    while it is still "requested"). Changing the status of an existing permit
    now has exactly two doors, both of which record who and why: the guarded
    transitions, and `FlightPermissionCorrectStatus` for genuine corrections.
    """

    class Meta(FlightPermissionForm.Meta):
        fields = [
            field for field in FlightPermissionForm.Meta.fields if field != "status"
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # LV-153: traer los datos de un plan es del **alta**. Un permiso que ya
        # existe tiene su propio selector en la ficha (`R10.2`), que además
        # muestra qué rellenó y escribe la bitácora del vínculo; ofrecerlo también
        # acá serían dos puertas para lo mismo, y una se queda atrás.
        self.fields.pop("source_plan", None)

    def clean(self):
        # The parent rejects an approved permit with no DGAC folio, reading the
        # status from cleaned_data -- absent here, so it comes from the instance
        # instead. Dropping the field must not drop the rule with it.
        cleaned = super().clean()
        cleaned["status"] = self.instance.status
        number = (cleaned.get("permission_number") or "").strip()
        if self.instance.status == "approved" and not number:
            self.add_error(
                "permission_number",
                _("An approved permission needs its DGAC number."),
            )
        return cleaned


class StatusCorrectionForm(forms.Form):
    """LV-101: fixing a status that is simply wrong, on the record.

    Corrections are real -- the defect above was found *because* somebody used
    the edit screen to undo a mistaken "completed". Removing the back door
    without offering a front door would only push the same act into `/admin/`,
    where it would still be unattributed. So the correction exists, but it costs
    a written reason: the same trade `AlertResolveForm` makes for ISO 10.2, and
    the difference between an audit trail that explains itself and one that says
    "system".
    """

    status = forms.ChoiceField(choices=(), label=_("Corrected status"))
    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        label=_("Reason for the correction"),
        help_text=_(
            "Why the recorded status was wrong. It stays in the permit's "
            "history, so write it for whoever reads this a year from now."
        ),
    )

    def __init__(self, *args, current_status=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Every status except the one it already has: "correcting" a permit to
        # the status it is already in is not a correction, and would write a
        # history row saying nothing happened.
        #
        # LV-193: y tampoco los retirados. `LV-155` sacó "Completado" del flujo
        # —*"completado no debe salir luego de aprobado; es caducado y final se
        # archiva"*— y este selector se quedó ofreciéndolo, así que la pantalla
        # que arregla un estado equivocado era la única que podía volver a
        # escribirlo. `RETIRED_STATUSES` vive en el modelo para que el próximo
        # retiro no vuelva a dejar una pantalla atrás.
        self.fields["status"].choices = [
            (value, label)
            for value, label in FlightPermission.STATUS_CHOICES
            if value != current_status
            and value not in FlightPermission.RETIRED_STATUSES
        ]

    def clean_reason(self):
        reason = self.cleaned_data["reason"].strip()
        if not reason:
            raise ValidationError(_("Write why the status is being corrected."))
        return reason


class FlightRecordForm(AeroModelForm):
    class Meta:
        model = FlightRecord
        fields = [
            "permission",
            "actual_date",
            "departure_time",
            "arrival_time",
            "pilot",
            "aircraft",
        ]
        labels = {
            "permission": _("Flight permission"),
            "actual_date": _("Flight date"),
            "departure_time": _("Departure time"),
            "arrival_time": _("Arrival time"),
            "pilot": _("Pilot"),
            "aircraft": _("Aircraft"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # LV-59: the "permission" field had no queryset override, so it fell
        # back to the ModelForm default (every FlightPermission ever created,
        # in raw pk order) -- unusable once there are more than a handful.
        # This is the picker someone actually sees when creating a flight
        # record from the standalone Vuelos list rather than from a specific
        # permission's own "+ Agregar registro" (which prefills it and never
        # shows this dropdown); the T5.5 narrowing below only starts once a
        # permission is already chosen, so it does not help here.
        self.fields["permission"].queryset = FlightPermission.objects.filter(
            is_active=True
        ).order_by("-valid_from")
        # R5.5: registration alone doesn't distinguish "which M300" in a
        # dropdown with several of the same model.
        self.fields["aircraft"].label_from_instance = lambda obj: obj.selector_label
        # T5.5: once a permission is chosen (prefilled from its detail page, or
        # posted back), narrow the pilot and aircraft pickers to that
        # permission's roster instead of the whole registry. The clean() below
        # still enforces it, but this stops the user picking an invalid option
        # in the first place -- the form reduces to what the permission allows.
        permission_id = (
            self.data.get("permission")
            or self.initial.get("permission")
            or getattr(self.instance, "permission_id", None)
        )
        if not permission_id:
            return
        try:
            permission = FlightPermission.objects.prefetch_related(
                "operators", "aircraft_fleet"
            ).get(pk=permission_id)
        except (FlightPermission.DoesNotExist, ValidationError, ValueError, TypeError):
            return
        self.fields["pilot"].queryset = permission.operators.filter(is_active=True)
        self.fields["aircraft"].queryset = permission.aircraft_fleet.filter(
            is_active=True
        )

    def clean(self):
        cleaned = super().clean()
        permission = cleaned.get("permission")
        pilot = cleaned.get("pilot")
        aircraft = cleaned.get("aircraft")
        actual_date = cleaned.get("actual_date")
        departure = cleaned.get("departure_time")
        arrival = cleaned.get("arrival_time")
        # OPS-4: the permission now lists a roster of operators/aircraft over a
        # date range, not a single one of each on a single day, so a flight
        # record is valid whenever it falls within that roster and range --
        # not an exact match against "the" operator/aircraft/date.
        if (
            permission
            and aircraft
            and not permission.aircraft_fleet.filter(pk=aircraft.pk).exists()
        ):
            self.add_error(
                "aircraft",
                _("The aircraft must be part of the flight permission's fleet."),
            )
        if (
            permission
            and pilot
            and not permission.operators.filter(pk=pilot.pk).exists()
        ):
            self.add_error(
                "pilot",
                _("The pilot must be one of the flight permission's operators."),
            )
        # LV-219: **el único sitio que hacía aritmética con las fechas sin que un
        # filtro SQL le quitara los nulos por delante.** El selector de permisos
        # (arriba, línea del `queryset`) ofrece todos los activos sin mirar el
        # estado, así que un permiso todavía solicitado llegaba acá y
        # `None <= actual_date` levantaba un TypeError — un 500 al registrar un
        # vuelo, no un error de formulario.
        #
        # Y no se resuelve dejándolo pasar: si la DGAC no ha dado la vigencia, no
        # hay autorización contra la cual registrar un vuelo. Se rechaza con su
        # propio motivo, que es distinto del de la fecha fuera de rango — decir
        # "la fecha debe caer dentro de la vigencia" cuando no hay vigencia manda
        # a corregir la fecha, que no es el problema.
        if permission and actual_date:
            if permission.valid_from is None or permission.valid_until is None:
                self.add_error(
                    "permission",
                    _(
                        "That permission has no validity window yet, so no flight "
                        "can be recorded against it. It arrives with the DGAC "
                        "authorization."
                    ),
                )
            elif not (permission.valid_from <= actual_date <= permission.valid_until):
                self.add_error(
                    "actual_date",
                    _(
                        "The flight date must fall within the flight permission's validity range."
                    ),
                )
        if departure and arrival and arrival <= departure:
            self.add_error(
                "arrival_time", _("Arrival time must be later than departure time.")
            )
        return cleaned


class FlightRequestForm(AeroModelForm):
    """Los campos de la solicitud que la persona completa a mano.

    Fuera quedan el centro, el radio y la geometría: los pone el motor al
    separar el KMZ y editarlos a mano desincronizaría la solicitud de su
    adjunto — el KMZ diría una cosa y las casillas otra, que es justamente el
    error que este flujo existe para no cometer.

    El AMC sí está: lo **propone** el cálculo y lo confirma la persona contra
    la carta AIP (`LV-93`: la app propone, el papel manda).
    """

    class Meta:
        model = FlightRequest
        fields = [
            "title",
            "request_type",
            "commune",
            "area_name",
            "amc",
            "amc_distance_km",
            "altitude_m",
            "hour_from",
            "hour_to",
            "filed_on",
        ]
        labels = {
            "title": _("Title"),
            "request_type": _("Request type"),
            "commune": _("Commune"),
            "area_name": _("Area"),
            "amc": _("Nearest aerodrome (AMC)"),
            "amc_distance_km": _("Distance to AMC (km)"),
            "altitude_m": _("Height (m)"),
            "hour_from": _("From (time)"),
            "hour_to": _("To (time)"),
            "filed_on": _("Filed in SIGO on"),
        }


class FlightRequestWorkItemForm(AeroModelForm):
    """Un par (Área de Trabajo, Objetivo del Vuelo) — el botón "Agregar" de SIGO."""

    class Meta:
        model = FlightRequestWorkItem
        fields = ["work_area", "objective"]
        # "Objective" y no "Flight objective": el catálogo ya tiene
        # "flight objective" (el `verbose_name` del modelo) y una variante que
        # sólo difiere en mayúsculas es una clave distinta para gettext -- el
        # error que `test_every_translatable_string_is_in_the_catalog` existe
        # para atrapar, y que en su día dejó "Document types" en inglés.
        labels = {
            "work_area": _("Work area"),
            "objective": _("Objective"),
        }


class FlightRequestNoteForm(AeroModelForm):
    """La nota de cambio. Un solo campo: el resto lo pone la vista.

    Sin comparación entre versiones, por decisión del usuario -- lo que queda
    es quién anotó qué y cuándo.
    """

    class Meta:
        model = FlightRequestNote
        fields = ["text"]
        labels = {"text": _("Note")}


class NotamReviewForm(AeroModelForm):
    """LV-218(b): lo que la persona declara haber leído en el IFIS.

    ⚠️ **`outcome` sin valor por omisión y con `empty_label`, a propósito.** Si
    el selector llegara con "no afecta" ya elegido, guardar sin mirar afirmaría
    que ningún aviso afecta al vuelo — que es el fallo silencioso que toda esta
    fila viene evitando desde el paso (a). Hay que elegir.

    El día se propone desde el permiso en la vista, no acá: la fecha por la que
    se revisa es la del vuelo autorizado, y el permiso ya la sabe.
    """

    class Meta:
        model = NotamReview
        fields = ["target_date", "outcome", "findings"]
        labels = {
            "target_date": _("Date reviewed for"),
            "outcome": _("Outcome"),
            "findings": _("What it said"),
        }
        help_texts = {
            "findings": _(
                "Required when a NOTAM affects the operation: say which one and how."
            )
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["outcome"].empty_label = _("Choose what the review found")
