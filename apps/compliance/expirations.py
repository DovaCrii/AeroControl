"""Qué vence en los próximos treinta días, y de qué cuelga cada vencimiento.

⚠️ **LV-240: esto vivía en `apps/dashboard/views.py`, y por eso el correo diario
avisaba de dos de seis fuentes.** El panel recorría las seis —habilitación,
credencial DGAC, seguro JAC, prueba de conocimientos, documento y permiso— y
`compliance.digest.build_digest` tenía su propia recolección parcial con dos. Dos
implementaciones del mismo hecho, y la de menos alcance era **la que sale por
correo**: quien no abre la aplicación no se enteraba de que caduca una póliza.

No se compartía antes porque la dependencia iba al revés: `digest` no puede
importar de `dashboard.views`, que a su vez importa `digest` en el nivel de módulo.
Viviendo acá —en el dominio y no en la presentación— las dos superficies leen lo
mismo, y "qué vence" pasa a tener un solo dueño.

Lo que este módulo garantiza y la recolección del digest no tenía:

* **Lo que ya se revisó y se cerró no vuelve a salir** (`LV-122`). Un vencimiento
  resuelto y no renovado tiene una fecha que no va a cambiar nunca, así que sin
  esto se queda para siempre — en el panel se notó porque llenaba la lista, y en un
  correo diario es peor: *"un aviso que sale todos los días enseña a no leerlo"*
  (`LV-118`).
* **Los registros en estado terminal quedan fuera** (`LV-90`, `LV-113`), leído de
  `TERMINAL_STATUSES` del propio modelo. Una aeronave dada de baja con el seguro
  vencido en 2024 no es trabajo de nadie.
* **Sólo la última prueba de conocimientos de cada operador**: los intentos
  anteriores son historial, y su vencimiento ya no es trabajo.
"""

from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils.translation import gettext as _

from apps.compliance.digest import BUCKET_TEXT_CSS, SUBJECT_TONE_CSS, bucket_for
from apps.compliance.models import Alert, Document
from apps.compliance.reports import (
    cost_centers_for_refs,
    document_subjects,
    documents_for_cost_center,
)
from apps.compliance.watchables import terminal_statuses
from apps.operations.models import FlightPermission
from apps.registry.models import (
    Aircraft,
    KnowledgeAssessment,
    Operator,
    Qualification,
)


def resolved_alert_keys(candidates=None):
    """LV-122: (tipo, registro, valor) de todo lo que la bandeja ya cerró.

    Una consulta, no una por fila: el panel se abre en cada login y esto se
    cruza contra cinco listados. Devuelve la **misma clave con que
    `generate_alerts` deduplica** desde `LV-111` — y usarla textual es lo que
    garantiza que el panel esconda ni más ni menos de lo que la bandeja
    considera cerrado.

    **LV-237: `candidates` acota la consulta a lo que se va a cruzar.** Sin él,
    esto era `filter(is_resolved=True, is_active=True)` **sin cota alguna** —ni
    fecha, ni faena, ni modelo— materializado en un `set` de Python en cada
    carga del panel. El costo no dependía de lo que la pantalla muestra sino de
    **toda la historia de la operación**: cada vencimiento que alguien resolvió
    alguna vez seguía viajando a memoria para filtrar una lista de diez filas, y
    a tres años son decenas de miles de tuplas por inicio de sesión. Crecía sin
    techo y en silencio, porque la pantalla se ve igual.

    `candidates` es un iterable de `(content_type_id, object_id)`. El `IN` sobre
    los dos campos por separado puede traer alguna fila de más —el producto
    cartesiano de ambos conjuntos—, y no importa: **el cruce final sigue siendo
    por la tupla completa de tres**, así que el resultado es idéntico y lo único
    que cambia es cuánto se trae. Sin candidatos no hay nada que cruzar y se
    devuelve el conjunto vacío sin consultar.

    Se conserva el parámetro opcional en `None` —comportamiento anterior, sin
    cota— porque la firma es pública y hay llamadores que preguntan por el
    universo completo.
    """
    alerts = Alert.objects.filter(is_resolved=True, is_active=True)
    if candidates is not None:
        pairs = set(candidates)
        if not pairs:
            return set()
        alerts = alerts.filter(
            content_type_id__in={content_type for content_type, _pk in pairs},
            object_id__in={pk for _ct, pk in pairs},
        )
    return set(alerts.values_list("content_type_id", "object_id", "watched_value"))


# LV-191: qué permiso hace falta para ver cada fuente de la lista de
# vencimientos. Declarado como mapa y no como seis `if` repartidos por la función
# por la misma razón que `ALERT_COST_CENTER_PATHS`: acá un `if` olvidado no se ve
# y es una fuga, mientras una fuente que falte en esta tabla salta a la vista —
# y la tabla se lee de una vez para saber qué gatea qué.
#
# Son los permisos por defecto de Django sobre el modelo del que sale cada fila.
# No se inventa un permiso nuevo: si alguien puede ver la ficha de una aeronave,
# puede ver que su seguro vence; y si no puede, la fila del panel no es el lugar
# por donde enterarse.
EXPIRATION_PERMISSIONS = {
    Qualification: "registry.view_qualification",
    Operator: "registry.view_operator",
    Aircraft: "registry.view_aircraft",
    KnowledgeAssessment: "registry.view_knowledgeassessment",
    Document: "compliance.view_document",
    FlightPermission: "operations.view_flightpermission",
}
# LV-217: de qué cuelga cada vencimiento, que es lo que decide el color de su
# píldora. Los tonos viven en `digest.SUBJECT_TONE_CSS`, junto a la escala de
# urgencia que no deben canibalizar.
#
# **Declarado con la misma clave que la tabla de arriba, y al lado, a propósito.**
# Los dos datos que necesita una fuente nueva —qué permiso la gatea y de qué
# cuelga— quedan a la vista uno sobre otro: agregar una fuente y olvidar el color
# se nota leyendo diez líneas, y `add()` lo delata en el momento porque busca la
# clave sin `get`.
EXPIRATION_SUBJECT_TONES = {
    Qualification: "person",
    Operator: "person",
    Aircraft: "aircraft",
    KnowledgeAssessment: "person",
    Document: "document",
    FlightPermission: "permit",
}


def upcoming_expirations(today, cutoff, cost_center=None, user=None):
    """Lo que expira **hasta** `cutoff`, incluido lo que ya expiró (T5.4/U4):
    habilitaciones, credenciales DGAC, seguros JAC, documentos y permisos. Cada
    ítem lleva su enlace para que el panel deje al usuario donde puede actuar.

    **LV-146: las cinco fuentes respetan el filtro por centro de costo, y cada
    fila dice a qué faena pertenece.** Los documentos también: el párrafo que
    estaba acá decía que iban siempre "porque cuelgan de una relación genérica
    sin centro de costo directo", y esa premisa dejó de ser cierta cuando
    `LV-129` escribió `documents_for_cost_center` — que la tarjeta "Alertas
    pendientes" de la misma pantalla ya usa. Elegir una faena recortaba cuatro
    fuentes y dejaba los documentos de las otras en la lista: el mismo defecto
    que LV-129 arregló en la tarjeta y no en la lista de al lado.

    "Sin faena" es un caso real y se dice: `Aircraft.cost_center` y
    `Operator.cost_center` son nulos, y un documento de empresa cuelga del
    tenant, no de una faena.

    R1.1: el "bucket" de cada ítem reusa `digest.bucket_for` -- la misma escala
    overdue/due_7/due_15/due_30 que el reporte de cumplimiento, en vez de una
    cuarta escala propia.

    **LV-120: ya no hay piso en `today`.** Las cinco consultas filtraban
    `expiry >= today`, así que **nada vencido podía aparecer nunca** -- y el
    reporte del usuario (2026-08-20) es exacto: la tarjeta decía "5 faltantes o
    vencidos" y la lista de al lado sólo mostraba los dos del 2026-09-05,
    mientras `RPA-5534` (vencido el 08-08) y `RPA-2198` (el 05-20, tres meses)
    no salían en ninguna parte. La rama `overdue` de la plantilla estaba escrita
    completa —en rojo y en negrita— y **no podía dibujarse jamás**, que es la
    señal de que el hueco estaba en los datos y no en el diseño.

    El piso no fue un descuido: el comentario que lo puso dice que sin él la
    lista mostraba "todas las habilitaciones históricamente vencidas, en una
    página que se abre en cada login". Era un problema real y la solución se
    pasó de largo -- para sacar el ruido antiguo sacó también lo urgente.

    Lo que acota ahora es **la misma regla que el motor de alertas**: se excluyen
    los registros en estado terminal, leído de `TERMINAL_STATUSES` del propio
    modelo vía `terminal_statuses()` (`LV-90`, `LV-113`). Así el panel y la
    bandeja **no pueden discrepar por construcción**, que es justo lo que el
    usuario notó al ver una alerta sin su fila en el panel; y una aeronave dada
    de baja con el seguro vencido en 2024 deja de contar sin necesidad de una
    ventana hacia atrás elegida a dedo. Un permiso vencido tampoco reaparece: al
    caducar queda en `expired`, que es terminal (`LV-83`).

    **LV-122: y tampoco aparece lo que ya se revisó y se cerró.** `LV-120` alineó
    el panel con la bandeja en una sola dirección —mostrar lo que la bandeja
    muestra— y faltaba la otra: **esconder lo que la bandeja cerró**. El usuario
    lo vio el mismo día: la credencial de `Carlos Peñailillo`, vencida el
    2025-05-02 y resuelta con el motivo *"Fuera de CC con operación RPA"*, se
    instaló en el panel para siempre — porque esa fecha ya no va a cambiar
    nunca. Sus palabras: *"que sean las no resueltas nada más o si no se llenará
    completo"*, y es literal: cada vencimiento resuelto y no renovado se queda
    en la lista, así que el panel se llena de trabajo ya hecho hasta empujar
    fuera del corte de diez filas lo que sí importa.

    Se filtra con **la misma clave con que el motor deduplica** (`LV-111`):
    (registro, valor vigilado). Eso importa por lo que **no** esconde -- una
    renovación cambia el valor, así que el vencimiento siguiente es una fila
    nueva y vuelve a mostrarse, que es exactamente la mitad que `LV-111` decidió
    no suprimir. Y esconde sólo lo **resuelto**, no "lo que no tiene alerta
    abierta": un vencimiento que el motor todavía no miró (se genera a las
    06:00) no tiene alerta ninguna y tiene que verse igual.
    """
    items = []

    def code(cost_center_of_the_row):
        """El código de la faena, o "" cuando la fila no tiene ninguna.

        LV-146: `Aircraft.cost_center` y `Operator.cost_center` son `null=True`,
        así que "sin faena" es un caso real también en las fuentes directas y no
        sólo en los documentos de empresa.
        """
        return cost_center_of_the_row.code if cost_center_of_the_row else ""

    def add(model, record_pk, item):
        """Agrega el ítem salvo que su alerta ya esté resuelta o el usuario no
        pueda ver esa fuente.

        Se filtra acá y no al final para no construir la fila que se va a
        descartar, y con `get_for_model` —que Django cachea por modelo— para no
        pagar una consulta de `ContentType` por listado.

        **LV-191: el gate de permisos va acá, en un solo lugar.** Cuesta ejecutar
        la consulta de una fuente que se va a descartar —seis consultas acotadas
        en el peor caso, no una por fila—, y se paga a propósito: seis `if`
        repartidos por la función son seis lugares donde olvidarse de uno, y
        olvidarse de uno es una fuga que nadie ve. `model` ya llega acá por el
        filtro de `LV-122`, así que el punto de control existía y estaba sin usar.

        `user is None` **no gatea nada**, y es deliberado: los tests y los
        llamadores internos que preguntan "qué vence" sin una sesión detrás están
        probando la consulta, no la autorización. La vista pasa siempre
        `request.user`.

        **LV-237: el descarte de lo ya resuelto ya no ocurre acá.** Se recogen
        todos los ítems con su clave y el cruce va al final, en una sola consulta
        acotada a estos candidatos — ver el cierre de la función.
        """
        if user is not None and not user.has_perm(EXPIRATION_PERMISSIONS[model]):
            return
        item["key"] = (
            ContentType.objects.get_for_model(model).id,
            record_pk,
            item["date"].isoformat(),
        )
        # LV-148: el color del tramo sale de la misma tabla que la insignia de
        # la bandeja. Antes era una cadena de cuatro `{% if %}` en la
        # plantilla, y por eso `due_30` era ámbar acá y azul allá.
        item["tone"] = BUCKET_TEXT_CSS.get(item["bucket"], "")
        # LV-217: el color del **tipo**, que contesta otra pregunta que el
        # tramo de urgencia de la línea de arriba. Sin `get` y sin valor por
        # defecto: una fuente nueva sin entrada en la tabla levanta acá, en el
        # momento, en vez de dibujarse gris para siempre — que es el estado
        # que esta fila vino a arreglar y el que nadie reportaría dos veces.
        item["kind_css"] = SUBJECT_TONE_CSS[EXPIRATION_SUBJECT_TONES[model]]
        items.append(item)

    quals = Qualification.objects.filter(
        is_active=True,
        expiry_date__lte=cutoff,
        # LV-146: `operator__cost_center` en el `select_related`, o leer la faena
        # de cada fila costaría una consulta por fila.
    ).select_related("operator__cost_center", "qualification_type")
    if cost_center:
        quals = quals.filter(operator__cost_center=cost_center)
    for qual in quals:
        add(
            Qualification,
            qual.pk,
            {
                "kind": _("Qualification"),
                "label": f"{qual.operator} — {qual.qualification_type}",
                "date": qual.expiry_date,
                "bucket": bucket_for(qual.expiry_date, today),
                "cost_center_code": code(qual.operator.cost_center),
                "url": reverse("operator-detail", args=[qual.operator_id]),
            },
        )

    # LV-29: the DGAC vigencias join the same window -- a lapsing credential or
    # JAC insurance is exactly what "upcoming expirations" is for.
    credentials = Operator.objects.filter(
        is_active=True, credential_expiry__lte=cutoff
    ).select_related("cost_center")
    if cost_center:
        credentials = credentials.filter(cost_center=cost_center)
    for operator in credentials:
        add(
            Operator,
            operator.pk,
            {
                "kind": _("DGAC credential"),
                "label": operator.full_name,
                "date": operator.credential_expiry,
                "bucket": bucket_for(operator.credential_expiry, today),
                "cost_center_code": code(operator.cost_center),
                "url": reverse("operator-detail", args=[operator.pk]),
            },
        )

    insured = (
        Aircraft.objects.filter(is_active=True, insurance_expiry__lte=cutoff)
        .exclude(status__in=terminal_statuses(Aircraft))
        .select_related("cost_center")
    )
    if cost_center:
        insured = insured.filter(cost_center=cost_center)
    for aircraft in insured:
        add(
            Aircraft,
            aircraft.pk,
            {
                "kind": _("JAC insurance"),
                "label": aircraft.registration,
                "date": aircraft.insurance_expiry,
                "bucket": bucket_for(aircraft.insurance_expiry, today),
                "cost_center_code": code(aircraft.cost_center),
                "url": reverse("aircraft-detail", args=[aircraft.pk]),
            },
        )

    # LV-158: la prueba de conocimientos vence a los 12 meses y entra a la misma
    # lista que las credenciales -- el usuario pidió que el resultado sirviera
    # para "saber cómo está la condición de los profesionales", y una vigencia
    # que nadie ve venir no sirve para eso. Sólo la **última** de cada operador:
    # los intentos anteriores son historial, y su vencimiento ya no es trabajo.
    assessments = (
        KnowledgeAssessment.objects.filter(is_active=True, expires_on__lte=cutoff)
        .select_related("operator__cost_center")
        .order_by("operator_id", "-taken_at")
    )
    if cost_center:
        assessments = assessments.filter(operator__cost_center=cost_center)
    seen_operators = set()
    for assessment in assessments:
        if assessment.operator_id in seen_operators:
            continue
        seen_operators.add(assessment.operator_id)
        add(
            KnowledgeAssessment,
            assessment.pk,
            {
                "kind": _("Knowledge assessment"),
                "label": str(assessment.operator),
                "date": assessment.expires_on,
                "bucket": bucket_for(assessment.expires_on, today),
                "cost_center_code": code(assessment.operator.cost_center),
                "url": reverse("operator-detail", args=[assessment.operator_id]),
            },
        )

    document_qs = Document.objects.filter(
        is_active=True,
        is_current_version=True,
        expiry_date__isnull=False,
        expiry_date__lte=cutoff,
    ).select_related("doc_type")
    # LV-146: los documentos **pasan a respetar el filtro por faena**. El
    # docstring de esta función decía que iban siempre "porque cuelgan de una
    # relación genérica sin centro de costo directo", y esa premisa ya no se
    # sostiene: `documents_for_cost_center` sabe atribuirlos desde `LV-129`, y la
    # tarjeta "Alertas pendientes" de la misma pantalla ya los descuenta con ella.
    # Elegir CC738 recortaba cuatro fuentes y dejaba los documentos de las otras
    # faenas en la lista — el mismo defecto que LV-129 arregló en la tarjeta y no
    # en la lista de al lado.
    if cost_center:
        document_qs = documents_for_cost_center(cost_center, document_qs)
    documents = list(document_qs)
    # Una vuelta para todos los documentos, no una por documento: el sujeto de
    # cada uno se resuelve con el mismo mapa que usa la bandeja de alertas.
    document_centers = cost_centers_for_refs(
        (document.content_type_id, document.object_id) for document in documents
    )
    # LV-186: de qué cuelga cada documento. El título no lo dice —hay una "Carta
    # Permiso" por permiso— así que la fila obligaba a abrir para saber a cuál se
    # refiere. Es el único de los cinco orígenes con ese problema: en los otros
    # la etiqueta **es** el sujeto (la matrícula, el nombre de la persona).
    document_labels = document_subjects(documents)
    for document in documents:
        add(
            Document,
            document.pk,
            {
                "kind": _("Document"),
                "label": document.title,
                "subject": document_labels.get(document.pk, ""),
                "date": document.expiry_date,
                "bucket": bucket_for(document.expiry_date, today),
                "cost_center_code": code(
                    document_centers.get((document.content_type_id, document.object_id))
                ),
                "url": reverse("document-detail", args=[document.pk]),
            },
        )

    permissions = (
        FlightPermission.objects.filter(is_active=True, valid_until__lte=cutoff)
        .exclude(status__in=terminal_statuses(FlightPermission))
        .select_related("cost_center")
    )
    if cost_center:
        permissions = permissions.filter(cost_center=cost_center)
    for permission in permissions:
        add(
            FlightPermission,
            permission.pk,
            {
                "kind": _("Flight permission"),
                # R1.2/R2.2/R2.3: used to be `permission_number or "Pending
                # DGAC folio"` -- permission_number is None until the DGAC
                # folio arrives (LV-39), and rendered as-is the row read
                # "Flight permission None" (verified live on the demo).
                # internal_folio is assigned at creation and never blank.
                "label": permission.internal_folio,
                "date": permission.valid_until,
                "bucket": bucket_for(permission.valid_until, today),
                "cost_center_code": code(permission.cost_center),
                "url": reverse("permission-detail", args=[permission.pk]),
            },
        )

    # LV-122, con la consulta de LV-237: se esconde lo que la bandeja ya cerró, y
    # se pregunta **sólo por estos candidatos** en vez de traerse toda la historia
    # de alertas resueltas. El cruce sigue siendo por la tupla de tres —la misma
    # con que `generate_alerts` deduplica desde `LV-111`—, así que lo que se
    # esconde y lo que no es exactamente lo de antes: una renovación cambia el
    # valor vigilado, y por eso el vencimiento siguiente vuelve a aparecer.
    triaged = resolved_alert_keys(item["key"][:2] for item in items)
    items = [item for item in items if item.pop("key") not in triaged]

    items.sort(key=lambda item: item["date"])
    return items
