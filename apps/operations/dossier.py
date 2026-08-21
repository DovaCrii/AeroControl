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
"""

from dataclasses import dataclass, field

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

    @property
    def is_ok(self):
        return self.status == OK


def _aircraft_insurance_item(permission):
    overdue, unknown = [], []
    for aircraft in permission.aircraft_fleet.all():
        if aircraft.insurance_expiry is None:
            unknown.append(str(aircraft.registration))
        elif aircraft.insurance_is_overdue:
            overdue.append(str(aircraft.registration))
    label = _("Insurance in force for every aircraft")
    if overdue:
        return DossierItem("insurance", label, MISSING, _("Lapsed insurance"), overdue)
    if unknown:
        return DossierItem("insurance", label, UNKNOWN, _("No expiry on file"), unknown)
    return DossierItem("insurance", label, OK)


def _operator_credential_item(permission):
    overdue, unknown = [], []
    for operator in permission.operators.all():
        if operator.credential_expiry is None:
            unknown.append(str(operator.full_name))
        elif operator.credential_is_overdue:
            overdue.append(str(operator.full_name))
    label = _("DGAC credential in force for every operator")
    if overdue:
        return DossierItem(
            "credential", label, MISSING, _("Lapsed credential"), overdue
        )
    if unknown:
        return DossierItem(
            "credential", label, UNKNOWN, _("No expiry on file"), unknown
        )
    return DossierItem("credential", label, OK)


def _document_items(permission):
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
    return [
        DossierItem(
            "signed_authorization",
            _("Signed DGAC authorization on file"),
            OK if SIGNED_AUTHORIZATION in codes else MISSING,
            "" if SIGNED_AUTHORIZATION in codes else _("The folio'd SIGO PDF"),
        ),
        DossierItem(
            "permit_letter",
            _("Permit letter on file"),
            OK if PERMIT_LETTER in codes else UNKNOWN,
            "" if PERMIT_LETTER in codes else _("Not on file"),
        ),
    ]


def _geo_plan_items(permission):
    """El plan y su revisión meteorológica.

    La revisión existe como evidencia desde `R8.2` y se escribe **por una acción
    explícita**: que alguien abriera la pestaña no acredita que nadie revisó
    nada. Acá sólo se lee si esa acción ocurrió.
    """
    plans = list(permission.geo_plans.all())
    if not plans:
        return [
            DossierItem(
                "geo_plan",
                _("Geospatial plan linked"),
                UNKNOWN,
                _("No plan linked to this permit"),
            )
        ]
    reviewed = [plan for plan in plans if plan.weather_reviews.exists()]
    without = [str(plan.title) for plan in plans if plan not in reviewed]
    return [
        DossierItem("geo_plan", _("Geospatial plan linked"), OK),
        DossierItem(
            "weather",
            _("Weather reviewed and on record"),
            OK if not without else UNKNOWN,
            "" if not without else _("No review on record"),
            without,
        ),
    ]


def _flight_record_item(permission):
    """Un permiso **completado** sin un solo vuelo registrado es la contradicción
    que esta pantalla existe para mostrar: se declaró que se voló lo autorizado y
    no hay bitácora que lo respalde. Antes de completarse, en cambio, no tener
    vuelos es lo normal, así que no es un faltante sino un dato.
    """
    count = permission.records.filter(is_active=True).count()
    label = _("Flights logged against this permit")
    if count:
        return DossierItem("flights", label, OK, detail=str(count))
    if permission.status == "completed":
        return DossierItem(
            "flights", label, MISSING, _("Completed with no flights logged")
        )
    return DossierItem("flights", label, UNKNOWN, _("None logged yet"))


def _flight_request_item(permission):
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
        return DossierItem(
            "flight_request", label, UNKNOWN, _("No request recorded for this permit")
        )
    return DossierItem(
        "flight_request",
        label,
        OK,
        detail=", ".join(str(request.title) for request in requests),
    )


def operational_dossier(permission):
    """Los renglones del expediente, en el orden en que se revisa una operación."""
    items = [
        *_document_items(permission),
        _aircraft_insurance_item(permission),
        _operator_credential_item(permission),
        *_geo_plan_items(permission),
        _flight_request_item(permission),
        _flight_record_item(permission),
    ]
    return {
        "items": items,
        # Contado acá y no en la plantilla: "cuántas cosas faltan" es la única
        # cifra que la persona mira antes de leer el detalle.
        "missing_count": sum(1 for item in items if item.status == MISSING),
        "unknown_count": sum(1 for item in items if item.status == UNKNOWN),
        "is_complete": all(item.is_ok for item in items),
    }
