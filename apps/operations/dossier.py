"""LV-107: el expediente operativo de un permiso.

Responde una sola pregunta —**"¿esta operación está completa y documentada?"**—
sin obligar a saltar entre la ficha del permiso, la de cada aeronave, la de cada
operador, el plan geoespacial y el repositorio de documentos. Es la pregunta que
hace un inspector, y hasta ahora se contestaba abriendo cinco pantallas y
acordándose de todas.

**Cero datos nuevos.** Es la misma composición que el panel (`LV-89`) hace para
la flota, aplicada a una operación: cada renglón lee campos que ya existen.

Tres decisiones que dan forma a todo lo demás:

1. **Un faltante se nombra.** "Faltan vigencias" no dice qué hacer; "RPA-5532 sin
   seguro vigente" sí. Cada renglón que no está en verde dice **cuál** es el
   registro y **por qué**.
2. **Sin dato no es lo mismo que vencido.** `LV-29` decidió que un nulo significa
   "nunca se ingresó" y por eso no genera alerta; pintar ese hueco de verde sería
   mentir, y de rojo también. Va en ámbar, con su propio texto: es trabajo
   pendiente, no un incumplimiento.
3. **Esto no bloquea nada.** Es una lectura, no una compuerta: las compuertas
   reales (el PDF firmado de la DGAC para aprobar o completar) viven en
   `RequireDgacPermitPdfMixin`, donde tienen efecto. Un expediente que además
   prohibiera cosas duplicaría esa regla en un segundo lugar del que después se
   desincroniza.

`LV-130` agrega la cuarta, que es la que convierte esto en trabajo:

4. **Cada renglón que falta lleva el atajo que lo cierra.** Textual del usuario:
   *"en el expediente de cada uno […] buscar un workflow mejor o cómo para ir
   cubriendo y confirmando lo faltante para que esté completo"*. La pantalla
   respondía "faltan cuatro cosas" y ahí terminaba: cerrar cada una exigía saber
   **dónde** se cierra —la ficha de la aeronave para una vigencia, la del plan
   para la revisión meteorológica, el formulario de carga con el tipo correcto
   para un PDF— que es el conocimiento que esta pantalla existía para no exigir.
   El destino es siempre **una pantalla que ya existía**: el expediente no gana
   formularios propios, gana enlaces con lo que se puede prellenar ya puesto.

   Y el atajo **respeta los permisos**: `operational_dossier(permission, user)`
   omite la acción que ese usuario no podría ejecutar. Ofrecer un botón que
   termina en 403 es peor que no ofrecerlo — enseña a desconfiar de la pantalla.
   Sin `user` no se filtra nada, que es lo que necesitan los tests del renglón.
"""

from dataclasses import dataclass, field
from urllib.parse import urlencode

from django.urls import reverse
from django.utils.translation import gettext_lazy as _

# Los tres estados que puede tener un renglón. `UNKNOWN` existe por la decisión
# 2 de arriba y es la mitad del valor de esta pantalla.
OK = "ok"
MISSING = "missing"
UNKNOWN = "unknown"

# Los dos documentos DGAC del expediente, por `code` (identidad estable del
# catálogo, la misma sobre la que `seed_document_types` es idempotente).
SIGNED_AUTHORIZATION = "dgac-rpa-operation-authorization"
PERMIT_LETTER = "dgac-flight-permit"


@dataclass
class DossierItem:
    """Un renglón del expediente: qué se revisó, cómo salió y qué falta.

    `key` es la identidad del renglón para el código; `label` es para la
    persona. Están separados porque la etiqueta **se traduce**: cualquier cosa
    —un test, una regla de estilo— que identifique un renglón por su texto pasa
    o falla según el idioma activo, que es una forma de fragilidad que este
    proyecto ya pagó al agrupar el selector de tipos de documento (`LV-95`).
    """

    key: str
    label: str
    status: str
    detail: str = ""
    # Los registros concretos que fallan, para nombrarlos en vez de contarlos.
    offenders: list = field(default_factory=list)
    # LV-130: dónde se cierra este renglón. Vacíos cuando está en verde, cuando
    # el usuario no tiene el permiso, o cuando no hay una sola pantalla que lo
    # resuelva (un permiso "completado" sin vuelos ya ocurrió: lo que falta ahí
    # es una decisión, no un formulario).
    action_label: str = ""
    action_url: str = ""

    @property
    def is_ok(self):
        return self.status == OK


def _allowed(user, codename):
    """Sin usuario no se filtra; con usuario, manda su permiso."""
    return user is None or user.has_perm(codename)


def _open_record_action(records, *, user, codename, detail_url, list_url, one, many):
    """LV-130: la ficha del registro que falla, o su listado si son varios.

    Con **uno** se va derecho al lugar donde se carga el dato. Con varios no:
    llevar al primero de tres escondería los otros dos detrás de un botón que
    parece haber resuelto el renglón, y el listado los muestra a todos.
    """
    if not records or not _allowed(user, codename):
        return "", ""
    if len(records) == 1:
        return one, reverse(detail_url, args=[records[0].pk])
    return many, reverse(list_url)


def _aircraft_insurance_item(permission, user=None):
    overdue, unknown, offending = [], [], []
    for aircraft in permission.aircraft_fleet.all():
        if aircraft.insurance_expiry is None:
            unknown.append(str(aircraft.registration))
            offending.append(aircraft)
        elif aircraft.insurance_is_overdue:
            overdue.append(str(aircraft.registration))
            offending.append(aircraft)
    label = _("Insurance in force for every aircraft")
    action = _open_record_action(
        offending,
        user=user,
        codename="registry.change_aircraft",
        detail_url="aircraft-detail",
        list_url="aircraft-list",
        one=_("Open the aircraft"),
        many=_("Open the fleet"),
    )
    if overdue:
        return DossierItem(
            "insurance", label, MISSING, _("Lapsed insurance"), overdue, *action
        )
    if unknown:
        return DossierItem(
            "insurance", label, UNKNOWN, _("No expiry on file"), unknown, *action
        )
    return DossierItem("insurance", label, OK)


def _operator_credential_item(permission, user=None):
    overdue, unknown, offending = [], [], []
    for operator in permission.operators.all():
        if operator.credential_expiry is None:
            unknown.append(str(operator.full_name))
            offending.append(operator)
        elif operator.credential_is_overdue:
            overdue.append(str(operator.full_name))
            offending.append(operator)
    label = _("DGAC credential in force for every operator")
    action = _open_record_action(
        offending,
        user=user,
        codename="registry.change_operator",
        detail_url="operator-detail",
        list_url="operator-list",
        one=_("Open the operator"),
        many=_("Open the roster"),
    )
    if overdue:
        return DossierItem(
            "credential", label, MISSING, _("Lapsed credential"), overdue, *action
        )
    if unknown:
        return DossierItem(
            "credential", label, UNKNOWN, _("No expiry on file"), unknown, *action
        )
    return DossierItem("credential", label, OK)


def _upload_action(permission, code, user):
    """LV-130: el formulario de carga con el tipo de documento ya elegido.

    `DocumentCreate` prellena desde `entity_type`, `object_id` y `doc_type` en la
    URL (OPS-5, LV-30), así que el atajo no agrega una vista: agrega los tres
    datos que la persona tendría que elegir a mano sabiendo cuál es el correcto
    —y "cuál es el correcto" es justo lo que `LV-64` demostró que se confunde.

    Si el tipo no está en el catálogo el enlace va igual, sin prellenarlo: dejar
    a alguien sin forma de subir el papel porque falta una fila de catálogo sería
    peor que ofrecerle el formulario en blanco.
    """
    if not _allowed(user, "compliance.add_document"):
        return "", ""
    from django.contrib.contenttypes.models import ContentType

    from apps.compliance.models import DocumentType

    params = {
        "entity_type": ContentType.objects.get_for_model(permission.__class__).pk,
        "object_id": str(permission.pk),
    }
    doc_type_pk = (
        DocumentType.objects.filter(code=code).values_list("pk", flat=True).first()
    )
    if doc_type_pk:
        params["doc_type"] = doc_type_pk
    return _("Upload it"), f"{reverse('document-create')}?{urlencode(params)}"


def _document_items(permission, user=None):
    """Los dos papeles DGAC, que son documentos distintos y no intercambiables.

    `LV-64`: la carta es lo que va **hacia** la DGAC como parte de la solicitud;
    la autorización firmada es lo que **vuelve**, con folio, cuando la DGAC
    aprueba de verdad. Sólo la segunda certifica la aprobación, y por eso es la
    que la compuerta de `R2.4` exige.
    """
    from django.contrib.contenttypes.models import ContentType

    from apps.compliance.models import Document

    codes = set(
        Document.objects.filter(
            content_type=ContentType.objects.get_for_model(permission.__class__),
            object_id=permission.pk,
            is_current_version=True,
            is_active=True,
        ).values_list("doc_type__code", flat=True)
    )
    items = []
    for key, label, code, missing_status, missing_detail in (
        (
            "signed_authorization",
            _("Signed DGAC authorization on file"),
            SIGNED_AUTHORIZATION,
            MISSING,
            _("The folio'd SIGO PDF"),
        ),
        (
            "permit_letter",
            _("Permit letter on file"),
            PERMIT_LETTER,
            UNKNOWN,
            _("Not on file"),
        ),
    ):
        if code in codes:
            items.append(DossierItem(key, label, OK))
            continue
        items.append(
            DossierItem(
                key,
                label,
                missing_status,
                missing_detail,
                [],
                *_upload_action(permission, code, user),
            )
        )
    return items


def _geo_plan_items(permission, user=None):
    """El plan y su revisión meteorológica.

    La revisión existe como evidencia desde `R8.2` y se escribe **por una acción
    explícita**: que alguien abriera la pestaña no acredita que nadie revisó
    nada. Acá sólo se lee si esa acción ocurrió.
    """
    plans = list(permission.geo_plans.all())
    if not plans:
        # **LV-137: primero vincular, y sólo importar si no hay nada que
        # vincular.** El atajo ofrecía importar, y eso estaba mal en lo que más
        # importa: importar crea un plan nuevo desde un KMZ, mientras que el plan
        # que hace falta **ya existe en la app** y al vincularlo *rellena la
        # ubicación del permiso* — centro, radio, área y, desde esta fila, el
        # aeródromo más cercano con su distancia. Textual del usuario: *"el plan
        # geoespacial no se debe importar, se debe llamar desde el geoespacial que
        # se crea dentro de la app, y ese tiene además la información faltante
        # para llenar el permiso"*.
        #
        # El destino es el selector de R10.2, que vive en esta misma ficha: un
        # ancla y no una pantalla nueva, porque vincular es un `<select>` con los
        # planes de este centro de costo y ya está dibujado unos centímetros más
        # abajo.
        from apps.geo.models import GeoPlan

        linkable = GeoPlan.objects.filter(
            cost_center=permission.cost_center,
            flight_permission__isnull=True,
            is_active=True,
        ).exists()
        action = ("", "")
        if linkable and _allowed(user, "geo.change_geoplan"):
            action = (_("Link a plan"), "#tab-geo-plans")
        elif _allowed(user, "geo.add_geoplan"):
            # Sin planes sueltos en esta faena, importar es lo único que queda —
            # y ahí sí es la acción correcta, no un atajo equivocado.
            action = (
                _("Import a plan"),
                f"{reverse('geo-plan-import')}?flight_permission={permission.pk}",
            )
        return [
            DossierItem(
                "geo_plan",
                _("Geospatial plan linked"),
                UNKNOWN,
                _("No plan linked to this permit"),
                [],
                *action,
            )
        ]
    reviewed = [plan for plan in plans if plan.weather_reviews.exists()]
    pending = [plan for plan in plans if plan not in reviewed]
    without = [str(plan.title) for plan in pending]
    # La revisión se registra **con un botón que vive en la ficha del plan**
    # (R8.1), así que el atajo lleva ahí y no a una acción propia: duplicar el
    # registro de evidencia en dos lugares es cómo se termina con dos versiones
    # de "quién revisó qué".
    weather_action = _open_record_action(
        pending,
        user=user,
        codename="geo.view_geoplan",
        detail_url="geo-plan-detail",
        list_url="geo-plan-list",
        one=_("Open the plan"),
        many=_("Open the plans"),
    )
    return [
        DossierItem("geo_plan", _("Geospatial plan linked"), OK),
        DossierItem(
            "weather",
            _("Weather reviewed and on record"),
            OK if not without else UNKNOWN,
            "" if not without else _("No review on record"),
            without,
            *weather_action,
        ),
    ]


def _flight_record_item(permission, user=None):
    """Un permiso **completado** sin un solo vuelo registrado es la contradicción
    que esta pantalla existe para mostrar: se declaró que se voló lo autorizado y
    no hay bitácora que lo respalde. Antes de completarse, en cambio, no tener
    vuelos es lo normal, así que no es un faltante sino un dato.
    """
    count = permission.records.filter(is_active=True).count()
    label = _("Flights logged against this permit")
    if count:
        return DossierItem("flights", label, OK, detail=str(count))
    action = ("", "")
    if _allowed(user, "operations.add_flightrecord"):
        # `FlightRecordCreate` prellena el permiso desde la URL, así que el
        # atajo llega al formulario con la mitad del contexto ya puesta.
        action = (
            _("Log a flight"),
            f"{reverse('record-create')}?permission={permission.pk}",
        )
    if permission.status == "completed":
        return DossierItem(
            "flights",
            label,
            MISSING,
            _("Completed with no flights logged"),
            [],
            *action,
        )
    return DossierItem("flights", label, UNKNOWN, _("None logged yet"), [], *action)


def _flight_request_item(permission, user=None):
    """R9.6: de qué solicitud SIGO salió este permiso.

    Cierra el círculo del expediente: hasta acá se podía ver el plan que dibujó
    el área y el papel que la DGAC devolvió, pero no **lo que efectivamente se
    pidió** — y esa es la pregunta que separa "la DGAC autorizó esto" de "la
    DGAC autorizó lo que pedimos". Con la solicitud al lado, las coordenadas
    presentadas y las del permiso se pueden comparar de un vistazo.

    `UNKNOWN` y no `MISSING` cuando no hay ninguna, deliberadamente: los
    permisos anteriores a R9 —todos los que existen hoy— se tramitaron sin que
    la app registrara la solicitud, y marcarlos como incompletos los declararía
    defectuosos de forma retroactiva por una función que no existía. Mismo
    criterio que `LV-107` aplicó al plan geoespacial.
    """
    requests = list(permission.flight_requests.filter(is_active=True))
    label = _("Originating SIGO request")
    if not requests:
        # El vínculo se hace **desde la solicitud** (`FlightRequestLink`), porque
        # es ahí donde están las coordenadas presentadas que hay que comparar
        # antes de afirmar que este permiso responde a esa solicitud. El atajo
        # lleva al listado, no vincula: vincular sin mirar es el error que ese
        # formulario evita.
        action = ("", "")
        if _allowed(user, "operations.view_flightrequest"):
            action = (_("See the requests"), reverse("flight-request-list"))
        return DossierItem(
            "flight_request",
            label,
            UNKNOWN,
            _("No request recorded for this permit"),
            [],
            *action,
        )
    return DossierItem(
        "flight_request",
        label,
        OK,
        detail=", ".join(str(request.title) for request in requests),
    )


def operational_dossier(permission, user=None):
    """Los renglones del expediente, en el orden en que se revisa una operación.

    `user` es opcional: con él, cada renglón trae sólo el atajo que esa persona
    puede ejecutar (`LV-130`); sin él, trae todos. Se deja opcional para que los
    tests del renglón —que afirman estado y detalle, no permisos— no tengan que
    montar un usuario para nada.
    """
    items = [
        *_document_items(permission, user),
        _aircraft_insurance_item(permission, user),
        _operator_credential_item(permission, user),
        *_geo_plan_items(permission, user),
        _flight_request_item(permission, user),
        _flight_record_item(permission, user),
    ]
    return {
        "items": items,
        # Contado acá y no en la plantilla: "cuántas cosas faltan" es la única
        # cifra que la persona mira antes de leer el detalle.
        "missing_count": sum(1 for item in items if item.status == MISSING),
        "unknown_count": sum(1 for item in items if item.status == UNKNOWN),
        "is_complete": all(item.is_ok for item in items),
    }
