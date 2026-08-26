"""Corporate identity for generated documents (LV-144).

Facts, not layout: the palette, the typefaces, the footer line the company puts
on paper, and where the logo lives on disk. Deliberately imports **no** PDF
library, so a template tag, a spreadsheet writer or a test can read the same
values the letterhead draws without pulling reportlab in.

Both sources were supplied by the user on 2026-08-26:

* ``PANTONE Y TIPOGRAFIA.pdf`` -- the brand manual. Section 3.5 (palette) and
  section 3.2 (typography) are where every constant below comes from.
* ``Pie de firma.docx`` (2026 revision) -- the corporate signature block, which
  is where the legal name, address and site come from.

The proper nouns here are **not** marked for translation, and must not be: a
company name is the same in both languages, and marking it would put "J.E.J.
Ingenieria S.A." with its accent into the message catalog, where
``test_source_strings_are_written_in_english`` rejects accented source strings.
"""

from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.exceptions import ImproperlyConfigured

# -- Palette (brand manual, 3.5 "PALETA CROMATICA") -------------------------
#
# The two primaries and the three corporate neutrals, verbatim. No sixth
# colour gets added here: shades the reports need are *derived* with `tint()`
# below, so it stays obvious which values are the brand's and which are ours.
BLUE = "#1E418C"  # PANTONE 661 C -- the logo's own blue
CYAN = "#60C4F5"  # PANTONE 638 C
WHITE = "#FFFFFF"
GRAY_DARK = "#4D4D4D"  # COOL GRAY 11
GRAY_LIGHT = "#B3B3B3"  # COOL GRAY 4

# -- Typography (brand manual, 3.2 "TIPOGRAFIA CORPORATIVA") -----------------
#
# The manual specifies Helvetica in Light / Regular / Bold, chosen there for
# being available "en todos los formatos y software" -- which is exactly why it
# suits a PDF: Helvetica is one of reportlab's base-14 faces, so there is
# nothing to embed, ship or license. There is no Light in the base-14 set, so
# Light maps onto Regular; that is a downgrade in weight, not in typeface.
FONT_REGULAR = "Helvetica"
FONT_BOLD = "Helvetica-Bold"
FONT_ITALIC = "Helvetica-Oblique"

# -- Identity (2026 signature block) ----------------------------------------
LEGAL_NAME = "J.E.J. Ingeniería S.A."
ADDRESS = "Av. Apoquindo 2930 Piso 11, Las Condes, Santiago de Chile"
WEBSITE = "www.jej.cl"

# The signature template carries the phone as a per-person placeholder
# ("(56) Teléfono Fijo – Teléfono Celular"), so there is no corporate number to
# put here and none is invented.
FOOTER_LINE = f"{LEGAL_NAME} · {ADDRESS} · {WEBSITE}"

LOGO_STATIC_PATH = "img/jej-logo-blue.png"


def tint(hex_color, strength):
    """Return `hex_color` mixed with white; 1.0 is the colour, 0.0 is white.

    The manual defines five colours and no table-banding or rule tint, so the
    shades the reports need are derived from the palette here rather than
    written down beside it as if they were brand values too.
    """
    if not 0.0 <= strength <= 1.0:
        raise ValueError("strength must be between 0.0 and 1.0")
    raw = hex_color.lstrip("#")
    channels = (int(raw[i : i + 2], 16) for i in (0, 2, 4))
    mixed = (round(255 - (255 - channel) * strength) for channel in channels)
    return "#" + "".join(f"{value:02X}" for value in mixed)


# Derived, not brand: the hairline of a table grid and the banding of its rows.
GRID_TINT = tint(GRAY_LIGHT, 0.55)
BAND_TINT = tint(GRAY_LIGHT, 0.14)


@lru_cache(maxsize=1)
def logo_path():
    """Absolute path of the corporate logo on disk, or ``None`` if it is gone.

    **Read from disk, never through a URL.** In production ``STORAGES`` hashes
    static file names, so the asset does not exist under its source name in
    ``STATIC_ROOT`` and a ``{% static %}``-style URL would additionally need a
    live server to answer its own request. ``finders.find()`` covers both
    environments -- it searches ``STATICFILES_DIRS`` and the app static dirs,
    which the deploy checks out -- and the two fallbacks cover a settings
    layout where the finders are not usable.

    Returns ``None`` instead of raising: a missing brand asset must not take a
    compliance report down with it, and the letterhead draws the legal name in
    the logo's place.

    Cached per process. A test that moves the asset or overrides the static
    settings has to call ``logo_path.cache_clear()``.
    """
    candidates = []
    try:
        candidates.append(finders.find(LOGO_STATIC_PATH))
    except (ImproperlyConfigured, OSError, ValueError):
        pass
    base_dir = getattr(settings, "BASE_DIR", None)
    if base_dir:
        candidates.append(Path(base_dir) / "static" / LOGO_STATIC_PATH)
    static_root = getattr(settings, "STATIC_ROOT", None)
    if static_root:
        candidates.append(Path(static_root) / LOGO_STATIC_PATH)

    for candidate in candidates:
        if not candidate:
            continue
        try:
            path = Path(candidate)
            if path.is_file():
                return path
        except OSError:
            continue
    return None
