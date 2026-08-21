"""Safe extraction of the main KML and resource names from a KMZ (a ZIP).

A KMZ is attacker-controlled input the moment we open it. Every guard here
exists because the ZIP header cannot be trusted: entry counts, declared sizes
and names are all verified against hard limits, in memory, before any bytes are
handed on. Nothing is ever written to disk.
"""

import io
import zipfile

from .errors import KmlImportError

MAX_ENTRIES = 200
MAX_ENTRY_BYTES = 50 * 1024 * 1024
MAX_TOTAL_BYTES = 120 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100


def _reject_unsafe_name(name):
    # Never extract to disk, but a traversal name is still a red flag and some
    # names are outright invalid.
    if not name or name.endswith("/"):
        return  # directory entry, ignored later
    if name.startswith(("/", "\\")) or ".." in name.replace("\\", "/").split("/"):
        raise KmlImportError("The KMZ contains an unsafe entry name.")
    if "\\" in name or "\x00" in name:
        raise KmlImportError("The KMZ contains an unsafe entry name.")


def build_kmz(kml_bytes, *, kml_name="doc.kml"):
    """Empaquetar KML en un KMZ mínimo: un ZIP con `doc.kml` adentro.

    R9.1: la contraparte de `read_kmz`, para los KMZ de sección que se generan
    hacia SIGO. Sin recursos embebidos a propósito — una sección es un punto y
    su circunferencia, y todo lo demás del archivo madre (iconos, estilos) es
    contenido ajeno que no viaja a un formulario del Estado. `doc.kml` es el
    nombre que Google Earth y el propio `_pick_main_kml` de este módulo buscan
    primero, así que lo que se escribe acá se puede releer con `read_kmz`.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(kml_name, kml_bytes)
    return buffer.getvalue()


def read_kmz(data):
    """Return (main_kml_bytes, resource_names) from KMZ bytes.

    resource_names lists the non-KML files (icons, imagery) by name only; they
    are copied byte-for-byte from the original at export time, never stored.
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise KmlImportError("The file is not a valid KMZ archive.") from exc

    entries = archive.infolist()
    if len(entries) > MAX_ENTRIES:
        raise KmlImportError(
            f"The KMZ has {len(entries)} entries; the limit is {MAX_ENTRIES}."
        )

    total = 0
    for info in entries:
        _reject_unsafe_name(info.filename)
        if info.is_dir():
            continue
        if info.file_size > MAX_ENTRY_BYTES:
            raise KmlImportError("A KMZ entry exceeds the per-file size limit.")
        if info.compress_size > 0:
            ratio = info.file_size / info.compress_size
            if ratio > MAX_COMPRESSION_RATIO:
                raise KmlImportError("A KMZ entry has a suspicious compression ratio.")
        total += info.file_size
        if total > MAX_TOTAL_BYTES:
            raise KmlImportError("The KMZ decompresses to more than the size limit.")

    main = _pick_main_kml(entries)
    if main is None:
        raise KmlImportError("The KMZ does not contain a root .kml document.")

    main_bytes = _read_verified(archive, main)
    resources = [
        info.filename
        for info in entries
        if not info.is_dir() and info.filename != main.filename
    ]
    return main_bytes, resources


def read_kmz_resource(data, name):
    """Return the bytes of one named entry from KMZ bytes, guarded.

    Used to serve an embedded icon/image (GEO-13). The caller must have already
    checked `name` against the version's stored resource whitelist; this still
    re-applies the importer's zip guards because a stored file is
    attacker-controlled input and could have been tampered with. Returns None
    when the entry is absent (best-effort, like the export copy).
    """
    _reject_unsafe_name(name)
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise KmlImportError("The file is not a valid KMZ archive.") from exc

    entries = archive.infolist()
    if len(entries) > MAX_ENTRIES:
        raise KmlImportError(
            f"The KMZ has {len(entries)} entries; the limit is {MAX_ENTRIES}."
        )
    for info in entries:
        if info.is_dir() or info.filename != name:
            continue
        if info.file_size > MAX_ENTRY_BYTES:
            raise KmlImportError("A KMZ entry exceeds the per-file size limit.")
        if info.compress_size > 0:
            ratio = info.file_size / info.compress_size
            if ratio > MAX_COMPRESSION_RATIO:
                raise KmlImportError("A KMZ entry has a suspicious compression ratio.")
        return _read_verified(archive, info)
    return None


def _pick_main_kml(entries):
    """First root-level .kml, preferring doc.kml (Google Earth's convention)."""
    root_kml = [
        info
        for info in entries
        if not info.is_dir()
        and "/" not in info.filename
        and info.filename.lower().endswith(".kml")
    ]
    if not root_kml:
        return None
    for info in root_kml:
        if info.filename.lower() == "doc.kml":
            return info
    return root_kml[0]


def _read_verified(archive, info):
    """Read one entry, confirming it does not exceed its declared size.

    A zip bomb lies in the header, so read one byte past the declared size and
    reject if more comes out.
    """
    limit = info.file_size
    with archive.open(info) as handle:
        payload = handle.read(limit + 1)
    if len(payload) > limit:
        raise KmlImportError("A KMZ entry is larger than its declared size.")
    return payload
