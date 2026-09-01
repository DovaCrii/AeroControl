"""Expiry digest assembly.

Kept out of the management command so Bloque 6 (executive reports) can reuse
the same buckets instead of recomputing them, and so it is testable without
invoking mail.
"""

from datetime import timedelta

from django.utils import timezone

from apps.compliance.models import Document
from apps.registry.models import CostCenter, Operator, Qualification

# Ordered most urgent first; the last bound is the digest horizon.
BUCKETS = [
    ("overdue", None),
    ("due_7", 7),
    ("due_15", 15),
    ("due_30", 30),
]
HORIZON_DAYS = 30

# LV-148: una escala, dos representaciones. El mismo tramo se pintaba distinto en
# dos pantallas —insignia en la bandeja de alertas, texto de color en el panel— y
# no sólo distinto: **discrepaban**, porque `due_30` era azul allá y ámbar acá.
# Las dos tablas viven junto a `bucket_for`, que es el dueño de los cortes, así
# que un tramo nuevo obliga a decidir sus dos colores en el mismo lugar.
#
# `later` es el tramo que el digest no necesita y la bandeja sí: ahí vive también
# el historial, y una alerta resuelta puede apuntar a una vigencia de 2027.
BUCKET_BADGE_CSS = {
    "overdue": "bg-danger",
    "due_7": "bg-warning text-dark",
    "due_15": "bg-warning-subtle text-warning-emphasis",
    "due_30": "bg-info-subtle text-info-emphasis",
    "later": "bg-secondary-subtle text-secondary-emphasis",
}
# En la fila del panel la fecha va como **texto** y no dentro de una píldora: con
# el chip de faena de `LV-146` la fila ya lleva dos pastillas, y una fecha se lee
# mejor suelta. Lo que se unifica es la paleta, no la forma.
BUCKET_TEXT_CSS = {
    "overdue": "text-danger fw-bold",
    "due_7": "text-warning-emphasis fw-bold",
    "due_15": "text-warning-emphasis fw-semibold",
    "due_30": "text-info-emphasis",
    "later": "",
}


# LV-217: el color del **tipo**, que es otra pregunta que la urgencia.
#
# Pedido del usuario con captura: *"a los vencimientos y alertas poner colores
# para diferenciar los tag de qué es cada uno; hoy no tiene y es gris"*. Los cinco
# orígenes de la lista llevaban el mismo `bg-secondary-subtle`, así que había que
# leer el texto de cada píldora para saber de qué hablaba la fila — justo lo que
# una píldora de color existe para evitar.
#
# **Cuatro tonos y no uno por tipo, y es una decisión.** Hay seis orígenes
# (habilitación, credencial DGAC, evaluación, seguro JAC, documento, permiso), y
# seis colores serían seis cosas que memorizar sin que el color diga nada por sí
# mismo. Agrupados por **de qué cuelga el vencimiento**, el color contesta algo
# verdadero de un vistazo —"esto es de una persona", "esto es de una aeronave"— y
# el texto de la píldora sigue precisando cuál. Cuatro categorías se aprenden
# solas; seis colores arbitrarios se consultan.
#
# ⚠️ **Ninguno de los cuatro usa `danger`, `warning` ni `info`**, y eso es lo que
# los hace convivir con la fila: esos tres son la escala de urgencia de `LV-148`
# (arriba), que en el panel se dibuja sobre la fecha. Un tipo y una urgencia
# compitiendo por el mismo canal es cómo se pierde el rojo, que es la única señal
# que tiene que gritar.
#
# ⚠️ **Medido en el navegador, y el resultado corrige la intuición: lo que
# distingue estas píldoras es el color del TEXTO, no el del fondo.**
#
# Los fondos `-subtle` de Bootstrap en tema claro son cuatro blancos casi iguales
# —`rgb(231,239,255)`, `rgb(228,246,234)`, `rgb(236,229,248)`, `rgb(236,239,244)`—
# separados por distancias RGB de **11 a 23**, o sea imperceptibles de un vistazo.
# Quien diseñe esto pensando en "fondos de colores distintos" se equivoca, y es
# fácil equivocarse: fue el primer diseño de esta fila.
#
# La señal está en los `-emphasis`: azul `rgb(27,79,156)`, verde `rgb(31,122,67)`,
# púrpura `rgb(74,44,143)` y gris `rgb(56,66,82)`, con distancias de **60 a 117**
# en tema claro y de **51 a 136** en oscuro. El par más cercano es permiso/aeronave
# (azul contra púrpura), y es el que hay que cuidar si algún día se retoca.
#
# El fondo suave hace de píldora; el texto hace de identidad. **No sustituir el
# texto de énfasis por un gris uniforme "para que se lea mejor": ahí se pierde
# todo lo que esta fila logró.**
#
# Contraste de texto sobre su propio fondo, medido en los dos temas: 6.88 / 4.76 /
# 8.36 / 8.80 en claro y 7.45 / 7.63 / 8.44 / 8.21 en oscuro — los ocho sobre el
# 4.5:1 que pide AA para texto pequeño. El más justo es el verde de `person`.
SUBJECT_TONE_CSS = {
    # El trámite en sí: el permiso de vuelo y su vigencia. Azul, el más
    # distinguible, porque es el objeto central de la app.
    "permit": "bg-primary-subtle text-primary-emphasis",
    # De una persona: su habilitación, su credencial DGAC, su evaluación.
    "person": "bg-success-subtle text-success-emphasis",
    # De una aeronave: el seguro JAC, y el registro DGAC cuando exista.
    #
    # ⚠️ **El único que no es un par de Bootstrap, y por medición.** Empezó siendo
    # `bg-dark-subtle`, y medido en el navegador resultó ser `rgb(233,235,238)`
    # contra el `rgb(236,239,244)` de `document`: dos grises separados por tres
    # puntos de canal, o sea el mismo gris a la vista. Dos de los cuatro tipos no
    # se distinguían — exactamente lo que esta fila vino a arreglar.
    #
    # Bootstrap ofrece ocho familias y tres están reservadas a la urgencia
    # (`danger`, `warning`, `info`), así que sólo quedan **dos** cromáticas
    # (`primary`, `success`) y tres grises. Con cuatro tipos que conviven en la
    # misma lista hacía falta un tercer color, y se define en `app.css` como
    # `.badge-kind-aircraft` con su variante de tema oscuro.
    "aircraft": "badge-kind-aircraft",
    # Un documento del expediente. Se queda con el gris que tenían todos: es el
    # origen más genérico y el que menos gana con un color propio.
    "document": "bg-secondary-subtle text-secondary-emphasis",
}


# LV-217, segunda mitad: lo mismo en la bandeja de alertas, pedido del usuario en
# un segundo mensaje: *"lo mismo en alerta, el tipo de entidad"*.
#
# Va por `"app_label.model"` y no por la clase, porque acá el modelo llega desde
# el `content_type` de la alerta y las reglas las configura el usuario
# (`AlertRule.entity_type` es texto).
#
# ⚠️ **Y por eso este mapeo lleva fallback y el del panel no.** Las fuentes del
# panel están codificadas: una fuente nueva sin color es un olvido del
# programador, y conviene que levante. Acá, en cambio, cualquiera puede crear una
# regla sobre un modelo que esta tabla no conozca, y una bandeja que revienta por
# un color es peor que una píldora gris. La asimetría es deliberada.
ENTITY_TONES = {
    "operations.flightpermission": "permit",
    "registry.qualification": "person",
    "registry.operator": "person",
    "registry.knowledgeassessment": "person",
    "registry.aircraft": "aircraft",
    # La mantención cuelga de una aeronave, así que comparte su tono: para quien
    # mira la bandeja, las dos filas hablan del mismo equipo.
    "maintenance.maintenancerecord": "aircraft",
    "compliance.document": "document",
    "compliance.monthlycompliancereview": "document",
}


def bucket_for(expiry, today):
    """Return the urgency bucket key for an expiry date."""
    if expiry < today:
        return "overdue"
    days_left = (expiry - today).days
    if days_left <= 7:
        return "due_7"
    if days_left <= 15:
        return "due_15"
    if days_left <= HORIZON_DAYS:
        return "due_30"
    return None


def _documents_for(cost_center, cutoff):
    """Expiring current documents attached to this cost center."""
    from apps.compliance.reports import documents_for_cost_center

    return documents_for_cost_center(
        cost_center,
        Document.objects.filter(
            is_active=True,
            is_current_version=True,
            expiry_date__isnull=False,
            expiry_date__lte=cutoff,
        ).select_related("doc_type"),
    ).order_by("expiry_date")


def build_digest(cost_center, today=None):
    """Return {bucket: [item, ...]} of expiring items for a cost center.

    Items are dicts with kind/label/detail/expiry_date/url_path so the email
    templates stay free of model knowledge.
    """
    today = today or timezone.localdate()
    cutoff = today + timedelta(days=HORIZON_DAYS)
    operator_ids = list(
        Operator.objects.filter(cost_center=cost_center, is_active=True).values_list(
            "pk", flat=True
        )
    )

    buckets = {key: [] for key, _bound in BUCKETS}

    qualifications = (
        Qualification.objects.filter(
            operator_id__in=operator_ids,
            is_active=True,
            expiry_date__isnull=False,
            expiry_date__lte=cutoff,
        )
        .select_related("operator", "qualification_type")
        .order_by("expiry_date")
    )
    for qualification in qualifications:
        key = bucket_for(qualification.expiry_date, today)
        if key:
            buckets[key].append(
                {
                    "kind": "qualification",
                    "label": qualification.qualification_type.name,
                    "detail": str(qualification.operator),
                    "expiry_date": qualification.expiry_date,
                    "url_path": f"/registry/qualification/{qualification.pk}/",
                }
            )

    for document in _documents_for(cost_center, cutoff):
        key = bucket_for(document.expiry_date, today)
        if key:
            buckets[key].append(
                {
                    "kind": "document",
                    "label": document.title,
                    "detail": str(document.doc_type),
                    "expiry_date": document.expiry_date,
                    "url_path": f"/compliance/document/{document.pk}/",
                }
            )

    for items in buckets.values():
        items.sort(key=lambda item: item["expiry_date"])
    return buckets


def digest_item_count(buckets):
    return sum(len(items) for items in buckets.values())


def cost_centers_to_notify():
    """Active cost centers, most specific first, for the digest run."""
    return (
        CostCenter.objects.filter(is_active=True)
        .select_related("responsible_operator")
        .order_by("code")
    )


def archived_centers_with_active_dependents():
    """Archived cost centers whose operators or aircraft are still active.

    Archiving a center drops it from the digest and the report silently -- the
    exact compliance blind spot the digest exists to prevent. The command
    reports these instead of staying quiet. Returns (center, operators,
    aircraft) tuples.
    """
    from django.db.models import Count, Q

    centers = (
        CostCenter.objects.filter(is_active=False)
        .annotate(
            active_operators=Count(
                "operators", filter=Q(operators__is_active=True), distinct=True
            ),
            active_aircraft=Count(
                "aircraft", filter=Q(aircraft__is_active=True), distinct=True
            ),
        )
        .filter(Q(active_operators__gt=0) | Q(active_aircraft__gt=0))
        .order_by("code")
    )
    return [
        (center, center.active_operators, center.active_aircraft) for center in centers
    ]
