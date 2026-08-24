"""R10.8: la fila de la circunferencia mínima, y su propio AMC.

La parte que un test tiene que sujetar: **la distancia al aeródromo se mide desde
el centro que se va a declarar**, no desde el punto original. Devolver el AMC del
punto declarado junto a un centro distinto sería una fila internamente
inconsistente — dos datos correctos por separado que juntos describen una
solicitud que no existe.
"""

import math

import pytest
from django.core.management import call_command

from apps.geo.kml.canonical import empty_document, new_uid
from apps.geo.models import GeoPlan, GeoPlanVersion
from apps.operations.flight_requests import plan_sections
from apps.registry.models import CostCenter

# Cerca del área real de CC 861 (Tranque Talabre), donde el AMC del catálogo es
# Andrés Sabella y las distancias son de cientos de kilómetros: a esa escala un
# centro corrido 20 km cambia el número que se declara.
LAT, LON = -22.329039, -68.791275


def _placemark(name, geometry):
    return {
        "kind": "placemark",
        "uid": new_uid("placemark"),
        "name": name,
        "description": "",
        "visibility": True,
        "style_url": None,
        "geometry": geometry,
        "extended_data": None,
        "extras": [],
    }


def _document(offsets, *, with_point_at=None):
    ring = [[LON + dx, LAT + dy, 0] for dx, dy in offsets]
    ring.append(list(ring[0]))
    document = empty_document()
    if with_point_at is not None:
        dx, dy = with_point_at
        document["children"].append(
            _placemark(
                "Centro declarado",
                {"type": "Point", "coordinates": [LON + dx, LAT + dy, 0]},
            )
        )
    document["children"].append(
        _placemark("Área", {"type": "Polygon", "coordinates": [ring]})
    )
    return document


@pytest.fixture
def plan(db):
    call_command("seed_aerodromes")
    cost_center = CostCenter.objects.create(code="CC861", name="Tranque Talabre")
    from django.contrib.auth.models import User

    owner = User.objects.create_user("r108", "r108@test.com", "pw")  # nosec B106
    return GeoPlan.objects.create(
        title="Área irregular", cost_center=cost_center, created_by=owner
    )


def _row(plan, document):
    version = GeoPlanVersion.objects.create(
        plan=plan,
        version_number=1,
        content=document,
        content_checksum="x" * 64,
        source="import",
        created_by=plan.created_by,
    )
    plan.current_version = version
    plan.save(update_fields=["current_version", "updated_at"])
    return plan_sections(plan)[0]


@pytest.mark.django_db
class TestTheEnclosingRow:
    def test_its_aerodrome_is_measured_from_the_centre_that_will_be_declared(
        self, plan
    ):
        """El punto declarado va en una esquina del área alargada, así que el
        centro del círculo que la encierra queda a decenas de kilómetros: si el
        AMC se copiara del punto, las dos distancias serían iguales."""
        # Un área de ~0.5° de largo: del orden de 50 km, como las de CC 861.
        document = _document(
            [(0, 0), (0.5, 0), (0.5, 0.02), (0, 0.02)], with_point_at=(0, 0)
        )

        row = _row(plan, document)

        assert row["enclosing"] is not None
        assert row["amc"] is not None
        assert row["enclosing"]["amc"] is not None
        assert row["enclosing"]["amc_distance_km"] != row["amc_distance_km"]

    def test_it_carries_the_five_sigo_boxes(self, plan):
        """Las mismas casillas que la fila de arriba, para que se copien igual:
        grados, minutos y segundos por eje, radio, aeródromo y distancia."""
        document = _document([(0, 0), (0.2, 0), (0.2, 0.01), (0, 0.01)])

        enclosing = _row(plan, document)["enclosing"]

        assert set(enclosing) == {
            "lat",
            "lon",
            "dms_lat",
            "dms_lon",
            "lat_readable",
            "lon_readable",
            "radius_m",
            "amc",
            "amc_distance_km",
        }
        assert enclosing["dms_lat"]["hemisphere"] == "S"
        assert isinstance(enclosing["radius_m"], int)

    def test_a_circular_plan_has_no_enclosing_row(self, plan):
        circle = [
            (
                (400 * math.sin(2 * math.pi * step / 60))
                / (111_320 * math.cos(math.radians(LAT))),
                (400 * math.cos(2 * math.pi * step / 60)) / 111_320,
            )
            for step in range(60)
        ]

        row = _row(plan, _document(circle, with_point_at=(0, 0)))

        assert row["enclosing"] is None
        assert row["warnings"] == []
