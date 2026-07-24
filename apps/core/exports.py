"""Shared helpers for tabular exports."""

FORMULA_PREFIXES = ("=", "+", "-", "@")


def neutralize(value):
    """Return a spreadsheet-safe string for an exported cell.

    Excel and LibreOffice execute a cell whose text starts with =, +, - or @,
    so a value copied out of a user-editable field could run on open. Prefixing
    an apostrophe keeps the text visible and inert. AGENTS.md requires this on
    every export.
    """
    if value is None:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    text = str(value)
    return f"'{text}" if text.startswith(FORMULA_PREFIXES) else text
