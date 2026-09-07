"""`UX-27` · «¿Puedo volar?», la pantalla del operador en faena.

Una sola respuesta —**sí** o **no**— para una terna concreta: esta aeronave, con
esta persona, en esta faena, hoy. Y si es que no, el motivo, con el enlace a
resolverlo.

**Por qué existe teniendo panel, bandeja y alertas.** Las tres contestan
*"¿cuánto trabajo hay?"*, que es la pregunta de quien coordina. La de quien está
parado junto al equipo con la caja abierta es otra, y hasta ahora había que
armarla a mano: abrir la ficha de la aeronave, la de la persona, buscar el
permiso de la faena y decidir uno mismo si alguna de las tres cosas impide
despegar. Un cálculo hecho a mano, en terreno, con prisa.

## La regla, y de dónde sale

**Vencido bloquea; por vencer avisa.** Es la traducción directa de la escala de
severidad que la aplicación ya usa (`UX-01`): rojo es *no se puede*, ámbar es *se
puede y hay que ocuparse*. Aplicarla acá no inventa un criterio nuevo, usa el que
la bandeja y el panel ya aplican — y eso importa más que la elección en sí: dos
pantallas que responden distinto sobre el mismo hecho es lo que enseña a
desconfiar de las dos.

⚠️ **Con una excepción escrita, y no es un olvido.** La brecha de compatibilidad
operador–aeronave **avisa y no bloquea**, porque eso se acordó con el usuario el
2026-07-30 y está escrito en `registry.selectors`: *"a warning, not a validation
error"*. La comparación es por palabras clave contra el modelo de la aeronave, o
sea una heurística; convertirla acá en un bloqueo le daría a una coincidencia de
texto la última palabra sobre si se vuela.

⚠️ **Y esta pantalla no autoriza nada.** No escribe, no aprueba y no reemplaza al
permiso: lee lo que ya está cargado y lo dice junto. Un «sí» acá significa *"en
los registros no hay nada que lo impida"*, no *"volá"*. Lo dice también la
pantalla, y no es una fórmula de cortesía: quien firma sigue siendo quien firma.
"""

from dataclasses import dataclass, field
from datetime import timedelta

from django.urls import reverse
from django.utils.text import capfirst
from django.utils.translation import gettext_lazy as _

#: Cuántos días adelante mira el aviso ámbar. Es el mismo horizonte de
#: `panel_readiness`, y a propósito: un vencimiento que el panel ya llama
#: "próximo" no puede ser noticia nueva acá.
WARNING_HORIZON_DAYS = 30


@dataclass(frozen=True)
class Finding:
    """Un motivo. `url` es a dónde se va a resolverlo — nunca a una explicación.

    Que todo hallazgo lleve enlace es la mitad del valor de la pantalla: decirle
    a alguien en faena que la credencial está vencida y dejarlo buscando dónde se
    renueva es la mitad de un aviso.
    """

    label: str
    detail: str
    url: str


@dataclass
class Check:
    """Una de las cuatro preguntas, con su respuesta.

    Se devuelven **todas**, también las que salieron bien. Un «sí» sin decir qué
    se miró es un «sí» que no se puede contrastar, y quien opera necesita poder
    decir ante una fiscalización *qué* dio por comprobado.
    """

    name: str
    blockers: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    @property
    def passed(self):
        return not self.blockers


@dataclass
class Verdict:
    checks: list = field(default_factory=list)

    @property
    def blockers(self):
        return [item for check in self.checks for item in check.blockers]

    @property
    def warnings(self):
        return [item for check in self.checks for item in check.warnings]

    @property
    def can_fly(self):
        return not self.blockers


def _expiry_finding(label, expiry, today, url, missing_detail):
    """Clasifica una fecha de vigencia en bloqueo, aviso o nada.

    ⚠️ **La fecha ausente es un bloqueo, no un silencio.** Es la decisión menos
    obvia del módulo y la más importante: sin fecha cargada nadie puede afirmar
    que la vigencia está al día, y una pantalla que contesta «sí» porque *no
    sabe* es peor que una que no contesta. En el resto de la aplicación un nulo
    se muestra como hueco (la marca ámbar punteada del informe); acá el hueco
    tiene que pesar, porque de esto sale un despegue.
    """
    if expiry is None:
        return "blocker", Finding(label=label, detail=missing_detail, url=url)
    days = (expiry - today).days
    if days < 0:
        return "blocker", Finding(
            label=label,
            detail=_("Expired on %(date)s.") % {"date": expiry.strftime("%d-%m-%Y")},
            url=url,
        )
    if days <= WARNING_HORIZON_DAYS:
        return "warning", Finding(
            label=label,
            detail=_("Expires on %(date)s, in %(days)s days.")
            % {"date": expiry.strftime("%d-%m-%Y"), "days": days},
            url=url,
        )
    return None, None


def _add(check, outcome, finding):
    if outcome == "blocker":
        check.blockers.append(finding)
    elif outcome == "warning":
        check.warnings.append(finding)


def _check_aircraft(aircraft, today):
    from apps.compliance.models import Document

    # ⚠️ El nombre sale del `verbose_name` del modelo y no de `_("Aircraft")`.
    # Ese msgid ya está en el catálogo traducido como **«Aeronaves»**, porque lo
    # escribe el menú, y acá se está hablando de **una**: la lista decía
    # "✕ Aeronaves" para una sola matrícula. Visto en el navegador; ningún test
    # lo habría notado, porque la cadena existía y estaba traducida.
    check = Check(name=capfirst(aircraft._meta.verbose_name))
    url = reverse("aircraft-detail", args=[aircraft.pk])

    # El estado del fuselaje antes que cualquier papel: una aeronave dañada o en
    # mantención no vuela aunque tenga todos sus documentos al día, y decirlo
    # primero evita que alguien lea tres renglones verdes y se quede con ésos.
    if aircraft.status in {"damaged", "maintenance", "retired"}:
        check.blockers.append(
            Finding(
                label=_("Airframe status"),
                detail=_("The aircraft is recorded as «%(status)s».")
                % {"status": aircraft.get_status_display()},
                url=url,
            )
        )

    _add(
        check,
        *_expiry_finding(
            _("JAC insurance"),
            aircraft.insurance_expiry,
            today,
            url,
            _("No expiry date on file, so nothing here proves it is in force."),
        ),
    )

    for document in _expiring_documents(Document, aircraft):
        _add(
            check,
            *_expiry_finding(
                document.title,
                document.expiry_date,
                today,
                reverse("document-detail", args=[document.pk]),
                "",
            ),
        )
    return check


def _check_operator(operator, today):
    from apps.compliance.models import Document
    from apps.registry.models import KnowledgeAssessment, Qualification

    check = Check(name=capfirst(operator._meta.verbose_name))
    url = reverse("operator-detail", args=[operator.pk])

    _add(
        check,
        *_expiry_finding(
            _("DGAC credential"),
            operator.credential_expiry,
            today,
            url,
            _("No expiry date on file, so nothing here proves it is in force."),
        ),
    )

    for qualification in Qualification.objects.filter(
        operator=operator, is_active=True, expiry_date__isnull=False
    ).select_related("qualification_type"):
        _add(
            check,
            *_expiry_finding(
                str(qualification.qualification_type),
                qualification.expiry_date,
                today,
                url,
                "",
            ),
        )

    # Sólo la última: los intentos anteriores son historial, y su vencimiento ya
    # no es trabajo de nadie. Mismo criterio que la lista de vencimientos del
    # panel, que ya lo resolvió así.
    latest = (
        KnowledgeAssessment.objects.filter(operator=operator, is_active=True)
        .order_by("-taken_at")
        .first()
    )
    if latest and latest.expires_on:
        _add(
            check,
            *_expiry_finding(
                _("Knowledge assessment"), latest.expires_on, today, url, ""
            ),
        )

    for document in _expiring_documents(Document, operator):
        _add(
            check,
            *_expiry_finding(
                document.title,
                document.expiry_date,
                today,
                reverse("document-detail", args=[document.pk]),
                "",
            ),
        )
    return check


def _expiring_documents(Document, subject):
    """Los documentos vigentes que cuelgan de este registro y tienen vencimiento.

    `is_current_version=True` porque un reemplazo deja la versión anterior en la
    base: contarla haría que renovar un seguro **agregara** un bloqueo en vez de
    quitarlo.
    """
    from django.contrib.contenttypes.models import ContentType

    return Document.objects.filter(
        is_active=True,
        is_current_version=True,
        expiry_date__isnull=False,
        content_type=ContentType.objects.get_for_model(type(subject)),
        object_id=subject.pk,
    ).select_related("doc_type")


def _check_permission(cost_center, today):
    from apps.operations.models import FlightPermission

    check = Check(name=_("Flight permission"))
    permits = FlightPermission.objects.filter(
        cost_center=cost_center,
        is_active=True,
        status=FlightPermission.STATUS_APPROVED,
        valid_from__lte=today,
        valid_until__gte=today,
    ).order_by("valid_until")

    covering = list(permits)
    if not covering:
        check.blockers.append(
            Finding(
                label=_("Flight permission"),
                detail=_("No approved permit covers today for this cost centre."),
                url=reverse("permission-list") + f"?cost_center={cost_center.pk}",
            )
        )
        return check

    # El que vence primero es el que manda el aviso: es el que deja de cubrir
    # antes, y avisar por el más largo escondería justamente el que corre.
    soonest = covering[0]
    _add(
        check,
        *_expiry_finding(
            _("Permit %(folio)s") % {"folio": soonest.internal_folio},
            soonest.valid_until,
            today,
            reverse("permission-detail", args=[soonest.pk]),
            "",
        ),
    )
    return check


def _check_pairing(aircraft, operator, cost_center):
    """La terna encaja: la persona sabe volar **ese** modelo, y las dos cosas
    pertenecen a **esa** faena.

    Todo acá avisa y nada bloquea. La compatibilidad, porque así se acordó el
    2026-07-30 y es una coincidencia de palabras clave contra el modelo — darle
    la última palabra sobre un despegue sería darle demasiada. Y la pertenencia,
    porque prestar un equipo entre faenas es una operación normal: lo que
    corresponde es que quede dicho, no que se impida.
    """
    from apps.registry.selectors import operator_aircraft_compatibility_gaps

    check = Check(name=_("Operator and aircraft"))

    if operator_aircraft_compatibility_gaps([operator], [aircraft]):
        check.warnings.append(
            Finding(
                label=_("Model qualification"),
                detail=_(
                    "No current qualification of this operator covers the model "
                    "%(model)s."
                )
                % {"model": aircraft.model},
                url=reverse("operator-detail", args=[operator.pk]),
            )
        )

    for subject, label, url_name in (
        (aircraft, _("Aircraft belongs elsewhere"), "aircraft-detail"),
        (operator, _("Operator belongs elsewhere"), "operator-detail"),
    ):
        if subject.cost_center_id and subject.cost_center_id != cost_center.pk:
            check.warnings.append(
                Finding(
                    label=label,
                    detail=_("Recorded in %(code)s, not in %(chosen)s.")
                    % {
                        "code": subject.cost_center.code,
                        "chosen": cost_center.code,
                    },
                    url=reverse(url_name, args=[subject.pk]),
                )
            )
    return check


def can_fly(aircraft, operator, cost_center, today):
    """El veredicto de la terna, con las cuatro comprobaciones a la vista.

    El orden no es alfabético: aeronave, operador, permiso y por último cómo
    encajan entre sí. Es el orden en el que quien está en faena mira las cosas —
    el equipo delante, la persona al lado, el papel en el bolsillo— y leer un
    veredicto en el orden en que se comprueba es lo que permite abandonarlo a la
    mitad cuando ya salió que no.
    """
    return Verdict(
        checks=[
            _check_aircraft(aircraft, today),
            _check_operator(operator, today),
            _check_permission(cost_center, today),
            _check_pairing(aircraft, operator, cost_center),
        ]
    )


def horizon(today):
    """La fecha hasta la que se avisa. Para que la pantalla pueda decirla en vez
    de dejar al lector deducir de dónde salió el ámbar."""
    return today + timedelta(days=WARNING_HORIZON_DAYS)
