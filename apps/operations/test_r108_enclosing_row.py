"""R10.8 y LV-132: una fila por circunferencia, con los números declarables.

R10.8 puso la circunferencia mínima **al lado** de la dibujada, y el usuario
reportó lo que eso produce en pantalla: *"se ve como doble datos […] no es mejor
dejar solo uno?"*. Sobre `CC 716` las dos filas decían 3106 y 3115 m con el mismo
aeródromo y la misma distancia. Y el problema de fondo no era el ruido: dos
juegos al mismo nivel **invitan a mezclar el centro de uno con el radio del
otro**, y el punto dibujado con el radio del círculo envolvente no cubre el área.

Lo que estos tests sujetan: cuando el área no es circular, la fila **es** la del
círculo que la encierra —centro, radio y AMC del mismo objeto— y el radio
promedio de lo dibujado viaja aparte, como referencia y no como casilla.
"""

import math

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.core.management import call_command

from apps.geo.kml.canonical import empty_document, new_uid
from apps.geo.models import GeoPlan, GeoPlanVersion
from apps.geo.sections import haversine_km
from apps.operations.flight_requests import plan_sections
from apps.registry.models import CostCenter

# Cerca del área real de CC 861 (Tranque Talabre), donde el AMC del catálogo es
# Andrés Sabella y las distancias son de cientos de kilómetros: a esa escala un
# centro corrido decenas de kilómetros cambia el número que se declara.
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
    rows = plan_sections(plan)
    # Una circunferencia, una fila. La regla de LV-132, afirmada donde se genera.
    assert len(rows) == 1
    return rows[0]


@pytest.mark.django_db
class TestAnIrregularArea:
    def test_the_row_is_the_enclosing_circle_not_the_drawn_point(self, plan):
        """El punto declarado va en una esquina del área alargada, así que el
        centro del círculo que la encierra queda lejos: si la fila mostrara el
        punto, la latitud sería la del punto."""
        document = _document(
            [(0, 0), (0.5, 0), (0.5, 0.02), (0, 0.02)], with_point_at=(0, 0)
        )

        row = _row(plan, document)

        assert row["is_enclosing"] is True
        assert row["lat"] != pytest.approx(LAT)
        # El centro del círculo cae al medio del área, ~0.25° al este del punto.
        assert row["lon"] == pytest.approx(LON + 0.25, abs=0.01)

    def test_its_aerodrome_is_measured_from_that_centre(self, plan):
        """La distancia y el aeródromo salen del centro que se va a declarar. Si
        se copiaran del punto dibujado, serían dos datos correctos por separado
        que juntos describen una solicitud que no existe."""
        document = _document(
            [(0, 0), (0.5, 0), (0.5, 0.02), (0, 0.02)], with_point_at=(0, 0)
        )

        row = _row(plan, document)
        amc = row["amc"]
        assert amc is not None
        desde_el_centro = haversine_km(
            row["lat"], row["lon"], float(amc.latitude), float(amc.longitude)
        )
        desde_el_punto = haversine_km(
            LAT, LON, float(amc.latitude), float(amc.longitude)
        )

        assert row["amc_distance_km"] == pytest.approx(desde_el_centro, abs=0.1)
        # Y las dos medidas difieren de verdad: sin esto el test pasaría también
        # si el centro no se hubiera movido.
        assert abs(desde_el_centro - desde_el_punto) > 5

    def test_the_drawn_average_travels_as_a_reference_only(self, plan):
        """Se muestra en chico y no como casilla: el radio promedio de algo que
        no es un círculo es el artefacto de medir un no-círculo."""
        document = _document([(0, 0), (0.5, 0), (0.5, 0.02), (0, 0.02)])

        row = _row(plan, document)

        assert row["drawn_radius_m"] is not None
        # El envolvente cubre el área entera, así que es mayor que el promedio.
        assert row["radius_m"] > row["drawn_radius_m"]


@pytest.mark.django_db
class TestACircularArea:
    def test_it_keeps_the_drawn_point_and_radius(self, plan):
        circle = [
            (
                (400 * math.sin(2 * math.pi * step / 60))
                / (111_320 * math.cos(math.radians(LAT))),
                (400 * math.cos(2 * math.pi * step / 60)) / 111_320,
            )
            for step in range(60)
        ]

        row = _row(plan, _document(circle, with_point_at=(0, 0)))

        assert row["is_enclosing"] is False
        assert row["drawn_radius_m"] is None
        assert row["warnings"] == []
        assert row["lat"] == pytest.approx(LAT)
        assert row["radius_m"] == pytest.approx(400, abs=5)


class TestTheTableShowsOneRowPerCircle:
    """LV-132, leído en el archivo: la segunda fila no puede volver.

    Igual que el test de iconos de `R10.3` y el del encabezado de `LV-131`: lo
    que se afirma es una decisión sobre el marcado, y una página renderizada no
    distingue "dos filas" de "una fila con dos líneas".
    """

    def test_the_template_has_no_second_row_for_the_enclosing_circle(self):
        source = (
            settings.BASE_DIR / "templates" / "geo" / "plan_detail.html"
        ).read_text(encoding="utf-8")

        assert "row.enclosing" not in source
        assert "row.is_enclosing" in source
