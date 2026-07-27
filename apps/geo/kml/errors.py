"""Errors raised while interpreting user-supplied KML/KMZ.

KmlImportError is the one the import view catches and turns into a translatable
form error; its message is safe to show (it never echoes file contents).
"""


class KmlError(Exception):
    """Base class for KML/KMZ handling errors."""


class KmlImportError(KmlError):
    """A KML/KMZ upload could not be interpreted or violated a safety guard."""
