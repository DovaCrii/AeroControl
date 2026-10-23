"""LV-361 phase 2: ENR 5.1 parser, on SYNTHETIC text.

Nothing here is copied from the AIP: zone codes, names, coordinates and contacts
are invented with the same shape as the source (the real PDF and its remarks are
the property of the DGAC and carry personal data, so they never enter git).
"""

import re

import pytest

from apps.airspace import aip_parser as P
from apps.airspace.kml_import import normalize_zone_code

# --- coordinates ---------------------------------------------------------

FORMATS = [
    ("53 46 00 S 70 31 00 W", -(53 + 46 / 60), -(70 + 31 / 60)),
    (
        "334403.74S/0704141.16W",
        -(33 + 44 / 60 + 3.74 / 3600),
        -(70 + 41 / 60 + 41.16 / 3600),
    ),
    (
        "53 02 23.06S – 70 56 06.09W",
        -(53 + 2 / 60 + 23.06 / 3600),
        -(70 + 56 / 60 + 6.09 / 3600),
    ),
    (
        "20 15 29,48 S / 70 06 31,66 W",
        -(20 + 15 / 60 + 29.48 / 3600),
        -(70 + 6 / 60 + 31.66 / 3600),
    ),
    ("201125S/0700815W", -(20 + 11 / 60 + 25 / 3600), -(70 + 8 / 60 + 15 / 3600)),
    ("30 49 28 S / 711317 W", -(30 + 49 / 60 + 28 / 3600), -(71 + 13 / 60 + 17 / 3600)),
]


@pytest.mark.parametrize("text, lat, lon", FORMATS)
def test_the_six_formats_parse(text, lat, lon):
    coordinate = P.parse_coordinate(text)
    assert coordinate.lat == pytest.approx(lat, abs=1e-6)
    assert coordinate.lon == pytest.approx(lon, abs=1e-6)


@pytest.mark.parametrize("text", [f[0] for f in FORMATS[:5]])
def test_clean_formats_carry_no_warning(text):
    assert P.parse_coordinate(text).warnings == ()


def test_seconds_without_leading_zero_are_accepted():
    assert P.parse_coordinate("33 26 39.48 S / 70 41 9.06 W").lon == pytest.approx(
        -(70 + 41 / 60 + 9.06 / 3600), abs=1e-6
    )


ERRATA = [
    # text, expected warning code, expected (lat, lon)
    (
        "30 49 28 S / 07 031 15 W",
        "misplaced_space",
        (-(30 + 49 / 60 + 28 / 3600), -(70 + 31 / 60 + 15 / 3600)),
    ),
    (
        "30 49 28 S / 70 56 48 .74W",
        "space_in_decimal",
        (-(30 + 49 / 60 + 28 / 3600), -(70 + 56 / 60 + 48.74 / 3600)),
    ),
    (
        "30 49 28 S / 70 56 48, 74 W",
        "space_in_decimal",
        (-(30 + 49 / 60 + 28 / 3600), -(70 + 56 / 60 + 48.74 / 3600)),
    ),
    (
        "334403S/710636W",
        "six_digit_longitude",
        (-(33 + 44 / 60 + 3 / 3600), -(71 + 6 / 60 + 36 / 3600)),
    ),
    (
        "30,49 28 S / 70 31 15 W",
        "separator_typo",
        (-(30 + 49 / 60 + 28 / 3600), -(70 + 31 / 60 + 15 / 3600)),
    ),
]


@pytest.mark.parametrize("text, code, expected", ERRATA)
def test_known_errata_give_a_proposal_and_a_warning(text, code, expected):
    coordinate = P.parse_coordinate(text)
    assert code in P.warning_codes(coordinate.warnings)
    assert (coordinate.lat, coordinate.lon) == pytest.approx(expected, abs=1e-6)


def test_space_before_the_hemisphere_of_a_decimal_compact_group_is_flagged():
    coordinate = P.parse_coordinate("334403.74S/0704141.16 W")
    assert P.warning_codes(coordinate.warnings) == ["space_before_hemisphere"]
    assert coordinate.lon == pytest.approx(-(70 + 41 / 60 + 41.16 / 3600), abs=1e-6)


def test_the_six_digit_longitude_is_not_silent_even_in_the_documented_format():
    assert "six_digit_longitude" in P.warning_codes(
        P.parse_coordinate("30 49 28 S / 711317 W").warnings
    )


@pytest.mark.parametrize(
    "text",
    [
        "30 49 28 S / 33,31 W",  # comma between degrees and minutes with nothing to anchor it
        "30 49 28 S / 7031 W",  # four digits: neither DDMM nor anything else
        "30 49 28 S / 70 31 75 W",  # seconds out of range
        "30 49 28 S / 70 61 15 W",  # minutes out of range
        "30 49 28 N / 70 31 15 W",  # northern hemisphere, outside Chile
        "10 49 28 S / 70 31 15 W",  # latitude above -17
        "60 49 28 S / 70 31 15 W",  # latitude below -57
        "30 49 28 S / 60 31 15 W",  # longitude east of -66
        "30 49 28 S / 111 31 15 W",  # longitude west of -110
        "30 49 28 S 70 31 15",  # no hemisphere for the longitude
    ],
)
def test_ambiguous_or_out_of_range_is_an_error_not_a_guess(text):
    with pytest.raises(P.CoordinateError):
        P.parse_coordinate(text)


def test_range_edges_are_inclusive():
    assert P.parse_coordinate("17 00 00 S / 66 00 00 W").lat == -17
    assert P.parse_coordinate("57 00 00 S / 110 00 00 W").lon == -110


def test_find_coordinates_reports_unreadable_pairs_in_place():
    found = P.find_coordinates(
        "30 49 28 S / 70 31 15 W\n30 49 75 S / 70 31 15 W\n31 00 00 S / 71 00 00 W"
    )
    assert [bool(m.coordinate) for m in found] == [True, False, True]
    assert "out of range" in found[1].error


def test_unit_words_are_not_read_as_hemispheres():
    assert (
        P.find_coordinates(
            "Círculo 1 NM de radio, 20 NM y 90 NM desde el VOR/DME, Radio 6NM"
        )
        == []
    )


# --- codes and blocks ----------------------------------------------------


@pytest.mark.parametrize(
    "text, code",
    [
        ("SC-P3", "SC-P3"),
        ("SC - R54", "SC-R54"),
        ("SC R-41", "SC-R41"),
        ("SC – D5", "SC-D5"),
        ("SC- R1", "SC-R1"),
    ],
)
def test_codes_are_normalised_like_the_kml_importer(text, code):
    zone = P.parse_zone(f"{text} FIR SANTIAGO\nSector Demo\nEspacio aéreo:\n{POLY_OK}")
    assert zone["code"] == code == normalize_zone_code(text)


def test_split_blocks_by_code_ignores_the_legend_line():
    lines = [
        "SC-P3 SC- R1 SC-D11",
        "SC-P901 FIR PUNTA ARENAS",
        "x",
        "SC - R54 FIR SANTIAGO-Sector Z",
        "y",
    ]
    assert P.split_blocks_by_code(lines) == [1, 3]


def test_header_splits_fir_and_name_and_keeps_both_languages():
    zone = P.parse_zone(
        "SC - D905 FIR SANTIAGO-Sector Demo Norte\nDemo training area\nEspacio aéreo/Airspace:\n"
        + POLY_OK,
        "UNL\nGND",
    )
    assert zone["fir"] == "SANTIAGO"
    assert zone["name"] == "Sector Demo Norte / Demo training area"
    assert zone["kind"] == "D" and zone["vertical_text"] == "UNL / GND"


def test_a_zone_without_code_is_kept_and_flagged():
    zone = P.parse_zone(
        "ZONA PELIGROSA - FIR ANTOFAGASTA Vuelo demo\nEspacio aéreo:\n" + POLY_OK
    )
    assert zone["code"] == "" and zone["kind"] == "D"
    assert "no_code" in P.warning_codes(zone["warnings"])
    assert zone["review_status"] == P.REVIEW_NEEDS


def test_parse_zone_rejects_a_block_without_header():
    with pytest.raises(ValueError):
        P.parse_zone("Sector Demo\n" + POLY_OK)


# --- polygons ------------------------------------------------------------

POLY_OK = "30 00 00 S 70 00 00 W\n30 00 00 S 69 00 00 W\n31 00 00 S 69 00 00 W\n31 00 00 S 70 00 00 W"


def _poly(vertices, tail=""):
    return P.parse_zone(
        f"SC-P901 FIR SANTIAGO\nSector Demo\nEspacio aéreo:\n{vertices}{tail}",
        "UNL\nGND",
    )


def test_simple_polygon_is_clean_and_closed_geojson():
    zone = _poly(POLY_OK)
    assert (
        zone["geometry_method"] == "polygon" and zone["review_status"] == P.REVIEW_CLEAN
    )
    ring = zone["geometry"]["coordinates"][0]
    assert ring[0] == ring[-1] and len(ring) == 5
    assert ring[0] == [-70.0, -30.0]  # GeoJSON order: lon, lat
    assert zone["warnings"] == []


def test_a_repeated_first_vertex_is_normalised():
    zone = _poly(POLY_OK + "\n30 00 00 S 70 00 00 W")
    assert len(zone["geometry"]["coordinates"][0]) == 5
    assert zone["review_status"] == P.REVIEW_CLEAN


BOWTIE = "30 00 00 S 70 00 00 W\n31 00 00 S 69 00 00 W\n30 00 00 S 69 00 00 W\n31 00 00 S 70 00 00 W"


def test_a_crossing_vertex_order_is_flagged_and_never_reordered():
    zone = _poly(BOWTIE)
    assert "bowtie" in P.warning_codes(zone["warnings"])
    assert zone["review_status"] == P.REVIEW_NEEDS
    ring = zone["geometry"]["coordinates"][0]
    assert ring[:4] == [[-70.0, -30.0], [-69.0, -31.0], [-69.0, -30.0], [-70.0, -31.0]]


def test_ring_self_intersection_cases():
    square = [(0, 0), (1, 0), (1, 1), (0, 1)]
    assert not P.ring_self_intersects(square)
    assert P.ring_self_intersects([(0, 0), (1, 1), (1, 0), (0, 1)])
    assert P.ring_self_intersects(
        [(0, 0), (2, 0), (1, 0), (1, 1)]
    )  # spike doubling back
    concave = [(0, 0), (4, 0), (4, 4), (2, 1), (0, 4)]
    assert not P.ring_self_intersects(concave)


def test_an_unreadable_vertex_leaves_no_geometry_and_says_why():
    zone = _poly(POLY_OK.replace("31 00 00 S 69 00 00 W", "31 00 75 S 69 00 00 W"))
    assert zone["geometry"] is None
    assert {"vertex_unreadable", "incomplete_polygon"} <= set(
        P.warning_codes(zone["warnings"])
    )
    assert zone["review_status"] == P.REVIEW_NEEDS


def test_vertex_errata_warnings_name_the_vertex():
    zone = _poly(
        "30 00 00 S 70 00 00 W\n30 00 00 S 69 00 00 W\n31 00 00 S 07 031 15 W\n31 00 00 S 70 00 00 W"
    )
    assert any(w.startswith("misplaced_space: vertex 3:") for w in zone["warnings"])
    assert zone["geometry"] is not None and zone["review_status"] == P.REVIEW_NEEDS


def test_two_vertices_are_not_a_polygon():
    zone = _poly("30 00 00 S 70 00 00 W\n30 00 00 S 69 00 00 W")
    assert zone["geometry"] is None and "too_few_vertices" in P.warning_codes(
        zone["warnings"]
    )


def test_no_coordinates_at_all():
    zone = _poly("", "Zona de demostración sin coordenadas")
    assert zone["geometry"] is None and zone["geometry_method"] == "none"


# --- circles -------------------------------------------------------------

CENTRE = "30 00 00 S 70 00 00 W"


def _circle(text):
    return P.parse_zone(f"SC-R902 FIR SANTIAGO\nSector Demo\n{text}\n{CENTRE}")


@pytest.mark.parametrize(
    "text, metres",
    [
        ("Círculo de 1,5 NM de radio centrado en las coordenadas:", 1.5 * 1852),
        ("Círculo de radio 500 m centrado en:", 500),
        ("Círculo de 2 km de radio centrado en:", 2000),
        ("Círculo con radio 2NM centrado en:", 2 * 1852),
        ("Radio 6NM centrado en las siguientes coordenadas", 6 * 1852),
        ("Círculo 1 NM radio centrado en:", 1852),
        ("Circle radius 0.15 NM centred in:", 0.15 * 1852),
    ],
)
def test_circle_radius_in_each_unit(text, metres):
    zone = _circle(text)
    assert zone["geometry_method"] == "circle"
    assert zone["params"]["radius_m"] == pytest.approx(metres)
    assert (zone["params"]["centre_lat"], zone["params"]["centre_lon"]) == (
        -30.0,
        -70.0,
    )
    assert zone["warnings"] == [] and zone["review_status"] == P.REVIEW_CLEAN


def test_circle_ring_is_at_the_radius():
    zone = _circle("Círculo de 1 NM de radio centrado en:")
    ring = zone["geometry"]["coordinates"][0]
    assert ring[0] == ring[-1] and len(ring) == P.CIRCLE_SEGMENTS + 1
    # one degree of latitude is ~111.2 km; the northernmost point is 1 NM from the centre
    north = max(lat for _, lat in ring)
    assert (north - -30.0) * 111195 == pytest.approx(1852, rel=0.01)


def test_capital_m_is_metres_and_flagged():
    zone = _circle("Círculo de 500M de radio centrado en las")
    assert zone["params"]["radius_m"] == 500
    assert P.warning_codes(zone["warnings"]) == ["unit_capital_m"]


def test_500m_with_03nm_warns_about_the_discrepancy():
    zone = _circle(
        "Límites Laterales: círculo de 500m (0.3 NM) de radio, centrado en las siguientes coordenadas"
    )
    assert "radius_discrepancy" in P.warning_codes(zone["warnings"])
    assert zone["params"]["radius_m"] == 500


def test_consistent_double_unit_does_not_warn():
    zone = _circle(
        "Límites Laterales: círculo de 1852 m (1 NM) de radio, centrado en las siguientes coordenadas"
    )
    assert zone["warnings"] == []


def test_circle_without_radius_or_with_two_centres_has_no_geometry():
    no_radius = _circle("Círculo centrado en:")
    assert no_radius["geometry"] is None and "radius_missing" in P.warning_codes(
        no_radius["warnings"]
    )
    two = P.parse_zone(
        f"SC-R902 FIR SANTIAGO\nX\nCírculo de 1 NM de radio centrado en:\n{CENTRE}\n{CENTRE}"
    )
    assert two["geometry"] is None and "circle_centre" in P.warning_codes(
        two["warnings"]
    )


# --- arcs, sectors, shapes without geometry ------------------------------


def test_arc_with_external_centre_has_no_geometry():
    zone = P.parse_zone(
        "SC-R903 FIR ANTOFAGASTA\nDemo\nEspacio Aéreo/Airspace:\n21 41 00 S 69 56 00 W\n22 17 00 S 69 15 00 W\n"
        "Siguiendo arco 25 DME VOR XYZ hasta:\n22 33 00 S 69 19 00 W"
    )
    assert zone["geometry"] is None and zone["geometry_method"] == "arc"
    assert "external_centre" in P.warning_codes(zone["warnings"])
    assert zone["review_status"] == P.REVIEW_NEEDS


def test_sector_of_radials_has_no_geometry():
    zone = P.parse_zone(
        "SC-R904 FIR PUNTA ARENAS\nDemo\nEspacio aéreo entre los radiales 192° y 293° entre las\n"
        "distancias 20 NM y 90 NM desde el VOR/DME XYZ"
    )
    assert zone["geometry"] is None and zone["geometry_method"] == "sector"
    assert "magnetic_radials" in P.warning_codes(zone["warnings"])


def test_rectangle_is_not_invented():
    zone = P.parse_zone(
        f"SC-D905 FIR SANTIAGO\nDemo\nCuadrilátero de 0.7 x 0.2 NM siguientes\n{CENTRE}"
    )
    assert zone["geometry"] is None and zone["geometry_method"] == "unsupported"


# --- personal data -------------------------------------------------------

REMARKS = (
    "H24. Coordinar con Cap. Juan Perez, fono: +56 2 2555 0100, anexo 1234, correo ops.demo@example.test. "
    "Tel. 2 2555 0101 / (56-2) 2555 0102. Celular 9 8765 4321. Horario 0800-1700 LT, 118.100 MHz, FL 450, 3 000 FT. "
    "IVNO/VRNO. Contactar a jefe.turno@test.com."
)


def test_no_email_or_phone_survives_in_any_text_field():
    zone = P.parse_zone(
        "SC-P906 FIR SANTIAGO\nSector Demo fono +56 9 1234 5678\nEspacio aéreo:\n"
        + POLY_OK
        + "\n+56 2 2555 0103",
        "UNL\nGND 600 123 4567",
        REMARKS,
    )
    blob = " ".join(
        zone[k] for k in ("name", "lateral_text", "vertical_text", "remarks_text")
    )
    assert "@" not in blob
    assert not re.search(r"\+\d|\(\d{2}-\d\)", blob)
    for needle in (
        "Perez",
        "2555",
        "8765",
        "1234 5678",
        "example.test",
        "dominio-demo",
        "anexo 1234",
    ):
        assert needle not in blob
    assert P.CONTACT_PLACEHOLDER in zone["remarks_text"]


def test_bare_phone_numbers_without_a_label_are_scrubbed():
    out = P.scrub_contacts(
        "Llamar al 22 439 2000 o al 9 8765 4321 en horario 0800-1700."
    )
    assert "439" not in out and "8765" not in out and "0800-1700" in out


def test_a_seven_or_eight_digit_number_stuck_together_is_scrubbed_too():
    # Found on the real file (LV-361 phase 3): a landline written without spaces survived.
    out = P.scrub_contacts("Consultas 29222117 y 4567890; vigente 0800-1700 y 118.100.")
    assert "9222117" not in out and "4567890" not in out
    assert "0800-1700" in out and "118.100" in out


def test_scrubbing_keeps_schedules_frequencies_and_levels():
    out = P.scrub_contacts(REMARKS)
    for keep in (
        "H24",
        "0800-1700 LT",
        "118.100 MHz",
        "FL 450",
        "3 000 FT",
        "IVNO/VRNO",
    ):
        assert keep in out


def test_scrubbing_is_idempotent_and_leaves_plain_text_alone():
    once = P.scrub_contacts(REMARKS)
    assert P.scrub_contacts(once) == once
    assert (
        P.scrub_contacts("Activada por NOTAM. Coordinar con ACC.")
        == "Activada por NOTAM. Coordinar con ACC."
    )


# --- idempotence and summary --------------------------------------------


def test_parse_zone_is_idempotent():
    args = (
        "SC-P901 FIR SANTIAGO\nSector Demo\nEspacio aéreo:\n" + BOWTIE,
        "UNL\nGND",
        REMARKS,
    )
    assert P.parse_zone(*args) == P.parse_zone(*args)


def test_summary_counts_by_kind_method_and_warning():
    zones = [_poly(POLY_OK), _poly(BOWTIE), _circle("Círculo 1 NM radio centrado en:")]
    summary = P.summarize(zones)
    assert summary["zones"] == 3 and summary["with_geometry"] == 3
    assert summary["clean"] == 2 and summary["needs_review"] == 1
    assert summary["by_method"] == {"polygon": 2, "circle": 1}
    assert summary["warning_codes"] == {"bowtie": 1}
    assert summary["polygon_vertices_found"] == summary["polygon_vertices_ok"] == 8


# --- words with bounding boxes -------------------------------------------


def _word(text, x0, top):
    return {
        "text": text,
        "x0": x0,
        "x1": x0 + 4 * len(text),
        "top": top,
        "bottom": top + 8,
    }


def _row(texts, x0, top, step=14):
    return [_word(t, x0 + i * step, top) for i, t in enumerate(texts)]


def _page(header_x, body, furniture_top=10, with_header=True):
    words = _row(["AIP-CHILE", "ENR", "5.1-9"], 85, furniture_top) + _row(
        ["AIS", "-", "CHILE", "AMDT", "NR", "67"], 85, 700
    )
    if with_header:
        words += _row(["ZONAS", "PROHIBIDAS"], 253, 30)
        words += _row(["Identificación,", "nombre"], 101, 40) + _row(
            ["Observaciones"], 421, 40
        )
        words += [
            _word("1", header_x[0], 60),
            _word("2", header_x[1], 60),
            _word("3", header_x[2], 60),
        ]
    return words + body


def _synthetic_pages():
    page1 = _page(
        (173, 324, 455),
        _row(["", "SC-P901", "FIR", "PUNTA", "ARENAS"], 80, 100)
        + _row(["Sector", "Demo", "Norte"], 85, 112)
        + _row(["área", "definida", "por", "las", "siguientes"], 85, 124)
        + _row(["30", "00", "00.50S", "–", "70", "00", "00.50W"], 85, 136)
        + _row(["30", "00", "00S", "–", "69", "00", "00W"], 85, 148)
        + _row(["1000", "FT", "AGL"], 300, 140)
        + _row(["GND"], 317, 152)
        + _row(["Zona", "prohibida", "para", "RPAS"], 393, 140)
        + _row(["Fono:", "+56", "2", "2555", "0100"], 393, 152),
    )
    page2 = _page(
        (173, 324, 455),
        _row(["31", "00", "00S", "–", "69", "00", "00W"], 85, 60)
        + _row(["31", "00", "00S", "–", "70", "00", "00W"], 85, 72)
        + _row(["cte.", "jefe.turno@test.com"], 393, 66)
        + _row(["SC-R902", "FIR", "SANTIAGO-Sector", "Demo", "Sur"], 85, 100)
        + _row(["Círculo", "de", "1", "NM", "de", "radio", "centrado", "en:"], 85, 112)
        + _row(["34", "00", "00", "S", "70", "30", "00", "W"], 85, 124)
        + _row(["UNL"], 300, 112)
        + _row(["GND"], 317, 124),
        with_header=False,
    )
    return [page1, page2]


def test_blocks_from_words_split_columns_and_continue_across_pages():
    blocks = P.blocks_from_words(_synthetic_pages())
    assert len(blocks) == 2
    first = blocks[0]
    assert first.col1[0] == "SC-P901 FIR PUNTA ARENAS"  # bullet glyph dropped
    assert len(first.col1) == 7  # header, name, intro, two vertices per page
    assert first.col2 == ["1000 FT AGL", "GND"]
    assert any("Fono" in line for line in first.col3)
    assert any(
        "@" in line for line in first.col3
    )  # raw blocks are not scrubbed; zones are
    assert blocks[1].col2 == ["UNL", "GND"]
    assert not any(
        "AMDT" in line or "AIP-CHILE" in line or "Identificación" in line
        for b in blocks
        for line in b.col1
    )


def test_parse_words_end_to_end_with_scrubbing_and_idempotence():
    zones, summary = P.parse_enr51_words(_synthetic_pages())
    assert [z["code"] for z in zones] == ["SC-P901", "SC-R902"]
    polygon, circle = zones
    assert polygon["geometry_method"] == "polygon"
    assert (
        len(polygon["geometry"]["coordinates"][0]) == 5
    )  # 4 vertices (two per page) + closing
    assert (
        circle["geometry_method"] == "circle" and circle["params"]["radius_m"] == 1852
    )
    blob = " ".join(z["remarks_text"] for z in zones)
    assert "@" not in blob and "2555" not in blob
    assert summary["zones"] == 2 and summary["without_code"] == 0
    assert P.parse_enr51_words(_synthetic_pages()) == (zones, summary)


def test_column_limits_follow_each_pages_header():
    words = _page((184, 327, 447), [])
    low, high, _ = P.column_bounds(words)
    assert low == pytest.approx((184 + 2 + 327 + 2) / 2, abs=1)
    assert high == pytest.approx((327 + 2 + 447 + 2) / 2, abs=1)
    assert P.column_bounds(_row(["sin", "encabezado"], 85, 100)) is None


def test_pages_before_the_table_yield_nothing():
    preamble = _row(["SC-P3", "SC-", "R1", "SC-D11"], 85, 100)
    assert P.blocks_from_words([preamble]) == []


# --- PDF layer (optional dependency) --------------------------------------


def test_pdf_layer_without_pdfplumber_raises_a_clear_error(monkeypatch):
    import sys

    from apps.airspace import aip_pdf

    monkeypatch.setitem(sys.modules, "pdfplumber", None)
    with pytest.raises(aip_pdf.PdfSupportMissing):
        aip_pdf.read_pages("nada.pdf")


def test_pdf_layer_reads_a_synthetic_pdf(tmp_path):
    pytest.importorskip("pdfplumber")
    reportlab = pytest.importorskip("reportlab.pdfgen.canvas")
    from apps.airspace import aip_pdf

    path = tmp_path / "synthetic.pdf"
    pdf = reportlab.Canvas(str(path), pagesize=(612, 792))
    for x, label in ((173, "1"), (324, "2"), (455, "3")):
        pdf.drawString(x, 792 - 60, label)
    pdf.drawString(85, 792 - 100, "SC-P901 FIR SANTIAGO")
    pdf.drawString(85, 792 - 112, "Sector Demo")
    pdf.drawString(85, 792 - 124, "Espacio aéreo:")
    for i, vertex in enumerate(POLY_OK.splitlines()):
        pdf.drawString(85, 792 - 136 - 12 * i, vertex)
    pdf.drawString(300, 792 - 136, "UNL")
    pdf.drawString(300, 792 - 148, "GND")
    pdf.drawString(393, 792 - 136, "H24")
    pdf.save()

    zones, summary = P.parse_enr51_words(aip_pdf.read_pages(path))
    assert [z["code"] for z in zones] == ["SC-P901"]
    assert (
        zones[0]["geometry_method"] == "polygon"
        and zones[0]["vertical_text"] == "UNL / GND"
    )
    assert zones[0]["remarks_text"] == "H24"
    assert len(aip_pdf.sha256_of(path)) == 64
