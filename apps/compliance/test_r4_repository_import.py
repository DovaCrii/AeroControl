"""R4.1/R4.1a/R4.4/R4.5: the importer's classification logic is pure and
runs without a filesystem or a database -- verified against the real folder
names and PII filenames found in `Z:` 2026-08-10 (see MASTER_PLAN.md R4)."""

from apps.compliance.repository_import import (
    OK,
    REVIEW_NO_MATCH,
    REVIEW_SENSITIVE,
    SKIP_FORMAT,
    AircraftRef,
    classify_file_format,
    is_sensitive_filename,
    match_aircraft_folders,
    parse_aircraft_folder_name,
    subfolder_doc_type_code,
)


def test_parses_a_folder_name_with_a_plain_model():
    assert parse_aircraft_folder_name("CC633-1581F5FHC245700D181D-M3E") == (
        "CC633",
        "1581F5FHC245700D181D",
        "M3E",
    )


def test_parses_a_folder_name_whose_model_contains_a_space():
    assert parse_aircraft_folder_name("CC706-1581F5FHC245800DWTY6-M3E RTK") == (
        "CC706",
        "1581F5FHC245800DWTY6",
        "M3E RTK",
    )


def test_rejects_a_folder_name_without_three_segments():
    assert parse_aircraft_folder_name("DOCUMENTOS BASES") is None
    assert parse_aircraft_folder_name("CC633-onlytwo") is None


def test_subfolder_doc_type_ignores_the_singular_plural_variant():
    assert subfolder_doc_type_code("04.- Mantenciones") == "maintenance-certificate"
    assert subfolder_doc_type_code("04.- Mantención") == "maintenance-certificate"


def test_subfolder_doc_type_is_none_for_an_unrecognized_prefix():
    assert subfolder_doc_type_code("06.- Algo nuevo") is None


def test_classify_file_format_skips_rar_zip_and_kmz():
    assert classify_file_format("TOVE.kmz") == SKIP_FORMAT
    assert classify_file_format("respaldo.rar") == SKIP_FORMAT
    assert classify_file_format("respaldo.zip") == SKIP_FORMAT


def test_classify_file_format_flags_a_real_pii_filename_as_sensitive():
    assert (
        classify_file_format("Transferencias de Fondos de Alguien.msg")
        == REVIEW_SENSITIVE
    )
    assert (
        classify_file_format("04 Cedula de identidad Act MCJ.pdf") == REVIEW_SENSITIVE
    )
    assert classify_file_format("Escritura publica poderes.pdf") == REVIEW_SENSITIVE
    assert (
        classify_file_format("01_691 Comprobante-TEF_IPE2507141537.pdf")
        == REVIEW_SENSITIVE
    )


def test_classify_file_format_accepts_an_ordinary_pdf():
    assert classify_file_format("RES. EX. 0537(210426).pdf") == OK


def test_is_sensitive_filename_does_not_false_hit_on_a_substring():
    # "rut" must not match inside an unrelated word.
    assert not is_sensitive_filename("Brutalidad de vuelo.pdf")
    assert not is_sensitive_filename("Poliza_0020099470-21147.pdf")


def test_is_sensitive_filename_is_accent_insensitive():
    assert is_sensitive_filename("Cédula de identidad.pdf")


def test_match_aircraft_folders_matches_by_exact_serial():
    aircraft = AircraftRef(
        id="a1", registration="RPA-9001", serial_number="ABC123", cost_center_code="CC1"
    )
    [result] = match_aircraft_folders(["CC1-ABC123-M3E"], [aircraft])

    assert result.status == OK
    assert result.aircraft == aircraft


def test_match_aircraft_folders_does_not_match_across_a_cost_center_difference():
    # RPA-2019: app has it under CC110, the Z: folder is under CC717 --
    # the serial still matches, and that is enough (the CC prefix is
    # informational, not part of the match key).
    aircraft = AircraftRef(
        id="a1",
        registration="RPA-2019",
        serial_number="1ZNBJ8300C00P1",
        cost_center_code="CC110",
    )
    [result] = match_aircraft_folders(["CC717-1ZNBJ8300C00P1-M300"], [aircraft])

    assert result.status == OK
    assert result.aircraft == aircraft


def test_match_aircraft_folders_never_uses_fuzzy_matching():
    # RPA-4647: the app has "...246B00D7WPK" (zeros); the real Z: folder
    # has "...246BOOD7WPK" ("OO"). No substitution logic should paper over
    # this -- it must come back unmatched, not silently attached.
    aircraft = AircraftRef(
        id="a1",
        registration="RPA-4647",
        serial_number="1581F5FHC246B00D7WPK",
        cost_center_code="CC684",
    )
    [result] = match_aircraft_folders(["CC684-1581F5FHC246BOOD7WPK-M3E"], [aircraft])

    assert result.status == REVIEW_NO_MATCH
    assert result.aircraft is None


def test_match_aircraft_folders_hints_at_the_only_unmatched_aircraft_in_the_same_cost_center():
    aircraft = AircraftRef(
        id="a1",
        registration="RPA-4647",
        serial_number="1581F5FHC246B00D7WPK",
        cost_center_code="CC684",
    )
    [result] = match_aircraft_folders(["CC684-1581F5FHC246BOOD7WPK-M3E"], [aircraft])

    assert result.hint == "near:RPA-4647"


def test_match_aircraft_folders_gives_no_hint_when_several_aircraft_could_fit():
    unmatched_a = AircraftRef(
        id="a1", registration="RPA-1", serial_number="AAA", cost_center_code="CC1"
    )
    unmatched_b = AircraftRef(
        id="a2", registration="RPA-2", serial_number="BBB", cost_center_code="CC1"
    )
    [result] = match_aircraft_folders(["CC1-ZZZ-M3E"], [unmatched_a, unmatched_b])

    assert result.status == REVIEW_NO_MATCH
    assert result.hint is None


def test_match_aircraft_folders_reports_an_orphan_folder_with_no_hint():
    # CC633's "M3E Revisión" folder: no aircraft anywhere has this serial.
    [result] = match_aircraft_folders(["CC633-1581F5FHD231500C2Z48-M3E Revisión"], [])

    assert result.status == REVIEW_NO_MATCH
    assert result.hint is None
