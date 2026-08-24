"""LV-141: comuna, provincia y región del punto central.

Pedido del usuario: *"en la planificación geoespacial quiero que me entregue el
dato de la comuna y el área […] esta debe ser de la circunferencia del KMZ
entregado, del pin central, la comuna y el área a volar y la región"*, y después
*"se le puede sumar entonces todos los datos como región provincia comuna que son
los principales"*.

Las coordenadas de los casos son las **faenas reales**, y sus resultados se
verificaron uno por uno contra lo que se sabe del terreno: el valle del Choapa es
Salamanca, el tranque El Mauro es Los Vilos, el embalse Carén es Alhué. Un test
con coordenadas inventadas no habría detectado un error de proyección — que es el
riesgo real acá, porque el shapefile de BCN viene en Web Mercator y hubo que
invertirlo a mano.
"""

import pytest

from apps.geo.administrative import DATA_FILE, locate


class TestTheRealSites:
    @pytest.mark.parametrize(
        ("lat", "lon", "comuna", "provincia"),
        [
            # Los siete KMZ de CC 738, a lo largo de 25 km de quebrada.
            (-31.906392, -70.717982, "Salamanca", "Choapa"),
            (-31.917712, -70.949562, "Salamanca", "Choapa"),
            # CC 691, tranque de relaves El Mauro.
            (-31.967111, -71.021678, "Los Vilos", "Choapa"),
            # CC 861, Tranque Talabre: el permiso en producción dice
            # "Antofagasta, Antofagasta" y el punto cae en Calama. Este test
            # documenta el dato correcto, que es la mitad del valor de la fila.
            (-22.329039, -68.791275, "Calama", "El Loa"),
            # Embalse Carén.
            (-34.109431, -71.134258, "Alhué", "Melipilla"),
        ],
    )
    def test_it_resolves_the_commune_and_province(self, lat, lon, comuna, provincia):
        found = locate(lat, lon)

        assert found is not None
        assert found["comuna"] == comuna
        assert found["provincia"] == provincia
        assert found["region"]

    def test_insular_territory_is_covered(self):
        """La capa incluye Isla de Pascua, que es comuna y provincia a la vez."""
        found = locate(-27.1127, -109.3497)

        assert found is not None
        assert found["comuna"] == "Isla de Pascua"


class TestWhatItRefusesToAnswer:
    def test_a_point_at_sea_gets_nothing(self):
        """None es una respuesta legítima: mejor no decir nada que nombrar una
        comuna equivocada."""
        assert locate(-33.0, -75.0) is None

    def test_a_missing_coordinate_gets_nothing(self):
        assert locate(None, -70.7) is None
        assert locate(-33.0, None) is None


class TestTheDataFile:
    def test_it_has_the_346_communes_and_declares_its_source(self):
        text = DATA_FILE.read_text(encoding="utf-8")
        header = [line for line in text.splitlines() if line.startswith("#")]
        rows = [line for line in text.splitlines() if line and not line.startswith("#")]

        assert len(rows) == 346
        # La procedencia y la advertencia viajan **en el archivo**, no sólo en el
        # commit: quien lo abra en dos años tiene que leer de dónde salió y por
        # qué es referencial.
        assert any("Biblioteca del Congreso Nacional" in line for line in header)
        assert any("REFERENCIAL" in line for line in header)

    def test_every_row_has_its_five_fields_and_a_usable_ring(self):
        for line in DATA_FILE.read_text(encoding="utf-8").splitlines():
            if line.startswith("#") or not line:
                continue
            code, comuna, provincia, region, bbox, rings = line.split("|", 5)
            assert code.isdigit(), line[:60]
            assert comuna and provincia and region, line[:60]
            assert len(bbox.split(",")) == 4, line[:60]
            first_ring = rings.split(";")[0].split(" ")
            # Cuatro vértices es el mínimo de un anillo cerrado.
            assert len(first_ring) >= 4, line[:60]


class TestTheRowThatFeedsSigo:
    """Que el dato llegue a la fila que la persona copia, no sólo al módulo."""

    @pytest.mark.django_db
    def test_the_plan_row_carries_commune_province_and_region(self):
        import math

        from django.contrib.auth.models import User

        from apps.geo.kml.canonical import empty_document, new_uid
        from apps.geo.models import GeoPlan, GeoPlanVersion
        from apps.operations.flight_requests import plan_sections
        from apps.registry.models import CostCenter

        lat, lon = -31.906392, -70.717982
        ring = []
        for step in range(36):
            angle = 2 * math.pi * step / 36
            ring.append(
                [
                    lon
                    + (400 * math.sin(angle)) / (111_320 * math.cos(math.radians(lat))),
                    lat + (400 * math.cos(angle)) / 111_320,
                    0,
                ]
            )
        ring.append(list(ring[0]))

        def placemark(name, geometry):
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

        document = empty_document()
        document["children"] = [
            placemark("Centro CG-01", {"type": "Point", "coordinates": [lon, lat, 0]}),
            placemark("Área", {"type": "Polygon", "coordinates": [ring]}),
        ]
        owner = User.objects.create_user("owner-141", "o141@test.com", "pw")  # nosec B106
        plan = GeoPlan.objects.create(
            title="CC738 · CG-01",
            cost_center=CostCenter.objects.create(code="CC738", name="MLP"),
            created_by=owner,
        )
        version = GeoPlanVersion.objects.create(
            plan=plan,
            version_number=1,
            content=document,
            content_checksum="x" * 64,
            source="import",
            created_by=owner,
        )
        plan.current_version = version
        plan.save(update_fields=["current_version", "updated_at"])

        row = plan_sections(plan)[0]

        assert row["comuna"] == "Salamanca"
        assert row["provincia"] == "Choapa"
        assert "Coquimbo" in row["region"]
