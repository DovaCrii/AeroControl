"""X.1: Aircraft.serial_number is the only key present in all three worlds
(DJI, the Z: folder names, the DGAC registry) and a DJI serial never
contains whitespace. Production has 2 real aircraft with a stray internal
space typed into the field -- confirmed against the Z: folder names, which
carry the actual serial. Normalize on save so the field is trustworthy
before any `unique` constraint is imposed on it."""

import pytest

from apps.registry.models import Aircraft


@pytest.mark.django_db
def test_save_strips_an_internal_space_from_the_serial_number():
    aircraft = Aircraft.objects.create(
        registration="RPA-9001",
        type="Multirotor",
        model="M3E",
        manufacturer="DJI",
        serial_number="1581F5FHC245700 D181D",
    )

    assert aircraft.serial_number == "1581F5FHC245700D181D"


@pytest.mark.django_db
def test_save_strips_leading_and_trailing_whitespace_from_the_serial_number():
    aircraft = Aircraft.objects.create(
        registration="RPA-9002",
        type="Multirotor",
        model="M3E",
        manufacturer="DJI",
        serial_number="  1581F5FHD23AL00D0P51  ",
    )

    assert aircraft.serial_number == "1581F5FHD23AL00D0P51"


@pytest.mark.django_db
def test_save_leaves_a_clean_serial_number_untouched():
    aircraft = Aircraft.objects.create(
        registration="RPA-9003",
        type="Multirotor",
        model="M3E",
        manufacturer="DJI",
        serial_number="1581F5FHC246B00D7WPK",
    )

    assert aircraft.serial_number == "1581F5FHC246B00D7WPK"


@pytest.mark.django_db
def test_save_leaves_a_blank_serial_number_untouched():
    aircraft = Aircraft.objects.create(
        registration="RPA-9004",
        type="Multirotor",
        model="M3E",
        manufacturer="DJI",
    )

    assert aircraft.serial_number == ""
