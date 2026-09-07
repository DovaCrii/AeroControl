"""UX-13: la bandeja de trabajo — todo lo pendiente en una sola lista.

Del plan: *"vista unificada sobre alertas, no conformidades, mantención por
definir, permisos esperando respuesta y entregables sin liberar, con **dueño,
severidad y acción en la fila**"*.

⚠️ **El criterio manda sobre el diseño, y es una restricción, no un adorno:**
*"resolver desde la bandeja produce exactamente la misma evidencia ISO 10.2 que
resolver desde la lista de alertas — es la misma vista, no un segundo camino"*.

Por eso **este módulo no resuelve nada**. Cada fila trae la URL de la acción que
ya existe —el modal de resolver, la ficha de la no conformidad, la del permiso—
y la bandeja se limita a juntarlas. Un segundo camino para resolver sería un
segundo lugar donde registrar (o no registrar) la causa raíz, y ahí es donde la
evidencia ISO 10.2 se pierde: no de golpe, sino en la mitad de los casos.

**Cada fuente se lee sólo si quien mira puede verla.** No es cosmético: la
bandeja cruza cuatro aplicaciones, y sin esto le mostraría a un rol el nombre de
faenas, aeronaves y personas que sus permisos le niegan en la pantalla propia de
cada módulo. Es la lección de `LV-191`, donde un panel llevaba meses listando
credenciales por vencer porque lo que lo tapaba no era un control de acceso.
"""

from django.urls import reverse

# Las cuatro fuentes que tienen una definición de "pendiente" que se sostiene.
#
# ⚠️ **Mantención queda fuera a propósito, y el plan lo dice**: su fila la lista
# como *"mantención por definir"*. `MaintenanceRecord` tiene `status`, pero sin
# `STATUS_CHOICES` declarado — no hay un vocabulario del que leer qué estado es
# "pendiente", y elegir uno acá sería inventarlo en la pantalla en vez de en el
# modelo, que es exactamente el defecto que `LV-90` sacó del motor de alertas.
# Cuando ese modelo declare sus estados, entra sin tocar nada más.
SOURCE_ALERT = "alert"
SOURCE_NONCONFORMITY = "nonconformity"
SOURCE_PERMIT = "permit"
SOURCE_DELIVERABLE = "deliverable"


def _row(*, source, label, title, subject, cost_centre, severity, owner, due, url):
    """Una fila de la bandeja.

    `severity` vacío **no es "sin urgencia"**: es "este dominio no calcula una".
    Sólo las alertas tienen una escala de urgencia real (`urgency_level`, los
    mismos cortes que el digest diario) y sólo las no conformidades tienen un
    plazo de verificación vencido. Inventarle un color a un entregable sin
    liberar sería pintar una prioridad que nadie definió, y con ella enseñar a
    ignorar el color — el daño que `LV-118` documentó en la bandeja de alertas.
    """
    return {
        "source": source,
        "label": label,
        "title": title,
        "subject": subject,
        "cost_centre": cost_centre,
        "severity": severity,
        "owner": owner,
        "due": due,
        "url": url,
    }


def _alerts(user):
    from django.utils.translation import gettext as _

    from apps.compliance.models import Alert
    from apps.compliance.reports import cost_centers_for_refs

    alerts = list(
        Alert.objects.filter(is_active=True, is_resolved=False)
        .select_related("alert_rule", "assigned_to")
        # Por `triggered_at` y no por `triggering_date`: esa segunda es una
        # **propiedad** que lee el valor congelado (`watched_value`, `LV-118`),
        # así que la base no puede ordenar por ella. La bandeja reordena después
        # por fecha en Python, sobre todas las fuentes juntas, que es donde ese
        # orden importa.
        .order_by("triggered_at")
    )
    # La faena de una alerta **no es un campo**: cuelga de una relación genérica
    # y se resuelve con el mismo mapa que usan el filtro y la bandeja de alertas.
    # En bloque y no por fila: una consulta por modelo presente en vez de una por
    # alerta, que es el N+1 que `LV-106` sacó de esa pantalla.
    centres = cost_centers_for_refs(
        [(alert.content_type_id, alert.object_id) for alert in alerts]
    )

    rows = []
    for alert in alerts:
        rows.append(
            _row(
                source=SOURCE_ALERT,
                label=_("alert"),
                title=alert.alert_rule.name,
                subject=str(alert.content_object or _("Record unavailable")),
                cost_centre=centres.get((alert.content_type_id, alert.object_id)),
                # La única escala de urgencia real del conjunto, y la misma que
                # la píldora de la bandeja de alertas: dos escalas para el mismo
                # hecho es cómo dos pantallas empiezan a discrepar.
                severity=alert.urgency_level,
                owner=alert.assigned_to,
                due=alert.triggering_date,
                url=reverse("alert-list"),
            )
        )
    return rows


def _nonconformities(user):
    from django.utils.translation import gettext as _

    from apps.compliance.models import NonConformity

    rows = []
    for finding in (
        NonConformity.objects.filter(is_active=True, status="open")
        .select_related("cost_center", "assigned_to")
        .order_by("detected_on")
    ):
        rows.append(
            _row(
                source=SOURCE_NONCONFORMITY,
                label=_("non-conformity"),
                title=finding.title,
                subject=finding.get_source_display(),
                cost_centre=finding.cost_center,
                # Sólo cuando la verificación de eficacia ya venció: ahí sí hay
                # un hecho que urge, y es el que `R7.6a` escala a Dirección.
                severity="warning" if finding.effectiveness_is_due else "",
                owner=finding.assigned_to,
                due=finding.detected_on,
                url=finding.get_absolute_url(),
            )
        )
    return rows


def _permits(user):
    from django.utils.translation import gettext as _

    from apps.operations.models import FlightPermission

    rows = []
    for permit in (
        FlightPermission.objects.filter(
            is_active=True, status=FlightPermission.STATUS_REQUESTED
        )
        .select_related("cost_center")
        .order_by("created_at")
    ):
        rows.append(
            _row(
                source=SOURCE_PERMIT,
                label=_("permit awaiting the DGAC"),
                title=permit.internal_folio or str(permit),
                subject=permit.location,
                cost_centre=permit.cost_center,
                # Esperar a la autoridad no es un incumplimiento de nadie, así
                # que no lleva color. `LV-129` ya separó "espera a la DGAC" de
                # "es trabajo pendiente" por esta misma razón.
                severity="",
                owner=None,
                due=None,
                url=permit.get_absolute_url(),
            )
        )
    return rows


def _deliverables(user):
    from django.utils.translation import gettext as _

    from apps.compliance.models import Deliverable

    rows = []
    for deliverable in (
        Deliverable.objects.filter(is_active=True, status__in=("draft", "validated"))
        .select_related("cost_center")
        .order_by("created_at")
    ):
        rows.append(
            _row(
                source=SOURCE_DELIVERABLE,
                label=_("deliverable not released"),
                title=deliverable.title,
                subject=deliverable.get_status_display(),
                cost_centre=deliverable.cost_center,
                severity="",
                owner=None,
                due=None,
                url=deliverable.get_absolute_url(),
            )
        )
    return rows


# (permiso que hace falta, función que lee esa fuente). El permiso es el de
# **ver** el modelo, no el de resolverlo: la bandeja muestra, y la acción de cada
# fila lleva a la pantalla que ya comprueba lo suyo.
SOURCES = (
    ("compliance.view_alert", _alerts),
    ("compliance.view_nonconformity", _nonconformities),
    ("operations.view_flightpermission", _permits),
    ("compliance.view_deliverable", _deliverables),
)


def pending_for(user):
    """Todo lo pendiente que `user` puede ver, en una sola lista.

    Ordenado por **lo que tiene fecha y está más cerca primero**, y lo que no
    tiene fecha después: un permiso esperando a la DGAC no compite con una
    credencial que vence el martes. Dentro de cada grupo, por origen y título,
    para que la lista no baile entre cargas.
    """
    rows = []
    for permission, read in SOURCES:
        if user.has_perm(permission):
            rows.extend(read(user))
    return sorted(
        rows,
        key=lambda row: (
            row["due"] is None,
            row["due"] or "",
            row["source"],
            row["title"],
        ),
    )
