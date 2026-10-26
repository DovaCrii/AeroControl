"""LV-378: el caso ficticio con todos los casos límite del informe v2.

Un solo lugar que arma, en la base de pruebas, la situación que rompió el informe de
octubre (centro terminado con permiso vigente, otro que no vuela, siete permisos
iguales, un vencido sin cerrar y uno en trámite), para que los tests de los tres PR
—cifras, permisos y resumen/cobertura— hablen del mismo caso. **No es un test**: el
nombre no empieza por `test_`, así que pytest no lo recolecta.

Códigos `CC9xx`, nombres genéricos y correos de prueba: nada es dato real.

Corte `2026-10-26` (el del informe anticipado de octubre). Lo que da:

| Centro | Situación al corte | Cuenta en la cobertura |
|---|---|---|
| CC901 | 7 permisos iguales, vigentes, vencen en 28 días, un único operador | sí |
| CC902 | 1 vigente (53 días, dos operadores) y 1 aprobado **vencido sin cerrar** | sí |
| CC903 | sin permiso vigente y 1 solicitud en trámite | sí |
| CC904 | **no vuela**, con 1 permiso vigente (65 días) | no |
| CC905 | contrato **terminado**, con 1 permiso vigente (2 días) | no |

Vigentes: 10 = 8 con operación + 2 sin operación. En trámite: 1. Vencidos sin cerrar: 1.
Vencen en 30 días (con operación): 7; en 60 días (con operación): 8.
"""

from datetime import date, datetime, time, timedelta
from itertools import count

from django.utils import timezone

from apps.operations.models import FlightPermission
from apps.registry.models import Aircraft, CostCenter, Operator

PERIOD = date(2026, 10, 1)
CUTOFF = date(2026, 10, 26)


#: N° DGAC ficticios y distintos para cada permiso aprobado (los de trámite no lo tienen).
_dgac = count(7001)


def _permit(centre, *, status="approved", start=None, end=None, operators=(), tails=()):
    permit = FlightPermission.objects.create(
        cost_center=centre,
        permission_number="" if status == "requested" else str(next(_dgac)),
        purpose="photogrammetry",
        status=status,
        location="Sector ficticio",
        area_type="unpopulated",
        valid_from=start,
        valid_until=end,
    )
    # `created_at` es `auto_now_add`: se retrasa para que el corte lo cuente.
    FlightPermission.objects.filter(pk=permit.pk).update(
        created_at=timezone.make_aware(datetime.combine(date(2026, 7, 15), time(12)))
    )
    permit.operators.add(*operators)
    permit.aircraft_fleet.add(*tails)
    permit.refresh_from_db()
    return permit


def _operator(code, name, centre):
    return Operator.objects.create(
        employee_id=code,
        full_name=name,
        cost_center=centre,
        email=f"{code.lower()}@test.com",
    )


def _aircraft(registration, centre):
    return Aircraft.objects.create(
        registration=registration,
        type="RPA",
        model="Modelo ficticio",
        manufacturer="Fabricante ficticio",
        cost_center=centre,
    )


def make_case():
    """Crea el caso y devuelve `{código: centro}`."""
    north = CostCenter.objects.create(
        code="CC901", name="Faena Norte", operates_flights=True
    )
    south = CostCenter.objects.create(
        code="CC902", name="Faena Sur", operates_flights=True
    )
    east = CostCenter.objects.create(
        code="CC903", name="Faena Este", operates_flights=True
    )
    ground = CostCenter.objects.create(
        code="CC904", name="Faena Sin Vuelo", operates_flights=False
    )
    ended = CostCenter.objects.create(
        code="CC905",
        name="Faena Terminada",
        operates_flights=True,
        contract_status=CostCenter.CONTRACT_CLOSED,
    )

    one = _operator("P901", "Operador Uno", north)
    two = _operator("P902", "Operador Dos", south)
    three = _operator("P903", "Operador Tres", south)
    four = _operator("P904", "Operador Cuatro", ground)

    # Siete permisos con la misma vigencia, aeronave y operador: una sola línea.
    shared_tail = _aircraft("RPA-9001", north)
    for _n in range(7):
        _permit(
            north,
            start=date(2026, 8, 28),
            end=CUTOFF + timedelta(days=28),
            operators=[one],
            tails=[shared_tail],
        )
    _permit(
        south,
        start=date(2026, 9, 1),
        end=CUTOFF + timedelta(days=53),
        operators=[two, three],
        tails=[_aircraft("RPA-9101", south), _aircraft("RPA-9102", south)],
    )
    # Aprobado, con la vigencia ya pasada y nadie lo cerró.
    _permit(
        south,
        start=date(2026, 7, 1),
        end=date(2026, 10, 20),
        operators=[two],
    )
    _permit(east, status=FlightPermission.STATUS_REQUESTED, operators=[three])
    _permit(
        ground,
        start=date(2026, 9, 1),
        end=CUTOFF + timedelta(days=65),
        operators=[four],
    )
    _permit(
        ended,
        start=date(2026, 7, 28),
        end=CUTOFF + timedelta(days=2),
        operators=[four],
    )
    return {c.code: c for c in (north, south, east, ground, ended)}
