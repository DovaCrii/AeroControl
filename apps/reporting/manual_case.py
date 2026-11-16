"""LV-445: el caso ficticio de la sección 5 (Manual, Act. 19), para sus tests.

**No es un test** (el nombre no empieza por `test_`). Códigos `CC9xx` y matrículas
`RPA-9xxx`, nombres genéricos: nada es dato real. Período noviembre de 2026, que es el
primero que mide la Act. 19 (desde el 10-11).
"""

from datetime import date, datetime, time, timezone as dt_timezone

from django.contrib.contenttypes.models import ContentType

from apps.compliance.models import Document, DocumentType
from apps.registry.models import Aircraft, CostCenter, KnowledgeAssessment, Operator

PERIOD = date(2026, 11, 1)
CUTOFF = date(2026, 11, 30)
BORN = datetime(2026, 10, 1, 12, 0, tzinfo=dt_timezone.utc)

TYPES = {
    "flight-log": "REG-016",
    "drone-inspection": "LVE-002",
    "operator-qualification-intake": "REG-018",
    "operator-theory-evaluations": "REG-019",
    "rpa-service-life": "REG-020",
}


def doc_types():
    """Los cinco tipos que la sección cuenta, creados si faltan."""
    return {
        code: DocumentType.objects.get_or_create(
            code=code, defaults={"name": f"{label} (prueba)"}
        )[0]
        for code, label in TYPES.items()
    }


def born(obj, moment=BORN):
    """`created_at` es `auto_now_add`: se fija para que el corte lo cuente."""
    type(obj).objects.filter(pk=obj.pk).update(created_at=moment)
    obj.refresh_from_db()
    return obj


def centre(code="CC901"):
    return CostCenter.objects.create(
        code=code, name=f"Faena {code}", operates_flights=True
    )


def aircraft(registration, site):
    return born(
        Aircraft.objects.create(
            registration=registration,
            type="RPA",
            model="Modelo ficticio",
            manufacturer="Fabricante ficticio",
            cost_center=site,
        )
    )


def operator(code, site):
    return born(
        Operator.objects.create(
            employee_id=code, full_name=f"Persona {code}", cost_center=site
        )
    )


def document(
    kind,
    subject,
    *,
    issue=None,
    expiry=None,
    loaded=None,
    source="",
    current=True,
):
    """Un documento de `kind` colgado de `subject`, cargado en el instante `loaded`."""
    doc = Document.objects.create(
        content_type=ContentType.objects.get_for_model(type(subject)),
        object_id=subject.pk,
        doc_type=kind,
        title="Documento ficticio",
        file_path="x.pdf",
        issue_date=issue,
        expiry_date=expiry,
        source_reference=source,
        is_current_version=current,
    )
    if loaded is not None:
        Document.objects.filter(pk=doc.pk).update(created_at=loaded)
    return doc


def at(day, hour=15):
    """Un instante UTC del día `day` (a las 15:00 UTC cae el mismo día en Chile)."""
    return datetime.combine(day, time(hour), tzinfo=dt_timezone.utc)


def assessment(person, *, passed, taken, expires):
    """Un intento de la prueba interna de conocimientos, con fecha de rendición."""
    row = KnowledgeAssessment.objects.create(
        operator=person,
        question_count=25,
        correct_count=25 if passed else 5,
        score_percent=100 if passed else 20,
        passed=passed,
        expires_on=expires,
    )
    KnowledgeAssessment.objects.filter(pk=row.pk).update(taken_at=at(taken))
    return row


def make_manual_case(centres=3, aircraft_count=3):
    """El caso del snapshot: faenas con REG-016 en plazo, tarde y en lote, una
    aeronave por estado de LVE-002, dos operadores con su prueba, y sin bitácora
    digital (así las misiones salen «Pendiente»)."""
    from apps.compliance.models import MonthlyComplianceReview

    kinds = doc_types()
    sites = [centre(f"CC90{n}") for n in range(1, centres + 1)]
    log = kinds["flight-log"]
    first = sites[0]
    document(log, first, issue=date(2026, 11, 12), loaded=at(date(2026, 11, 12)))
    document(log, first, issue=date(2026, 11, 13), loaded=at(date(2026, 11, 14)))
    document(log, first, issue=date(2026, 11, 16), loaded=at(date(2026, 11, 20)))
    document(
        log,
        first,
        issue=date(2026, 11, 18),
        loaded=at(date(2026, 11, 28)),
        source="Z:/ficticio/lote.pdf",
    )
    if centres > 1:
        document(log, sites[1], issue=date(2026, 11, 19), loaded=at(date(2026, 11, 20)))
    MonthlyComplianceReview.objects.create(
        cost_center=first, period=PERIOD, status="completed"
    )
    inspection = kinds["drone-inspection"]
    for index in range(aircraft_count):
        tail = aircraft(f"RPA-90{index + 1:02d}", sites[index % centres])
        if index % 3 == 0:
            document(inspection, tail, expiry=date(2027, 3, 1))
        elif index % 3 == 1:
            document(inspection, tail, expiry=date(2026, 11, 1))
        if index == 0:
            document(kinds["rpa-service-life"], tail)
    one = operator("P1", first)
    two = operator("P2", first)
    assessment(one, passed=True, taken=date(2026, 10, 5), expires=date(2027, 10, 5))
    assessment(two, passed=False, taken=date(2026, 10, 6), expires=date(2027, 10, 6))
    document(kinds["operator-qualification-intake"], one)
    return sites
