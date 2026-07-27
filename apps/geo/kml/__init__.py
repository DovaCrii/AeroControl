"""KML/KMZ interpretation for BLOQUE GEO.

Pure-Python, no HTTP: importing bytes produces the canonical "AeroKML JSON"
document (see docs/dev/geo-editor-plan.md). The generator (canonical -> KML)
lands in GEO-3.
"""

from .errors import KmlError, KmlImportError
from .loader import parse_upload

__all__ = ["KmlError", "KmlImportError", "parse_upload"]
