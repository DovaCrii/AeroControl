"""Compile checked-in Django translation catalogs without a system gettext install."""

from pathlib import Path

import polib


def main():
    for catalog in Path("locale").glob("*/LC_MESSAGES/*.po"):
        polib.pofile(str(catalog)).save_as_mofile(str(catalog.with_suffix(".mo")))


if __name__ == "__main__":
    main()
