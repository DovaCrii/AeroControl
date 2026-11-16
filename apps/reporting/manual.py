"""LV-445: la sección 5 del informe mensual, «Cumplimiento del Manual (Act. 19)».

El Manual de Operaciones AOC N° 1485, Actualización N° 19 (aprobada por la DGAC el
2026-11-10), reemplaza los registros de misión y agrega otros. El informe mensual
deja de ser exigencia del Manual y pasa a ser control interno (INS-096), pero sigue
siendo **la** pieza donde la gerencia ve si lo que el Manual pide se está cumpliendo.

**Sólo lee el dominio**, como el resto de `apps.reporting`: cuenta lo que ya existe y
lo congela en el payload (`payload["manual"]`). Si el corte es anterior a la vigencia
la función devuelve `None` y **el payload no lleva la llave**: los informes de octubre
y anteriores no cambian ni un byte (el mismo mecanismo de `meta.early_cutoff`).

⚠️ **La regla que manda: sin dato es «Pendiente», nunca 0.** Un tipo de documento que
no existe todavía en la base (el LV-442 no se desplegó, o alguien lo borró) deja la
hoja en `None`, y la plantilla la dibuja ámbar punteada. «Cero REG-016» y «no sé
cuántos REG-016 hay» son afirmaciones distintas, y sólo la primera es un número.

Constantes con nombre y su fuente (Manual, Anexo B): REG-016 se carga «en un plazo no
mayor a 24 horas desde que se realizó el trabajo aéreo». La hora del vuelo no está en
el documento, así que «24 h» se mide en **días**: cargado a más tardar el día
siguiente a la misión. Se declara en el pie de la hoja.
"""

from datetime import date

from django.utils import timezone

from apps.reporting.builder import leaf, month_bounds

#: Aprobación de la DGAC: desde acá se mide. Antes de este día no hay sección.
ACT19_EFFECTIVE = date(2026, 11, 10)
ACT19_EDITION = {"code": "Act. 19", "approved_on": ACT19_EFFECTIVE.isoformat()}
#: «24 h» medido en días: cargado a más tardar el día siguiente al trabajo aéreo.
ON_TIME_DAYS = 1
#: Los tipos de documento que la sección cuenta (LV-442). Por código, no por nombre.
TYPE_CODES = {
    "mission": "flight-log",  # REG-016 Rev. 2
    "inspection": "drone-inspection",  # LVE-002 Rev. 1 (de la aeronave, vence)
    "reg018": "operator-qualification-intake",
    "reg019": "operator-theory-evaluations",
    "reg020": "rpa-service-life",
}


def collect_manual(period, cutoff, centres, early=False):
    """La sección completa, o `None` si el corte es anterior a la vigencia."""
    if cutoff < ACT19_EFFECTIVE:
        return None
    start, _end = month_bounds(period)
    window = (max(start, ACT19_EFFECTIVE), cutoff)
    type_ids = _type_ids()
    fleet = _fleet(cutoff)
    roster = _roster(cutoff)
    return {
        "edition": dict(ACT19_EDITION),
        "window": {"from": window[0].isoformat(), "to": cutoff.isoformat()},
        "missions": collect_mission_records(
            period, window, centres, type_ids["mission"], early
        ),
        "inspections": collect_inspections(
            fleet, cutoff, type_ids["inspection"], type_ids["reg020"], early
        ),
        "evaluations": collect_evaluations(
            roster, cutoff, type_ids["reg018"], type_ids["reg019"], early
        ),
        "maintenance": collect_maintenance(window, cutoff),
    }


def _type_ids():
    """`{clave: pk o None}`. **Sin filtrar `is_active`**: un tipo archivado existe."""
    from apps.compliance.models import DocumentType

    found = dict(
        DocumentType.objects.filter(code__in=TYPE_CODES.values()).values_list(
            "code", "pk"
        )
    )
    return {key: found.get(code) for key, code in TYPE_CODES.items()}


def _fleet(cutoff):
    """La flota al corte: `[(pk, matrícula)]`, el universo de `panel_readiness`."""
    from apps.registry.selectors import operational_fleet

    return list(
        operational_fleet()
        .filter(created_at__date__lte=cutoff)
        .order_by("registration")
        .values_list("pk", "registration")
    )


def _roster(cutoff):
    """El padrón al corte: `[pk]` de operadores."""
    from apps.registry.selectors import operational_roster

    return list(
        operational_roster(cutoff)
        .filter(created_at__date__lte=cutoff)
        .values_list("pk", flat=True)
    )


def _documents(content_model, ids, type_ids, cutoff, early):
    """Documentos vigentes de esos sujetos y tipos, una sola consulta."""
    from django.contrib.contenttypes.models import ContentType

    from apps.compliance.models import Document

    queryset = Document.objects.filter(
        is_active=True,
        is_current_version=True,
        content_type=ContentType.objects.get_for_model(content_model),
        object_id__in=ids,
        doc_type_id__in=[pk for pk in type_ids if pk is not None],
    )
    if early:
        # «Lo cargado después de congelar no se cuenta»: en un corte anticipado el
        # documento creado después del corte todavía no existía.
        queryset = queryset.filter(created_at__date__lte=cutoff)
    return queryset


# -- REG-016 por centro de costo ---------------------------------------------------


def _classify(issue_date, created_at, source_reference):
    """`on_time`, `late` o `not_assessable` para un REG-016.

    Sin fecha de misión, o importado en lote (su `created_at` es la fecha de la
    importación, no la de carga real), no se puede medir el plazo: **sin evaluar**,
    nunca «a tiempo» ni «fuera de plazo».
    """
    if issue_date is None or source_reference:
        return "not_assessable"
    loaded = timezone.localtime(created_at).date()
    return "on_time" if (loaded - issue_date).days <= ON_TIME_DAYS else "late"


def _reviewed_within_24h(centre_ids, window, cutoff, early):
    """REG-016 revisados dentro del plazo, o `None` si no hay revisiones que medir.

    Una revisión cuenta por su fecha de misión (la ventana del informe). En un corte
    anticipado lo revisado después del corte todavía no estaba revisado. Una sola
    consulta: el total decide entre «Pendiente» (ninguna revisión abierta) y un número.
    """
    from django.db.models import Count, F, Q

    from apps.compliance.models import MissionReview

    on_time = Q(
        status__in=MissionReview.TERMINAL_STATUSES,
        reviewed_at__date__lte=F("due_on"),
    )
    if early:
        on_time &= Q(reviewed_at__date__lte=cutoff)
    totals = MissionReview.objects.filter(
        is_active=True, cost_center_id__in=centre_ids, mission_date__range=window
    ).aggregate(total=Count("pk"), on_time=Count("pk", filter=on_time))
    return totals["on_time"] if totals["total"] else None


def collect_mission_records(period, window, centres, type_id, early):
    from django.contrib.contenttypes.models import ContentType
    from apps.compliance.models import Document, MonthlyComplianceReview
    from apps.compliance.monthly import filed_on
    from apps.operations.models import FlightRecord
    from apps.registry.models import CostCenter

    cutoff = window[1]
    ids = [centre.pk for centre in centres]
    centre_ids = set(ids)

    def kpi(value):
        return leaf(value, "compliance", cutoff)

    # Misiones voladas: pares (faena, día) distintos de la bitácora digital. Si la
    # bitácora no se usa no hay ninguna fila, y «cero vuelos cargados» no es «cero
    # misiones»: queda pendiente.
    missions = set(
        FlightRecord.objects.filter(
            is_active=True,
            aircraft__cost_center_id__in=ids,
            actual_date__range=window,
        )
        .values_list("aircraft__cost_center_id", "actual_date")
        .distinct()
    )

    reviews = dict(
        MonthlyComplianceReview.objects.filter(
            is_active=True, cost_center_id__in=ids, period=month_bounds(period)[0]
        ).values_list("cost_center_id", "status")
    )

    counts = {pk: {"on_time": 0, "late": 0, "not_assessable": 0} for pk in ids}
    filed = set()
    if type_id is not None:
        documents = Document.objects.annotate(filed_on=filed_on()).filter(
            is_active=True,
            is_current_version=True,
            doc_type_id=type_id,
            content_type=ContentType.objects.get_for_model(CostCenter),
            object_id__in=ids,
            filed_on__range=window,
        )
        if early:
            documents = documents.filter(created_at__date__lte=cutoff)
        for object_id, issue_date, created_at, source, day in documents.values_list(
            "object_id", "issue_date", "created_at", "source_reference", "filed_on"
        ):
            if object_id not in centre_ids:  # pragma: no cover - filtrado arriba
                continue
            counts[object_id][_classify(issue_date, created_at, source)] += 1
            filed.add((object_id, day))

    rows = []
    for centre in centres:
        own = counts[centre.pk]
        rows.append(
            {
                "code": centre.code,
                "name": centre.name,
                "records": (sum(own.values()) if type_id is not None else None),
                "on_time": own["on_time"] if type_id is not None else None,
                "late": own["late"] if type_id is not None else None,
                "not_assessable": (
                    own["not_assessable"] if type_id is not None else None
                ),
                "review": reviews.get(centre.pk),
            }
        )

    def total(key):
        if type_id is None:
            return kpi(None)
        return kpi(sum(own[key] for own in counts.values()))

    records_total = (
        kpi(sum(sum(own.values()) for own in counts.values()))
        if type_id is not None
        else kpi(None)
    )
    kpis = {
        "records_total": records_total,
        "records_on_time": total("on_time"),
        "records_late": total("late"),
        # Los que se pueden medir contra el plazo: el denominador de «en plazo».
        "records_assessable": (
            kpi(sum(own["on_time"] + own["late"] for own in counts.values()))
            if type_id is not None
            else kpi(None)
        ),
        "records_not_assessable": total("not_assessable"),
        "centres_with_records": kpi(
            sum(1 for own in counts.values() if sum(own.values()))
            if type_id is not None
            else None
        ),
        "centres_operating": kpi(len(centres)),
        "missions_flown": kpi(len(missions) if missions else None),
        "missions_without_record": kpi(
            sum(1 for pair in missions if pair not in filed)
            if missions and type_id is not None
            else None
        ),
        # El REG-016 se revisa dentro de 24 h (LV-447): las revisadas a más tardar el
        # día del plazo. Sin ninguna revisión abierta en la ventana no hay dato:
        # Pendiente, no cero. Sólo se recalcula al construir un informe nuevo.
        "reviewed_within_24h": kpi(_reviewed_within_24h(ids, window, cutoff, early)),
    }
    return {"rows": rows, "kpis": kpis}


# -- LVE-002 por aeronave ----------------------------------------------------------


def collect_inspections(fleet, cutoff, inspection_id, reg020_id, early):
    from apps.registry.models import Aircraft

    def kpi(value):
        return leaf(value, "compliance", cutoff)

    ids = [pk for pk, _registration in fleet]
    docs = {}
    if ids and (inspection_id is not None or reg020_id is not None):
        for object_id, type_pk, expiry in _documents(
            Aircraft, ids, (inspection_id, reg020_id), cutoff, early
        ).values_list("object_id", "doc_type_id", "expiry_date"):
            docs.setdefault((object_id, type_pk), []).append(expiry)

    states = {"in_force": 0, "lapsed": 0, "undated": 0, "missing": 0}
    gaps = []
    if inspection_id is not None:
        for pk, registration in fleet:
            expiries = docs.get((pk, inspection_id))
            if not expiries:
                state = "missing"
            else:
                dated = [day for day in expiries if day is not None]
                if not dated:
                    state = "undated"
                else:
                    state = "in_force" if max(dated) >= cutoff else "lapsed"
            states[state] += 1
            if state != "in_force":
                gaps.append(registration)

    if reg020_id is None:
        reg020 = kpi(None)
    else:
        reg020 = kpi(
            sum(
                1
                for pk, _registration in fleet
                if any(
                    day is None or day >= cutoff
                    for day in docs.get((pk, reg020_id), [])
                )
            )
        )
    known = inspection_id is not None
    return {
        "kpis": {
            "fleet": leaf(len(fleet), "registry", cutoff),
            "in_force": kpi(states["in_force"] if known else None),
            "lapsed": kpi(states["lapsed"] if known else None),
            "undated": kpi(states["undated"] if known else None),
            "missing": kpi(states["missing"] if known else None),
            "reg020_aircraft": reg020,
        },
        "gaps": sorted(gaps),
    }


# -- Evaluaciones teóricas y registros de operadores --------------------------------


def collect_evaluations(roster, cutoff, reg018_id, reg019_id, early):
    from apps.registry.models import KnowledgeAssessment, Operator

    def kpi(value):
        return leaf(value, "registry", cutoff)

    # Semántica LV-439: vigente es el último intento **aprobado** al corte; un
    # reprobado posterior no lo anula.
    attempts = {}
    if roster:
        for (
            operator_id,
            passed,
            expires_on,
            taken_at,
        ) in KnowledgeAssessment.objects.filter(
            is_active=True, operator_id__in=roster
        ).values_list("operator_id", "passed", "expires_on", "taken_at"):
            if timezone.localtime(taken_at).date() > cutoff:
                continue
            attempts.setdefault(operator_id, []).append((taken_at, passed, expires_on))
    counts = {"in_force": 0, "lapsed": 0, "failed_only": 0, "never": 0}
    for operator_id in roster:
        own = attempts.get(operator_id, [])
        passed = sorted((a for a in own if a[1]), key=lambda a: a[0])
        if passed:
            counts["in_force" if passed[-1][2] >= cutoff else "lapsed"] += 1
        elif own:
            counts["failed_only"] += 1
        else:
            counts["never"] += 1

    held = {}
    wanted = (reg018_id, reg019_id)
    if roster and any(pk is not None for pk in wanted):
        for object_id, type_pk, expiry in _documents(
            Operator, roster, wanted, cutoff, early
        ).values_list("object_id", "doc_type_id", "expiry_date"):
            if expiry is None or expiry >= cutoff:
                held.setdefault(type_pk, set()).add(object_id)

    def with_record(type_pk):
        return kpi(None if type_pk is None else len(held.get(type_pk, ())))

    return {
        # Hasta que la Act. 19 traiga su evaluación por tipo (bloque B6) la hoja
        # rotula la prueba interna previa: es honesto sobre qué se está contando.
        "format": "lv158",
        "kpis": {
            "roster": kpi(len(roster)),
            "in_force": kpi(counts["in_force"]),
            "lapsed": kpi(counts["lapsed"]),
            "failed_only": kpi(counts["failed_only"]),
            "never": kpi(counts["never"]),
            "reg018_operators": with_record(reg018_id),
            "reg019_operators": with_record(reg019_id),
        },
    }


# -- Mantenciones ------------------------------------------------------------------


def collect_maintenance(window, cutoff):
    from django.db.models import Count, Q

    from apps.maintenance.models import MaintenanceRecord

    # `is_active=True` es el mismo criterio que `MaintenanceRecordList`: un registro
    # anulado queda archivado y no sale de la lista ni de acá.
    counted = MaintenanceRecord.objects.filter(is_active=True).aggregate(
        completed=Count("pk", filter=Q(completed_date__range=window)),
        open=Count(
            "pk",
            filter=Q(created_at__date__lte=cutoff)
            & (Q(completed_date__isnull=True) | Q(completed_date__gt=cutoff)),
        ),
    )
    return {
        "kpis": {
            "completed_in_window": leaf(counted["completed"], "maintenance", cutoff),
            "open_at_cutoff": leaf(counted["open"], "maintenance", cutoff),
            # La mantención por niveles (200 h/6 m · 400 h/12 m · 600 h/18 m) la
            # conectará el bloque B8; hasta entonces es pendiente, no cero.
            "due_by_level": leaf(None, "maintenance", cutoff),
        }
    }
