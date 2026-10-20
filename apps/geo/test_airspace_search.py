"""Buscador puro del espacio aéreo (LV-357, fase 2)."""

import pytest

from apps.geo.airspace_search import (
    name_score,
    normalize_text,
    normalize_zone_code,
    parse_query,
    search_index,
)

SANTIAGO = (-33.0 - 26 / 60 - 28 / 3600, -70.0 - 39 / 60 - 17 / 3600)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("SC-R41", "SC-R41"),
        ("R41", "SC-R41"),
        ("r41", "SC-R41"),
        ("sc r-41", "SC-R41"),
        ("SC R-41", "SC-R41"),
        ("SC - R54", "SC-R54"),
        ("P 50", "SC-P50"),
        ("SC – P 30", "SC-P30"),  # guion largo
        ("SC — P30", "SC-P30"),
        ("scp30", "SC-P30"),
        ("SC-P029", "SC-P29"),  # ceros a la izquierda
        ("SC-D5", "SC-D5"),
        ("sa-r7", "SA-R7"),
        ("R", None),
        ("R4141", None),
        ("SC-X41", None),
        ("SCEL", None),
        ("Santiago", None),
        ("", None),
        (None, None),
    ],
)
def test_zone_code_normalisation(text, expected):
    assert normalize_zone_code(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Aeródromo Eulogio Sánchez", "aerodromo eulogio sanchez"),
        ("  ÑUÑOA--Tobalaba ", "nunoa tobalaba"),
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_text(text, expected):
    assert normalize_text(text) == expected


class TestParseQuery:
    @pytest.mark.parametrize("text", ["", "   ", None])
    def test_empty(self, text):
        assert parse_query(text)["type"] == "empty"

    @pytest.mark.parametrize("text", ["SCEL", "scel", " scel "])
    def test_oaci(self, text):
        assert parse_query(text) == {"type": "oaci", "code": "SCEL", "name": "scel"}

    @pytest.mark.parametrize("text", ["R41", "sc r-41", "P 50", "SC – P 30", "SC-R41"])
    def test_zone(self, text):
        parsed = parse_query(text)
        assert parsed["type"] == "zone"
        assert parsed["code"] == normalize_zone_code(text)

    @pytest.mark.parametrize(
        ("text", "lat", "lon"),
        [
            ("-33.45, -70.66", -33.45, -70.66),
            ("-33.45,-70.66", -33.45, -70.66),
            ("-33.45 -70.66", -33.45, -70.66),
            ("-33.45; -70.66", -33.45, -70.66),
            ("-33,45; -70,66", -33.45, -70.66),
            ("-33,45 -70,66", -33.45, -70.66),
            ("  33.45 ,  70.66 ", 33.45, 70.66),
            ("-33.45°, -70.66°", -33.45, -70.66),
            ("0, 0", 0.0, 0.0),
            ("-90, 180", -90.0, 180.0),  # bordes del rango, inclusivos
            ("90, -180", 90.0, -180.0),
        ],
    )
    def test_decimal_coordinate(self, text, lat, lon):
        parsed = parse_query(text)
        assert parsed["type"] == "coordinate"
        assert parsed["format"] == "decimal"
        assert parsed["lat"] == pytest.approx(lat)
        assert parsed["lon"] == pytest.approx(lon)

    @pytest.mark.parametrize(
        "text",
        [
            "33 26 28 S 70 39 17 W",
            "33°26'28\"S 70°39'17\"W",
            "33° 26′ 28″ S, 70° 39′ 17″ W",
            "33º26'28''S 70º39'17''W",
            "s 33 26 28 w 70 39 17",
            "S33 26 28 W70 39 17",
            "70 39 17 W 33 26 28 S",  # longitud primero: manda el hemisferio
            "33 26 28 s; 70 39 17 w",
        ],
    )
    def test_dms_coordinate(self, text):
        parsed = parse_query(text)
        assert parsed["type"] == "coordinate", parsed
        assert parsed["format"] == "dms"
        assert parsed["lat"] == pytest.approx(SANTIAGO[0])
        assert parsed["lon"] == pytest.approx(SANTIAGO[1])

    def test_dms_hemispheres_decide_the_sign(self):
        assert parse_query("33 26 28 N 70 39 17 E")["lat"] > 0
        assert parse_query("33 26 28 N 70 39 17 E")["lon"] > 0
        assert parse_query("33 26 28 N 70 39 17 W")["lon"] < 0
        assert parse_query("33 26 28 S 70 39 17 E")["lat"] < 0

    def test_dms_with_fewer_parts_and_decimal_degrees_with_hemisphere(self):
        parsed = parse_query("33 30 S 70 30 W")
        assert (parsed["lat"], parsed["lon"]) == (-33.5, -70.5)
        parsed = parse_query("33.5 S 70.25 W")
        assert (parsed["lat"], parsed["lon"]) == (-33.5, -70.25)

    @pytest.mark.parametrize(
        ("text", "reason"),
        [
            ("-91, -70", "latitude_out_of_range"),
            ("91, 0", "latitude_out_of_range"),
            ("-33, -181", "longitude_out_of_range"),
            ("100 S 70 W", "latitude_out_of_range"),
            ("33 S 190 W", "longitude_out_of_range"),
            ("90 30 0 N 70 W", "latitude_out_of_range"),  # más allá del polo
            ("33 61 0 S 70 W", "invalid_minutes_or_seconds"),
            ("33 26 60 S 70 W", "invalid_minutes_or_seconds"),
            ("33 26 28 S 70 39 17 N", "same_axis_twice"),
            ("33 26 28 E 70 39 17 W", "same_axis_twice"),
            ("-33 26 28 S 70 39 17 W", "sign_and_hemisphere"),
        ],
    )
    def test_invalid_coordinate_is_rejected_without_raising(self, text, reason):
        parsed = parse_query(text)
        assert parsed["type"] == "invalid_coordinate"
        assert parsed["reason"] == reason
        assert "lat" not in parsed

    @pytest.mark.parametrize(
        "text",
        ["Los Cerrillos", "33", "Pista 33 S", "N 5", "Ruta 5 Sur", "1, 2, 3", "a, b"],
    )
    def test_not_a_coordinate_falls_to_name(self, text):
        assert parse_query(text)["type"] == "name"

    def test_four_letter_word_is_oaci_but_keeps_the_name_for_fallback(self):
        parsed = parse_query("Lima")
        assert parsed["type"] == "oaci"
        assert parsed["name"] == "lima"

    def test_accented_name(self):
        assert parse_query("Aeródromo Tobalaba") == {
            "type": "name",
            "name": "aerodromo tobalaba",
        }


class TestNameScore:
    def test_ranking_exact_prefix_word_substring(self):
        assert name_score("tobalaba", "tobalaba") == 100
        assert name_score("tobal", "tobalaba ad") == 80
        assert name_score("cerrillos", "ad los cerrillos") == 60
        assert name_score("errill", "ad los cerrillos") == 40
        assert name_score("xyz", "ad los cerrillos") == 0
        assert (
            name_score("a", "a")
            > name_score("a", "ab")
            > name_score("a", "b a")
            > name_score("a", "xab")
        )

    def test_every_query_word_must_start_a_word(self):
        assert name_score("los cer", "ad los cerrillos") == 60
        assert name_score("los zzz", "ad los cerrillos") == 0

    def test_empty_never_matches(self):
        assert name_score("", "algo") == 0
        assert name_score("algo", "") == 0


class TestSearchIndex:
    ENTRIES = [
        {"name": "SCEL Ap Arturo Merino Benítez SANTIAGO", "code": "SCEL"},
        {"name": "SCTB Ad Eulogio Sánchez (Tobalaba) SANTIAGO", "code": "SCTB"},
        {"name": "Zona Restringida Cerrillos", "code": "SC - R 41"},
        {"name": "Zona Prohibida Palacio Pereira", "code": "SC-P30"},
        {"name": "Zona Peligrosa Tobalaba Norte", "code": "SC-D5"},
        {"name": "Ad Los Cerrillos", "code": "SCCC"},
        {"name": "Tobalaba Helipuerto", "code": "SCHP"},
    ]

    def names(self, outcome):
        return [r["entry"]["code"] for r in outcome["results"]]

    def test_oaci_exact_match(self):
        outcome = search_index("scel", self.ENTRIES)
        assert outcome["query"]["type"] == "oaci"
        assert self.names(outcome) == ["SCEL"]
        assert outcome["results"][0]["score"] == 100

    def test_zone_code_matches_whatever_way_the_index_wrote_it(self):
        outcome = search_index("r41", self.ENTRIES)
        assert self.names(outcome) == ["SC - R 41"]
        assert self.names(search_index("SC – P 30", self.ENTRIES)) == ["SC-P30"]

    def test_unknown_code_falls_back_to_name(self):
        # «Lima» no es un OACI del índice: se busca como nombre.
        entries = [{"name": "Hacienda Lima", "code": ""}]
        assert len(search_index("lima", entries)["results"]) == 1
        assert search_index("scxx", self.ENTRIES)["results"] == []

    def test_name_without_accents_and_ranked_prefix_over_word_over_substring(self):
        outcome = search_index("tobalaba", self.ENTRIES)
        assert outcome["query"]["type"] == "name"
        assert self.names(outcome) == ["SCHP", "SCTB", "SC-D5"]
        assert [r["score"] for r in outcome["results"]] == [80, 60, 60]

    def test_accents_and_case_are_ignored(self):
        assert self.names(search_index("BENITEZ", self.ENTRIES)) == ["SCEL"]
        assert self.names(search_index("sanchez", self.ENTRIES)) == ["SCTB"]

    def test_coordinate_returns_no_results_but_the_point(self):
        outcome = search_index("-33.45, -70.66", self.ENTRIES)
        assert outcome["results"] == []
        assert outcome["query"]["type"] == "coordinate"

    def test_invalid_and_empty(self):
        assert (
            search_index("-95, 0", self.ENTRIES)["query"]["type"]
            == "invalid_coordinate"
        )
        assert search_index("", self.ENTRIES)["results"] == []

    def test_limit_and_entries_without_fields(self):
        entries = [{"name": f"Zona {i}"} for i in range(30)] + [{}]
        assert len(search_index("zona", entries, limit=5)["results"]) == 5
        assert len(search_index("zona", entries)["results"]) == 20
