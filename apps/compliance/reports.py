"""Deterministic compliance KPIs.

Shared by the report views, the `compliance_report` command and the executive
report, so the number a manager reads in a spreadsheet is the same one the
email quotes. No wording or formatting decisions live here.
"""

from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.compliance.digest import HORIZON_DAYS
from apps.compliance.kpis import operational_kpis, permit_counts
from apps.compliance.models import Alert, Document
from apps.registry.models import Aircraft, CostCenter, Operator


# LV-129: cómo se llega al centro de costo desde cada modelo que una alerta
# puede apuntar. Declarado como mapa y no como cadena de `if`s porque el día que
# `WATCHABLE_MODELS` crezca, lo que hay que revisar es esta tabla — y un modelo
# que falte se ve, mientras que un `elif` olvidado no.
#
# `compliance.document` no está acá a propósito: cuelga de una relación genérica
# y su centro de costo se resuelve al revés, con `documents_for_cost_center`,
# que la usa a través de `_subject_scope`.
ALERT_COST_CENTER_PATHS = {
    "registry.aircraft": "cost_center",
    "registry.operator": "cost_center",
    "registry.qualification": "operator__cost_center",
    # LV-158: la prueba de conocimientos es de una persona, así que su faena es
    # la de esa persona -- el mismo camino que la habilitación.
    "registry.knowledgeassessment": "operator__cost_center",
    "operations.flightpermission": "cost_center",
    "maintenance.maintenancerecord": "aircraft__cost_center",
    "compliance.monthlycompliancereview": "cost_center",
    # LV-204: los tres que faltaban, y faltaban contra una lista que ya existía.
    # Pedido del usuario mirando la bandeja: *"la alerta debe mostrar de qué CC
    # pertenece la entidad, en todo tipo de caso"* — la fila de la aeronave
    # llevaba su chip `CC633` y la del documento no llevaba ninguno.
    #
    # `DOCUMENTABLE_MODELS` (`apps/compliance/forms.py`) declara a qué puede
    # colgar un documento, y esta tabla no la seguía: `geoplan` y `flightrequest`
    # los agregó `R10.5` precisamente porque los papeles de una faena llegan
    # **antes** que el permiso, así que son de los más probables en la etapa
    # temprana — y eran justo los que quedaban sin faena. Hay un test que cruza
    # las dos listas para que no vuelva a desalinearse; es el mismo tipo de
    # desalineación que `LV-188` acabó de pagar entre el filtro y la atribución.
    #
    # `"pk"` en el centro de costo no es un truco: la faena de un centro de costo
    # es él mismo, y escribirlo como ruta lo mete por la puerta normal en vez de
    # exigir un caso especial en las dos funciones que recorren esta tabla.
    "registry.costcenter": "pk",
    "geo.geoplan": "cost_center",
    "operations.flightrequest": "cost_center",
}


def _subject_scope(cost_center, *, only_active):
    """`Q` sobre `(content_type, object_id)` para lo atribuible a `cost_center`.

    LV-188: **la única forma de recorrer los modelos con faena declarada.** Antes
    había dos recorridos: `alerts_for_cost_center` iteraba
    `ALERT_COST_CENTER_PATHS` completa y `documents_for_cost_center` mantenía su
    propia lista escrita a mano — `Aircraft` y `Operator`, dos de siete. La
    consecuencia era visible en el panel: un documento colgado de un permiso de
    vuelo salía con el chip de su faena y **desaparecía al filtrar por esa misma
    faena**, porque el chip lo pone `cost_centers_for_refs` (que sí va sobre la
    tabla) y el filtro lo ponía la lista corta. Y no era sólo la pantalla: la
    misma función alimenta el informe de cumplimiento por faena, donde no hay
    filtro de usuario de por medio, así que los documentos que cuelgan de un
    permiso, de un mantenimiento, de una habilitación o de una revisión mensual
    **no contaban en el cumplimiento de ninguna faena**.

    Con subconsulta y no con `list(values_list("pk"))`: una consulta en total en
    vez de una por modelo, y sin traer a Python ids que sólo van a volver a la
    base. Importa acá porque el informe llama a esto **una vez por faena**.

    `only_active` es el criterio de quien pregunta, no una preferencia:
    - los **documentos** se cuentan como trabajo de cumplimiento, así que un
      sujeto archivado no aporta (criterio que ya tenía la lista corta);
    - las **alertas** se atribuyen, no se cuentan: una alerta sobre un registro
      archivado sigue perteneciendo a su faena, igual que en
      `_direct_cost_center_ids`.

    `Q(pk__in=[])` es el neutro del `|`: sin ningún sujeto, el resultado es vacío
    y no "todo".

    ⚠️ Lo que **no** hace, y quedó como `LV-189`: excluir sujetos en estado
    terminal. Una aeronave `retired` sigue `is_active=True`, así que sus
    documentos ya contaban antes de esta fila; extender la tabla suma a esa
    cuenta las cartas de permisos cerrados. Es la regla de `LV-120` y merece su
    propia fila porque cambia números del informe por una razón distinta.
    """
    from django.apps import apps as django_apps

    scope = Q(pk__in=[])
    for label, path in ALERT_COST_CENTER_PATHS.items():
        app_label, model_name = label.split(".", 1)
        try:
            model = django_apps.get_model(app_label, model_name)
        except LookupError:  # pragma: no cover - un modelo retirado del registro
            continue
        # Se filtra por **el pk y no por la instancia**: para una ruta de FK
        # (`cost_center`, `operator__cost_center`) Django acepta las dos, pero
        # `LV-204` agregó `"pk"` como ruta —la faena de un centro de costo es él
        # mismo— y ahí el campo es un `UUIDField`, no una relación: pasarle la
        # instancia hace que intente leer su `__str__` como UUID y levanta
        # `"CC738 - MLP" no es un UUID válido`. El pk sirve para las tres formas.
        subjects = model.objects.filter(**{path: cost_center.pk})
        if only_active:
            subjects = subjects.filter(is_active=True)
        scope |= Q(
            content_type=ContentType.objects.get_for_model(model),
            object_id__in=subjects.values("pk"),
        )
    return scope


def documents_for_cost_center(cost_center, queryset=None):
    """Los documentos que cuelgan de un registro de esta faena.

    `Document` apunta a su sujeto por una relación genérica, así que la faena no
    se alcanza con un join: se emparejan `(content_type, object_id)` contra los
    sujetos de la faena. **Los sujetos posibles son los de
    `ALERT_COST_CENTER_PATHS`** — ver `_subject_scope`, y `LV-188` por qué esta
    función tenía su propia lista de dos.
    """
    base = queryset if queryset is not None else Document.objects.all()
    return base.filter(_subject_scope(cost_center, only_active=True))


def _direct_cost_center_ids(ids_by_content_type):
    """`{(ct_id, pk): cost_center_id}` para los modelos con ruta declarada.

    Una consulta por modelo presente, con `values_list("pk", path)` — que para
    `"operator__cost_center"` devuelve el id del centro de costo sin traer el
    objeto. Sin filtro `is_active`, igual que `alerts_for_cost_center`: una
    alerta sobre un registro archivado sigue perteneciendo a su faena.
    """
    from django.apps import apps as django_apps

    resolved = {}
    for label, path in ALERT_COST_CENTER_PATHS.items():
        app_label, model_name = label.split(".", 1)
        try:
            model = django_apps.get_model(app_label, model_name)
        except LookupError:  # pragma: no cover - un modelo retirado del registro
            continue
        content_type_id = ContentType.objects.get_for_model(model).id
        ids = ids_by_content_type.get(content_type_id)
        if not ids:
            continue
        for pk, cost_center_id in model.objects.filter(pk__in=ids).values_list(
            "pk", path
        ):
            if cost_center_id is not None:
                resolved[(content_type_id, pk)] = cost_center_id
    return resolved


def _group_by_content_type(refs):
    grouped = {}
    for content_type_id, object_id in refs:
        grouped.setdefault(content_type_id, []).append(object_id)
    return grouped


def cost_centers_for_refs(refs):
    """`{(content_type_id, object_id): CostCenter}` para referencias genéricas.

    LV-146: la inversa de `alerts_for_cost_center`. Esa acota un queryset a una
    faena; ésta dice a qué faena pertenece cada fila, que es lo que la bandeja
    de alertas y los vencimientos del panel necesitan para **mostrarlo**.

    Va sobre la **misma** `ALERT_COST_CENTER_PATHS`, así que la columna nueva y
    el filtro que ya existe no pueden discrepar por construcción — y el día que
    `WATCHABLE_MODELS` crezca hay un solo lugar que revisar.

    `refs` es un iterable de `(content_type_id, object_id)`: sirve tanto para
    una página de alertas como para una lista de documentos.

    Coste: una consulta por modelo presente, más una por los documentos y su
    segunda vuelta, más una por los centros de costo. **Nunca una por fila.**

    El caso `Document` se resuelve en dos pasos y no con recursión: el sujeto de
    un documento es una aeronave, un operador o un centro de costo, nunca otro
    documento, así que la terminación es estructural y no una suposición.

    Devuelve la clave **sólo cuando hay faena resuelta**, así `mapa.get(ref) is
    None` cubre los tres casos de "sin faena" con una sola rama en la plantilla:
    modelo sin ruta declarada, FK nula (la de `Aircraft` y `Operator` lo es), y
    documento de empresa.
    """
    refs = list(refs)
    if not refs:
        return {}
    resolved = _direct_cost_center_ids(_group_by_content_type(refs))

    document_ct = ContentType.objects.get_for_model(Document).id
    document_ids = _group_by_content_type(refs).get(document_ct)
    if document_ids:
        subjects = {}
        for pk, subject_ct, subject_id in Document.objects.filter(
            pk__in=document_ids
        ).values_list("pk", "content_type_id", "object_id"):
            subjects.setdefault((subject_ct, subject_id), []).append(pk)
        subject_cost_centers = _direct_cost_center_ids(
            _group_by_content_type(subjects.keys())
        )
        for subject_ref, document_pks in subjects.items():
            cost_center_id = subject_cost_centers.get(subject_ref)
            if cost_center_id is None:
                continue
            for pk in document_pks:
                resolved[(document_ct, pk)] = cost_center_id

    cost_centers = CostCenter.objects.in_bulk(set(resolved.values()))
    return {
        ref: cost_centers[cost_center_id]
        for ref, cost_center_id in resolved.items()
        if cost_center_id in cost_centers
    }


def document_subjects(documents):
    """`{pk del documento: de qué cuelga, en palabras}`. LV-186.

    Pedido del usuario mirando los vencimientos del panel: una fila decía
    *"Documento · Carta Permiso"* y nada más. El título de un documento no dice
    **de cuál** es — hay una carta por permiso— así que la fila obligaba a abrir
    para saber a qué se refiere, que es justo lo que una lista de vencimientos
    existe para evitar.

    Las otras cuatro fuentes no tienen este problema porque su etiqueta **es**
    el sujeto: la matrícula para un seguro, el nombre para una credencial. El
    documento es el único que cuelga de otra cosa.

    Una consulta por tipo de sujeto presente y **ninguna por fila**, la misma
    disciplina que `cost_centers_for_refs`: esto se dibuja en el panel, que se
    abre en cada inicio de sesión.

    Devuelve la clave **sólo cuando el sujeto existe**, así una entrada ausente
    cubre de una sola forma los dos casos honestos: el documento de empresa, que
    cuelga del tenant y no de un registro, y el sujeto borrado.
    """
    documents = list(documents)
    if not documents:
        return {}
    by_type = {}
    for document in documents:
        by_type.setdefault(document.content_type_id, {}).setdefault(
            str(document.object_id), []
        ).append(document.pk)

    labels = {}
    for content_type_id, ids in by_type.items():
        content_type = ContentType.objects.get_for_id(content_type_id)
        model = content_type.model_class()
        if model is None:
            continue
        for subject in model._default_manager.filter(pk__in=list(ids)):
            for pk in ids.get(str(subject.pk), []):
                labels[pk] = str(subject)
    return labels


def alerts_for_cost_center(queryset, cost_center):
    """Acotar alertas a un centro de costo, resolviendo la GenericForeignKey.

    LV-129: la tarjeta "Alertas pendientes" del panel **ignoraba el filtro por
    centro de costo**. Elegir una faena cambiaba todas las tarjetas menos ésa,
    porque la consulta contaba las alertas de toda la operación — un número
    ajeno al filtro, presentado junto a otros que sí lo respetan.

    Mismo problema y misma forma que `documents_for_cost_center`: no hay join
    posible hacia el sujeto, así que se emparejan `(content_type, object_id)`
    contra los sujetos de la faena. **Las dos van por `_subject_scope`** desde
    `LV-188`, que es lo que impide que vuelvan a discrepar en qué modelos
    conocen.

    Un modelo sin ruta declarada **queda fuera** cuando hay filtro. Es la
    lectura honesta: si no se puede atribuir a una faena, no es de esa faena.
    Sin filtro no se toca nada.

    Acá los sujetos archivados **entran**: una alerta sobre un registro
    archivado sigue perteneciendo a su faena, y esconderla del filtro la
    escondería de la única pantalla donde alguien la cerraría.
    """
    if cost_center is None:
        return queryset

    scope = _subject_scope(cost_center, only_active=False)

    documents = documents_for_cost_center(
        cost_center, Document.objects.filter(is_active=True)
    )
    scope |= Q(
        content_type=ContentType.objects.get_for_model(Document),
        object_id__in=documents.values("pk"),
    )
    return queryset.filter(scope)


def _cost_center_row(cost_center, doc_type, today):
    documents = documents_for_cost_center(
        cost_center,
        Document.objects.filter(is_active=True, is_current_version=True),
    )
    if doc_type:
        documents = documents.filter(doc_type=doc_type)

    # One aggregate instead of iterating every document in Python: the loop
    # loaded the cost center's whole document table per row, which turns the
    # report from instant to seconds within a few years of accumulation.
    boundaries = {
        "due_7": today + timedelta(days=7),
        "due_15": today + timedelta(days=15),
        "due_30": today + timedelta(days=30),
    }
    counted = documents.aggregate(
        total=Count("pk"),
        expired=Count("pk", filter=Q(expiry_date__lt=today)),
        due_7=Count(
            "pk", filter=Q(expiry_date__gte=today, expiry_date__lte=boundaries["due_7"])
        ),
        due_15=Count(
            "pk",
            filter=Q(
                expiry_date__gt=boundaries["due_7"],
                expiry_date__lte=boundaries["due_15"],
            ),
        ),
        due_30=Count(
            "pk",
            filter=Q(
                expiry_date__gt=boundaries["due_15"],
                expiry_date__lte=boundaries["due_30"],
            ),
        ),
    )
    counters = {key: counted[key] for key in ("expired", "due_7", "due_15", "due_30")}
    total = counted["total"]

    # LV-49: DGAC vigencias (Operator.credential_expiry, Aircraft.insurance_expiry)
    # already drive real alerts (LV-29's "Credenciales DGAC"/"Seguros JAC" rules)
    # but were never reflected here, so this report read 0/0.0% for every cost
    # center while the alert list showed real open items for the same data.
    # Only merged in when no doc_type filter narrows the view: vigencias are
    # not Document rows and have no doc_type, so a type-filtered report should
    # not silently pull them back in.
    if doc_type is None:
        for model, field in (
            (Operator, "credential_expiry"),
            (Aircraft, "insurance_expiry"),
        ):
            vigencias = _vigencia_bucket_counts(
                model.objects.filter(cost_center=cost_center, is_active=True),
                field,
                today,
                boundaries,
            )
            total += vigencias["total"]
            for key in ("expired", "due_7", "due_15", "due_30"):
                counters[key] += vigencias[key]

    valid = total - counters["expired"]
    return {
        "code": cost_center.code,
        "name": cost_center.name,
        "total": total,
        "valid": valid,
        "valid_pct": round(valid * 100 / total, 1) if total else 0.0,
        "expired": counters["expired"],
        "due_7": counters["due_7"],
        "due_15": counters["due_15"],
        "due_30": counters["due_30"],
    }


def _vigencia_bucket_counts(queryset, date_field, today, boundaries):
    """Expired/due-soon counters for a DGAC vigencia field.

    Unlike Document.expiry_date -- where null means "this document type never
    expires" and the row still counts as valid -- a null vigencia means the
    value was never entered in the fiche. Those rows are excluded entirely
    rather than counted as valid, matching how generate_alerts already treats
    these same fields (LV-29: only aircraft/operators with a value set are
    watched).
    """
    present = queryset.filter(**{f"{date_field}__isnull": False})
    return present.aggregate(
        total=Count("pk"),
        expired=Count("pk", filter=Q(**{f"{date_field}__lt": today})),
        due_7=Count(
            "pk",
            filter=Q(
                **{
                    f"{date_field}__gte": today,
                    f"{date_field}__lte": boundaries["due_7"],
                }
            ),
        ),
        due_15=Count(
            "pk",
            filter=Q(
                **{
                    f"{date_field}__gt": boundaries["due_7"],
                    f"{date_field}__lte": boundaries["due_15"],
                }
            ),
        ),
        due_30=Count(
            "pk",
            filter=Q(
                **{
                    f"{date_field}__gt": boundaries["due_15"],
                    f"{date_field}__lte": boundaries["due_30"],
                }
            ),
        ),
    )


# Oldest-first cap on the open-alert list. The report is a status overview,
# not the alert queue: past this size the marginal row adds nothing the
# alert list page does not show better.
OPEN_ALERTS_LIMIT = 200


def _open_alerts(cost_center, today):
    alerts = list(
        Alert.objects.filter(is_active=True, is_resolved=False)
        .select_related("alert_rule", "content_type")
        .order_by("triggered_at")[:OPEN_ALERTS_LIMIT]
    )
    # str(alert.content_object) resolved each watched entity with its own
    # query - one per open alert, unbounded. Fetch them grouped by type
    # instead: one query per distinct content type.
    by_type = {}
    for alert in alerts:
        by_type.setdefault(alert.content_type, set()).add(alert.object_id)
    entities = {}
    for content_type, ids in by_type.items():
        model = content_type.model_class()
        if model is None:
            continue
        for obj in model._default_manager.filter(pk__in=ids):
            entities[(content_type.pk, obj.pk)] = obj

    rows = []
    for alert in alerts:
        entity = entities.get((alert.content_type_id, alert.object_id))
        # The received cost_center filter used to be accepted and ignored, so
        # a filtered report still listed every cost center's alerts.
        if cost_center is not None and entity is not None:
            entity_center = getattr(entity, "cost_center_id", None)
            if entity_center is None:
                operator = getattr(entity, "operator", None)
                entity_center = getattr(operator, "cost_center_id", None)
            if entity_center is not None and entity_center != cost_center.pk:
                continue
        rows.append(
            {
                "entity": str(entity or "—"),
                "entity_type": alert.entity_label,
                "rule": alert.alert_rule.name,
                "triggered_at": alert.triggered_at.date(),
                "age_days": (today - alert.triggered_at.date()).days,
            }
        )
    return rows


def _resolution_stats(start, end):
    """Average alert -> resolution time for alerts resolved in the period."""
    resolved = Alert.objects.filter(
        is_active=True,
        is_resolved=True,
        resolved_at__date__gte=start,
        resolved_at__date__lte=end,
    ).only("triggered_at", "resolved_at")
    days = [
        (alert.resolved_at - alert.triggered_at).total_seconds() / 86400
        for alert in resolved
    ]
    return {
        "resolved_count": len(days),
        "avg_days": round(sum(days) / len(days), 1) if days else None,
    }


def build_compliance_report(start=None, end=None, cost_center=None, doc_type=None):
    """Return the KPI structure for a period.

    `start`/`end` bound the resolution statistics; the expiry counters are
    always relative to today, because "expiring in 7 days" only means anything
    from now.
    """
    # `timezone.localdate()`, not `date.today()`: `_resolution_stats` filters
    # `resolved_at__date`, which the database evaluates in the project timezone.
    # A naive OS date disagrees with it whenever the two differ — with
    # TIME_ZONE="UTC" and an operator west of Greenwich, that is every evening,
    # and alerts resolved in those hours dropped out of the period silently.
    today = timezone.localdate()
    end = end or today
    start = start or (end - timedelta(days=30))

    centers = CostCenter.objects.filter(is_active=True).order_by("code")
    if cost_center:
        centers = centers.filter(pk=cost_center.pk)

    rows = [_cost_center_row(center, doc_type, today) for center in centers]
    totals = {
        key: sum(row[key] for row in rows)
        for key in ("total", "valid", "expired", "due_7", "due_15", "due_30")
    }
    totals["valid_pct"] = (
        round(totals["valid"] * 100 / totals["total"], 1) if totals["total"] else 0.0
    )

    return {
        "generated_on": today,
        "period": {"start": start, "end": end},
        "horizon_days": HORIZON_DAYS,
        "filters": {
            "cost_center": cost_center.code if cost_center else None,
            "doc_type": doc_type.name if doc_type else None,
        },
        "by_cost_center": rows,
        "totals": totals,
        "open_alerts": _open_alerts(cost_center, today),
        "resolution": _resolution_stats(start, end),
        # LV-8f: maintenance still needing planning is an open compliance gap.
        "incomplete_maintenance": _incomplete_maintenance_count(cost_center),
        # R7.7: the two operational KPIs derivable without Deliverable (R7.4)
        # or NonConformity (R7.6). Fleet-wide on purpose -- availability is a
        # property of the fleet, not of a cost center's slice of it.
        "operational_kpis": operational_kpis(start, end),
        # LV-201: los permisos vigentes, atrasados y esperando a la DGAC, con la
        # **misma función que dibuja el panel** (`kpis.permit_counts`). El pedido
        # del usuario nombraba las dos pantallas, y dos cálculos separados de la
        # misma cifra es cómo el informe que alguien imprime y el panel que otro
        # mira dejan de coincidir. A diferencia de `operational_kpis`, éste **sí**
        # respeta el filtro por faena: un permiso pertenece a una, y la pregunta
        # "cuántos tengo vigentes" se hace por faena.
        "permits": permit_counts(today, cost_center),
    }


def latest_snapshot_before(day, cost_center=None):
    """R7.7: the most recent `ComplianceSnapshot` strictly before `day`.

    `None` when no history has been recorded yet -- a fresh install, or one
    where `snapshot_compliance` has never run. Callers must degrade instead of
    failing: an empty history is the normal state on day one.
    """
    from .models import ComplianceSnapshot

    return (
        ComplianceSnapshot.objects.filter(
            date__lt=day, cost_center=cost_center, is_active=True
        )
        .order_by("-date")
        .first()
    )


def totals_from_snapshot(snapshot):
    """A stored snapshot in the same shape as `report["totals"]`, so it can
    stand in for a recomputed "previous period" without the comparison code
    needing to know where the numbers came from."""
    return {
        "total": snapshot.total,
        "valid": snapshot.valid,
        "expired": snapshot.expired,
        "due_7": snapshot.due_7,
        "due_15": snapshot.due_15,
        "due_30": snapshot.due_30,
        "valid_pct": snapshot.valid_pct,
    }


def previous_period(start, end):
    """The period of equal length immediately before [start, end] -- what
    "compared with last period" means throughout the executive report."""
    length = (end - start).days
    previous_end = start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=length)
    return previous_start, previous_end


# R6.4: shared by the executive email (send_executive_report) and the web
# report page, so both read the same comparison instead of the web page
# showing the raw counters while only the inbox says whether they are
# getting better or worse. "lower_is_better" decides whether a rise reads as
# an improvement or a regression, so the wording never contradicts the number.
COMPARED_KPIS = [
    ("valid_pct", _("Valid documents (%)"), False),
    ("expired", _("Expired documents"), True),
    ("due_30", _("Expiring within 30 days"), True),
]


def compare_periods(current, previous):
    """Each COMPARED_KPIS totals entry, current vs. previous, plus alert
    resolution counts (always reported "flat" -- more resolutions is not
    unambiguously better or worse, unlike a lower expired count)."""
    comparison = []
    for key, label, lower_is_better in COMPARED_KPIS:
        now = current["totals"][key]
        before = previous["totals"][key]
        delta = round(now - before, 1)
        if delta == 0:
            direction = "flat"
        elif (delta < 0) == lower_is_better:
            direction = "better"
        else:
            direction = "worse"
        comparison.append(
            {
                "label": label,
                "current": now,
                "previous": before,
                "delta": delta,
                "direction": direction,
            }
        )
    comparison.append(
        {
            "label": _("Alerts resolved in the period"),
            "current": current["resolution"]["resolved_count"],
            "previous": previous["resolution"]["resolved_count"],
            "delta": (
                current["resolution"]["resolved_count"]
                - previous["resolution"]["resolved_count"]
            ),
            "direction": "flat",
        }
    )
    return comparison


def _incomplete_maintenance_count(cost_center):
    """LV-8e/8f: maintenance flagged 'to be defined' or missing a scheduled
    date, and not yet completed. A cross-app read, scoped by cost center via
    the aircraft when one is selected."""
    from apps.maintenance.models import MaintenanceRecord

    queryset = MaintenanceRecord.objects.filter(
        is_active=True, status__in=["pending", "in_progress"]
    ).filter(Q(maintenance_type="to_be_defined") | Q(scheduled_date__isnull=True))
    if cost_center is not None:
        queryset = queryset.filter(aircraft__cost_center=cost_center)
    return queryset.count()


COST_CENTER_HEADERS = [
    "Centro de costo",
    "Nombre",
    "Documentos",
    "Vigentes",
    "% vigentes",
    "Vencidos",
    "Vence <=7d",
    "Vence <=15d",
    "Vence <=30d",
]

ALERT_HEADERS = ["Entidad", "Tipo", "Regla", "Detectada", "Antigüedad (días)"]


def cost_center_rows(report):
    return [
        [
            row["code"],
            row["name"],
            row["total"],
            row["valid"],
            row["valid_pct"],
            row["expired"],
            row["due_7"],
            row["due_15"],
            row["due_30"],
        ]
        for row in report["by_cost_center"]
    ]


def alert_rows(report):
    return [
        [
            alert["entity"],
            alert["entity_type"],
            alert["rule"],
            alert["triggered_at"],
            alert["age_days"],
        ]
        for alert in report["open_alerts"]
    ]
