from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.db.models.functions import TruncMonth
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.compliance.digest import BUCKET_TEXT_CSS, SUBJECT_TONE_CSS, bucket_for
from apps.compliance.reports import (
    alerts_for_cost_center,
    cost_centers_for_refs,
    document_subjects,
    documents_for_cost_center,
)
from apps.compliance.models import Alert, AlertRule, Document, DocumentType
from apps.compliance.watchables import terminal_statuses
from apps.maintenance.models import MaintenanceRecord
from apps.operations.models import FlightPermission, FlightRecord, FlightRequest
from apps.registry.models import (
    Aircraft,
    CostCenter,
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


def panel_readiness(today, cost_center=None):
    """LV-89: can we operate today? -- as three counts, not two pie charts.

    Replaces "Aircraft by status" (two slices) and "Permissions by status" (one
    bar), which took a third of the screen to restate numbers the tiles above
    already showed. These three answer the question the panel is opened for, and
    each is a **fraction with its shortfall named**: a percentage alone tells you
    something is wrong without telling you how much work it is to fix.

    Nothing here is new data. Fleet availability reuses the target agreed with
    the user on 2026-08-12 (`FLEET_AVAILABILITY_TARGET`, 90%), and the other two
    read the same fields the alert engine watches -- so a number on the panel and
    an alert in the inbox can never disagree.

    `retired` is excluded from the fleet denominator for the same reason
    `kpis.fleet_availability` excludes it: a decommissioned aircraft is not
    unavailable, it left the fleet, and counting it would make the figure sag
    permanently for a good decision.
    """
    from apps.compliance.kpis import FLEET_AVAILABILITY_TARGET, permit_counts

    horizon = today + timedelta(days=30)

    fleet = Aircraft.objects.filter(is_active=True).exclude(status="retired")
    # LV-229: fuera los equipos de una faena que **no vuela**.
    #
    # Encontrado midiendo `LV-74`: `RPA-2019` figuraba como "sin seguro JAC" y
    # está en `CC110`, uno de los centros administrativos que `LV-205` distinguió
    # a pedido del usuario (*"el CC110 de casa matriz o 410, por ejemplo, estamos
    # a cargo más de los equipos que volar"*). Confirmado con él: ese equipo está
    # en bodega y no opera, así que **no es una brecha de seguro** — y contarlo
    # como falta bajaba el indicador por una decisión correcta.
    #
    # Es el mismo criterio que `permit_status_by_cost_center` ya aplicaba a los
    # permisos, y que a este contador le faltaba: dos indicadores del mismo panel
    # respondían distinto a la misma pregunta sobre la misma faena.
    #
    # `cost_center__isnull=True` **entra**, no se excluye: una aeronave sin faena
    # no es una aeronave que no vuela, es una aeronave cuya pertenencia falta —y
    # eso sí es una brecha que hay que ver, no una que ocultar.
    fleet = fleet.exclude(cost_center__operates_flights=False)
    operators = Operator.objects.filter(is_active=True)

    # **El padrón que se cuenta es el que existía en `today`, no el de hoy.**
    #
    # `today` ya mandaba sobre las comparaciones de vencimiento —una credencial
    # vence *respecto de* esa fecha— pero no sobre la población: los dos
    # `filter(is_active=True)` de arriba traían el padrón **actual**. Con la
    # fecha de hoy da igual; con la de un mes cerrado, no. Medido en producción:
    # el payload de agosto devolvía **42 operadores** y el informe emitido a la
    # DGAC decía **41**. Un informe de agosto generado en diciembre habría dado
    # otra cifra todavía, que es justo lo que congelar el dato viene a evitar.
    #
    # Va sin parámetro y siempre: `created_at__date <= today` es verdadero para
    # toda fila cuando `today` es hoy, así que **el panel no cambia** — y una
    # segunda función "igual pero con corte" es cómo el panel y el informe
    # empiezan a discrepar, la lección que `LV-188` y `LV-201` ya dejaron.
    #
    # ⚠️ **Lo que este corte NO hace, y hay que decirlo porque el informe va
    # firmado**: no reconstruye el padrón de esa fecha, sólo **deja de contar lo
    # que todavía no existía**. Sin historial de `is_active` no se sabe quién
    # estaba archivado entonces, y si una ficha se cargó a destiempo su
    # `created_at` es la fecha de carga y no la del hecho. Es una cota superior
    # honesta, no una foto.
    fleet = fleet.filter(created_at__date__lte=today)
    operators = operators.filter(created_at__date__lte=today)

    if cost_center:
        fleet = fleet.filter(cost_center=cost_center)
        operators = operators.filter(cost_center=cost_center)

    fleet_total = fleet.count()
    flyable = fleet.filter(status="active").count()
    # "Up to date" means the policy is on file *and* still valid. An aircraft
    # whose insurance lapsed yesterday is not covered, whatever its status says.
    insured = fleet.filter(
        insurance_status=Aircraft.INSURANCE_STATUS_ACTIVE,
        insurance_expiry__gte=today,
    ).count()
    operators_total = operators.count()
    credentialed = operators.filter(credential_expiry__gte=today).count()

    # LV-201: los permisos vuelven a la fila, y vuelven porque el usuario los
    # pidió: *"es importante mencionar tanto en los reportes como en el dashboard
    # la cantidad de permisos vigentes, atrasados, o el indicador en general"*. La
    # fila mostraba flota, seguros y credenciales — y ninguna cifra del objeto que
    # esta aplicación existe para tramitar.
    #
    # No es una tarjeta nueva suelta: el docstring de arriba cuenta que `LV-89`
    # **retiró** un gráfico "Permissions by status" porque restataba números sin
    # decir qué hacer. Vuelven con la forma que esa fila fijó, una fracción con su
    # faltante nombrado.
    #
    # **El cálculo vive en `kpis.permit_counts` y no acá**, aunque acá sea el único
    # lugar donde hoy se dibuja: el pedido nombraba el panel **y** los informes, y
    # dos cálculos separados de la misma cifra es exactamente cómo el panel y el
    # informe terminan diciendo números distintos. `LV-188` acabó de mostrar el
    # costo de esa separación en otra función.
    permits = permit_counts(today, cost_center)

    return {
        "readiness": [
            {
                # LV-129: clave estable para direccionar la tarjeta sin pasar
                # por su etiqueta, que es traducible -- un test que compare
                # contra el texto pasa o falla según el idioma activo, que es lo
                # que `LV-95` dejó escrito y este archivo volvió a pagar.
                "key": "fleet",
                "label": _("Fleet available"),
                "count": flyable,
                "total": fleet_total,
                "pct": round(flyable * 100 / fleet_total, 1) if fleet_total else None,
                "target": FLEET_AVAILABILITY_TARGET,
                "shortfall": fleet_total - flyable,
                "shortfall_label": _("not flyable"),
                "url": reverse("aircraft-list"),
            },
            {
                "key": "insurance",
                "label": _("Insurance up to date"),
                "count": insured,
                "total": fleet_total,
                "pct": round(insured * 100 / fleet_total, 1) if fleet_total else None,
                "target": None,
                "shortfall": fleet_total - insured,
                # LV-129: "faltantes o vencidos" era una sola cifra para dos
                # cosas que se arreglan distinto -- cargar una fecha que nadie
                # ingresó, o renovar una póliza que caducó. Sumadas, además, no
                # cuadraban con ninguna otra tarjeta del panel: los "faltantes"
                # no generan alerta (`LV-29`: un nulo es "nunca se ingresó") ni
                # aparecen en la lista de vencimientos, así que el 5 de acá no
                # tenía cómo conversar con el 3 de más arriba.
                "missing": fleet.filter(insurance_expiry__isnull=True).count(),
                "lapsed": fleet.filter(insurance_expiry__lt=today).count(),
                "soon": fleet.filter(
                    insurance_expiry__gte=today, insurance_expiry__lte=horizon
                ).count(),
                "url": reverse("aircraft-list"),
            },
            {
                "key": "credentials",
                "label": _("Credentials up to date"),
                "count": credentialed,
                "total": operators_total,
                "pct": (
                    round(credentialed * 100 / operators_total, 1)
                    if operators_total
                    else None
                ),
                "target": None,
                "shortfall": operators_total - credentialed,
                "missing": operators.filter(credential_expiry__isnull=True).count(),
                "lapsed": operators.filter(credential_expiry__lt=today).count(),
                "soon": operators.filter(
                    credential_expiry__gte=today, credential_expiry__lte=horizon
                ).count(),
                "url": reverse("operator-list"),
            },
            {
                "key": "permits",
                "label": _("Permits in force"),
                "count": permits["in_force"],
                "total": permits["total"],
                "pct": permits["pct"],
                "target": None,
                "shortfall": permits["total"] - permits["in_force"],
                "lapsed": permits["lapsed"],
                # `awaiting` es propio de esta fila: las otras tres no tienen a
                # quién esperar. La plantilla lo dibuja junto a `lapsed` en vez de
                # en su lugar, porque son dos trabajos distintos y sumarlos sería
                # el defecto que `LV-129` corrigió en la tarjeta de seguros.
                "awaiting": permits["awaiting"],
                "soon": permits["soon"],
                "url": reverse("permission-list"),
            },
        ]
    }


# LV-237: acá vivían `panel_forecast` y sus tres ayudantes (`R8.4`, `LV-147`).
#
# `LV-216` retiró la tarjeta del clima de la plantilla a pedido del usuario —*"no es
# necesario que muestre el clima, ya el dashboard lo veo innecesario"*— y **borró sólo
# la mitad**: la vista siguió llamando `panel_forecast` en cada carga durante un mes,
# resolviendo candidatos de permisos, sitios con coordenadas y el plan geo ligado para
# un contexto que ninguna plantilla volvía a leer. Nueve consultas por carga de la
# primera pantalla de la aplicación, más la posible salida a Open-Meteo cuando la
# caché estaba fría.
#
# Es la razón por la que `test_lv237_panel_query_budget.py` existe: retirar una
# sección de la pantalla y dejar viva su consulta no se nota mirando la pantalla.
#
# **Lo que NO se fue**: `apps/core/weather.forecast_for` y la revisión meteorológica
# de la ficha del plan geo (`R8.1`/`R8.2`, `WeatherReview`), que es donde el pronóstico
# **queda registrado como evidencia** y era el único camino real desde `LV-216`. Un
# pronóstico no es reproducible después: preguntarle al proveedor por una fecha pasada
# devuelve otra corrida del modelo, o nada.
#
# Reponer la tarjeta es recuperar este bloque y el de la plantilla de git, en el commit
# anterior a esta fila.
@login_required
def dashboard(request):
    # OPS-8: an optional global filter by cost center. Silently ignored if it
    # does not resolve to a real, active cost center -- same "malformed filter
    # is a no-op, not an error" convention SearchMixin already uses.
    selected_cost_center = None
    cost_center_id = request.GET.get("cost_center")
    if cost_center_id:
        # LV-146: el `try/except` arregla un 500 vigente. "No-op silencioso"
        # cubría el UUID válido que no existe, el archivado y el de otro tenant —
        # pero no `?cost_center=abc`: un valor que no es UUID hace que
        # `filter(pk=...)` sobre una pk `UUIDField` levante `ValidationError`
        # **dentro** de la consulta, y eso no lo atrapa el `.first()`. Una URL
        # guardada, un autocompletado del navegador o un bot probando query
        # strings tiraban la primera pantalla de la app.
        try:
            selected_cost_center = CostCenter.objects.filter(
                pk=cost_center_id, is_active=True
            ).first()
        except (ValueError, ValidationError):
            selected_cost_center = None

    # `UX-17`: la faena elegida se recuerda. Quien trabaja una faena la vuelve a
    # elegir en cada login, y el panel es la primera pantalla del día.
    #
    # **En la sesión y no en una columna del usuario**: es una comodidad de
    # navegación, no una preferencia del negocio, y una columna la convertiría en
    # dato que alguien tiene que administrar.
    #
    # ⚠️ **La rama se elige por si el parámetro *viene*, no por si trae valor**, y
    # ésa es la distinción que hace que el recuerdo se pueda apagar: llegar sin
    # `cost_center` es abrir el panel de nuevo —y ahí se restaura—, mientras que
    # llegar con `?cost_center=` vacío es haber pedido "todas" a propósito, y eso
    # tiene que **borrar** el recuerdo. Sin separarlas, la única forma de volver a
    # verlo todo sería cerrar sesión.
    if "cost_center" in request.GET:
        # Se guarda la que resolvió de verdad y no la cadena cruda, así una faena
        # archivada deja de recordarse sola en vez de fijar un filtro que ya no
        # existe.
        if selected_cost_center is not None:
            request.session["dashboard_cost_center"] = str(selected_cost_center.pk)
        else:
            request.session.pop("dashboard_cost_center", None)
    else:
        remembered = request.session.get("dashboard_cost_center")
        if remembered:
            try:
                selected_cost_center = CostCenter.objects.filter(
                    pk=remembered, is_active=True
                ).first()
            except (ValueError, ValidationError):
                selected_cost_center = None
            if selected_cost_center is None:
                request.session.pop("dashboard_cost_center", None)
    cost_centers = CostCenter.objects.filter(is_active=True).order_by("code")

    # --- Summary counts ---
    aircraft_qs = Aircraft.objects.filter(is_active=True)
    operator_qs = Operator.objects.filter(is_active=True)
    if selected_cost_center:
        aircraft_qs = aircraft_qs.filter(cost_center=selected_cost_center)
        operator_qs = operator_qs.filter(cost_center=selected_cost_center)
    aircraft_count = aircraft_qs.filter(status="active").count()
    operator_count = operator_qs.count()
    # LV-129: respeta el filtro por centro de costo, como el resto de la fila.
    # Antes contaba las alertas de toda la operación, así que elegir una faena
    # cambiaba todas las tarjetas menos ésta — un número ajeno al filtro puesto
    # al lado de otros que sí lo obedecen.
    alert_count = alerts_for_cost_center(
        Alert.objects.filter(is_active=True, is_resolved=False), selected_cost_center
    ).count()

    # --- Compliance module setup state ---
    # The old onboarding card required *everything* to be empty, so with the
    # registry loaded it could never fire again - while compliance sat at zero
    # and the tiles read "0 alerts" as if all was well. These three steps are
    # what turns the digest, the alerts and the report from built to working.
    compliance_setup = {
        "doc_types": DocumentType.objects.filter(is_active=True).exists(),
        "documents": Document.objects.filter(is_active=True).exists(),
        "rules": AlertRule.objects.filter(is_active=True).exists(),
    }
    compliance_incomplete = not all(compliance_setup.values())

    # --- Expirations ---
    # LV-120: acotado por arriba (30 días) y, por abajo, por el **estado
    # terminal** del registro en vez de por la fecha de hoy -- ver
    # `upcoming_expirations`. El piso en `today` es lo que hacía que un seguro
    # vencido no apareciera nunca en el panel aunque su alerta sí estuviera en
    # la bandeja. Sólo la lista visible se recorta; los contadores son reales.
    # LV-206: el estado por faena sale de `kpis`, la misma casa que
    # `permit_counts` — un solo lugar donde vive "qué es un permiso vigente".
    from apps.compliance.kpis import permit_status_by_cost_center

    today = timezone.localdate()
    cutoff = today + timedelta(days=30)
    # LV-191: `request.user`, o la lista nombra permisos, matrículas, personas y
    # documentos que los permisos del usuario no le dan. Lo tapaba por accidente
    # el guard del onboarding, que escondía la sección entera cuando la base
    # estaba vacía — un control de acceso que no era uno, y que `LV-187` retiró.
    all_expirations = upcoming_expirations(
        today, cutoff, selected_cost_center, request.user
    )
    # Dos contadores y no uno: la tarjeta dice "Vence en 30 días", y meter ahí
    # lo ya vencido la volvería falsa -- la misma forma de defecto que `LV-118`
    # y `LV-119` corrigieron en la bandeja y en los correos. Lo vencido tiene
    # tarjeta propia, y sólo aparece cuando hay algo que mostrar.
    overdue_count = sum(1 for item in all_expirations if item["bucket"] == "overdue")
    expiring_count = len(all_expirations) - overdue_count
    expirations = all_expirations[:10]

    # LV-187: si se dibuja la tarjeta "Comienza tu operación" en vez del panel.
    #
    # Se calcula acá y no en la plantilla porque son cinco términos y ya iba mal
    # con cuatro: la condición vivía como `{% if not aircraft_count and not
    # operator_count and not alert_count and not stages %}`, y **`stages` nunca
    # existió en este contexto** — un cuarto término que parecía proteger algo y
    # era condición muerta desde algún refactor. Un `{% if %}` que nadie puede
    # leer de un vistazo es donde se esconde eso.
    #
    # **Los vencimientos entran en la condición.** No entraban, y el guard es
    # una decisión sobre si mostrar el panel: sin ellos, una operación con
    # documentos cargados y sin flota todavía —el orden real en que se carga,
    # porque los documentos de empresa no esperan a las aeronaves— veía el
    # onboarding con vencimientos reales detrás. La familia de `LV-120`.
    #
    # **Y sólo sin filtro por faena.** Los tres contadores lo respetan, así que
    # elegir una faena sin flota ni padrón cumplía la condición y escondía el
    # panel entero: "Comienza tu operación" y "1. Crear un centro de costo" a una
    # operación con 16 aeronaves, mientras la lista de al lado tenía vencimientos
    # de esa faena que no se dibujaban. Con una faena elegida lo que corresponde
    # es el panel con sus vacíos propios —"Nada expirado ni por vencer"—, que
    # dice la verdad: esta faena no tiene registros, no "no tienes operación".
    show_onboarding = not (
        selected_cost_center
        or aircraft_count
        or operator_count
        or alert_count
        or overdue_count
        or expiring_count
    )

    # --- LV-30: monthly compliance snapshot (latest period on record) ---
    # Compliant / total cost centers for the most recent reviewed month, with a
    # link into the monthly-review page. Absent (card hidden) until the first
    # month closes and check_monthly_records creates reviews.
    from django.db.models import Max

    from apps.compliance.models import MonthlyComplianceReview

    monthly_records = None
    review_qs = MonthlyComplianceReview.objects.filter(is_active=True)
    if selected_cost_center:
        review_qs = review_qs.filter(cost_center=selected_cost_center)
    latest_period = review_qs.aggregate(latest=Max("period"))["latest"]
    if latest_period:
        period_reviews = review_qs.filter(period=latest_period)
        monthly_records = {
            "period": latest_period.strftime("%Y-%m"),
            "total": period_reviews.count(),
            "compliant": period_reviews.filter(
                status=MonthlyComplianceReview.STATUS_COMPLETED
            ).count(),
            "pending": period_reviews.filter(
                status=MonthlyComplianceReview.STATUS_PENDING
            ).count(),
        }

    # LV-78/LV-89: the two Kanban charts are gone. The board was decommissioned
    # on 2026-08-12 and taken out of the menu, yet the panel kept drawing its
    # stages ("Recopilando antecedentes", "Enviado a DGAC") every day -- a chart
    # of a board nobody can reach, which reads as a live part of the operation.
    # This is step 1 of the retirement: the board loses its last surface without
    # a single row being deleted.

    # Charts label their slices with the human-readable choice, not the raw
    # database value (the legend used to read "active"/"in_progress"), and the
    # aggregations exclude archived rows like the rest of the app.
    def labelled(rows, field, choices):
        labels = dict(choices)
        return [
            {field: str(labels.get(row[field], row[field])), "count": row["count"]}
            for row in rows
        ]

    # LV-237: acá se agregaban "Aeronaves por estado" y "Permisos por estado".
    #
    # `LV-89` retiró los dos gráficos de la plantilla —restataban números que las
    # tarjetas de arriba ya mostraban— y las dos agregaciones se quedaron: se
    # calculaban, se serializaban al HTML en `#chart-data` y **ningún gráfico las
    # leía**. El propio `static/js/dashboard.js` lo dejó escrito: seguían ahí *"porque
    # un test lee `permissions_by_status` como evidencia del filtro por faena"*.
    #
    # Un test no debería fijar la forma del contexto de producción, y menos cobrando
    # dos agregaciones por inicio de sesión. La evidencia del filtro se lee ahora de
    # `readiness` —su fila `permits` respeta `selected_cost_center`—, que es un dato
    # que la pantalla **sí** dibuja: si mañana deja de filtrar, el test cae *y* se ve.
    #
    # De paso dejan de viajar al navegador dos distribuciones de estado que la página
    # no usa para nada.

    # --- Chart: Maintenance by type ---
    maintenance_qs = MaintenanceRecord.objects.filter(is_active=True)
    if selected_cost_center:
        maintenance_qs = maintenance_qs.filter(
            aircraft__cost_center=selected_cost_center
        )
    maint_by_type = labelled(
        maintenance_qs.values("maintenance_type")
        .annotate(count=Count("id"))
        .order_by("maintenance_type"),
        "maintenance_type",
        MaintenanceRecord.TYPES,
    )

    # --- LV-8e: maintenance that still needs planning ---
    # "To be defined" or missing a scheduled date, and not yet completed. The
    # alert engine only watches date *expiry*, so this absence is surfaced here
    # (and in the compliance report) instead of as an Alert object.
    incomplete_maintenance_count = (
        maintenance_qs.filter(status__in=["pending", "in_progress"])
        .filter(Q(maintenance_type="to_be_defined") | Q(scheduled_date__isnull=True))
        .count()
    )

    # --- R9.6: solicitudes SIGO presentadas y sin respuesta ---
    # Trabajo detenido en manos de un tercero: se presentó y nadie contestó. No
    # es una alerta —el motor vigila **vencimientos**, y acá no vence nada— sino
    # el mismo hueco que `LV-8e` resuelve para la mantención sin planificar: una
    # ausencia que ninguna regla de fecha puede ver.
    #
    # **Sin umbral inventado.** Se cuentan todas las presentadas y se muestra la
    # más antigua; poner "atrasada a los N días" exigiría un plazo de respuesta
    # de la DGAC que nadie confirmó, y un umbral inventado que resulta corto
    # enseña a ignorar la tarjeta.
    request_qs = FlightRequest.objects.filter(
        is_active=True, status=FlightRequest.STATUS_FILED
    )
    if selected_cost_center:
        request_qs = request_qs.filter(cost_center=selected_cost_center)
    awaiting_requests = list(request_qs.order_by("filed_on")[:5])
    awaiting_count = request_qs.count()
    longest_wait = next(
        (
            request.days_waiting()
            for request in awaiting_requests
            if request.days_waiting() is not None
        ),
        None,
    )

    # --- Chart: Monthly flight records (last 6 months) ---
    six_months_ago = timezone.localdate() - timedelta(days=180)
    flight_records_qs = FlightRecord.objects.filter(
        is_active=True, actual_date__gte=six_months_ago
    )
    if selected_cost_center:
        flight_records_qs = flight_records_qs.filter(
            aircraft__cost_center=selected_cost_center
        )
    monthly_flights = list(
        flight_records_qs.annotate(month=TruncMonth("actual_date"))
        .values("month")
        .annotate(count=Count("id"))
        .order_by("month")
    )

    chart_data = {
        "maintenance_by_type": maint_by_type,
        "monthly_flights": monthly_flights,
    }

    # `UX-15`: **qué está pasando hoy**, no sólo qué vence.
    #
    # Es lo que distingue un panel de cumplimiento de un centro de operaciones:
    # todo lo demás de esta pantalla contesta por vigencias y trabajo pendiente,
    # y ninguna tarjeta decía si hoy voló alguien. Criterio de la fila: *"sale de
    # datos existentes, sin modelo nuevo"* — y así es: `FlightRecord` ya guarda
    # la fecha real del vuelo.
    #
    # Por `actual_date` y no por `created_at`: la bitácora se escribe **después**
    # del vuelo, a veces al día siguiente, así que contar por fecha de carga
    # diría "0 operaciones hoy" en una jornada que sí voló. Es la misma
    # distinción que `LV-234` acaba de dejar cara: contar por cuándo se registró
    # en vez de por cuándo ocurrió.
    # LV-237: **una sola vuelta de `permit_counts` por carga.** El número de
    # permisos vigentes se dibuja dos veces —en el encabezado y en la tarjeta de
    # la tira, a cien píxeles— y hasta acá se calculaba dos veces para eso: una
    # dentro de `panel_readiness` y otra en esta función. Son la misma cifra con
    # los mismos argumentos, así que la tira se arma primero y el encabezado lee
    # de ella. Dos llamadas separadas además podían llegar a discrepar, que es
    # justo lo que `LV-201` centralizó `permit_counts` para evitar.
    readiness = panel_readiness(today, selected_cost_center)
    permits_in_force = next(
        row["count"] for row in readiness["readiness"] if row["key"] == "permits"
    )

    flights_today = FlightRecord.objects.filter(is_active=True, actual_date=today)
    if selected_cost_center:
        flights_today = flights_today.filter(
            permission__cost_center=selected_cost_center
        )

    context = {
        "flights_today": flights_today.count(),
        # El acompañante que la fila pide en la misma frase ("N operaciones hoy ·
        # M permisos vigentes"), y sale de `permit_counts` — la misma función que
        # el informe, para que el panel y el PDF no digan cifras distintas.
        "permits_in_force": permits_in_force,
        "aircraft_count": aircraft_count,
        "operator_count": operator_count,
        "alert_count": alert_count,
        "incomplete_maintenance_count": incomplete_maintenance_count,
        "awaiting_requests": awaiting_requests,
        "awaiting_count": awaiting_count,
        "longest_wait": longest_wait,
        "expirations": expirations,
        "expiring_count": expiring_count,
        "overdue_count": overdue_count,
        "show_onboarding": show_onboarding,
        # LV-206: el estado de los permisos faena por faena, incluidas las que no
        # tienen ninguno — que son las que el usuario quiere ver. Sólo las que
        # vuelan: ver `operates_flights` en `CostCenter`.
        "permit_status_rows": permit_status_by_cost_center(today),
        "chart_data": chart_data,
        "compliance_setup": compliance_setup,
        "compliance_incomplete": compliance_incomplete,
        "cost_centers": cost_centers,
        "selected_cost_center": selected_cost_center,
        "monthly_records": monthly_records,
    }
    context.update(readiness)
    return render(request, "dashboard/index.html", context)
