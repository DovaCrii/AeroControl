"""Entry point: raw upload bytes -> validated canonical document."""

from pathlib import Path

from . import canonical
from .errors import KmlImportError
from .kmz import read_kmz
from .parse import parse_kml_bytes


def parse_upload(data, filename):
    """Parse a .kml or .kmz upload into a validated canonical document.

    For KMZ the main KML is parsed and the embedded resource names are recorded
    (the files themselves stay in the original, copied at export). Raises
    KmlImportError on anything malformed or over a safety limit.
    """
    suffix = Path(filename).suffix.lower()
    if suffix == ".kmz":
        kml_bytes, resources = read_kmz(data)
        document = parse_kml_bytes(kml_bytes)
        document["kmz_resources"] = resources
    elif suffix == ".kml":
        document = parse_kml_bytes(data)
    else:
        raise KmlImportError("Only .kml and .kmz files can be imported.")

    canonical.validate_document(document)
    return document
