"""LV-399: imágenes oficiales que quien administra carga una vez y la app sirve internamente.

Dos usos comparten este servicio: la foto del fabricante por **modelo** de aeronave
(`registry.AircraftModelImage`) y el banner de los sistemas DGAC del panel
(`core.OfficialLinkImage`). Ninguna va al repositorio —es material de terceros y el repo es
público—: se guardan en el almacenamiento de documentos (`DOCUMENTS_DIR` o S3 privado) y se
sirven por una vista propia, con sesión, así que el CSP sigue sin admitir imágenes ajenas.

**La descarga desde una URL es una petición que el servidor hace por cuenta de alguien**, y
por eso es la parte con más reglas (anti-SSRF):

- sólo `https`, puerto estándar, sin usuario ni contraseña en la dirección;
- el host tiene que estar en la lista permitida del uso (el host o un subdominio suyo);
- el nombre se resuelve **una vez** y se rechaza si cualquiera de sus direcciones es privada,
  local, de enlace local, multicast o reservada (IPv4 e IPv6, incluida la IPv4 mapeada);
- la conexión va **a la dirección ya comprobada** (con el nombre en el SNI y el certificado),
  así que un DNS que cambie de respuesta entre la comprobación y la conexión no lleva a otro
  lado;
- no sigue redirecciones: una 3xx se rechaza y se pide la dirección final;
- tope de bytes leyendo por trozos, y tiempo límite por operación y total.

Lo que llega —subido o descargado— se valida **por contenido** con Pillow (JPEG, PNG o WebP,
nada más), y se re-codifica a WebP de hasta ~300 KB **desde los píxeles**, de modo que no
sobrevive ningún metadato (EXIF, GPS, perfil ICC, XMP).
"""

from __future__ import annotations

import http.client
import io
import ipaddress
import socket
import ssl
import time
import urllib.parse
import uuid
from contextlib import suppress

from django.conf import settings
from django.http import Http404, HttpResponse
from django.utils.translation import gettext as _
from PIL import Image, ImageOps, UnidentifiedImageError

ALLOWED_FORMATS = frozenset({"JPEG", "PNG", "WEBP"})
CONTENT_TYPE = "image/webp"
TARGET_BYTES = 300 * 1024
MAX_SIDE = 1600
# Un PNG de pocos KB puede declarar 50 000 × 50 000 píxeles: se rechaza antes de decodificar.
MAX_PIXELS = 40_000_000
READ_CHUNK = 64 * 1024
STORAGE_PREFIX = "official-images"


class OfficialImageError(Exception):
    """Un motivo legible para la persona: se muestra tal cual junto al formulario."""


def host_is_allowed(host, allowed_hosts):
    """`host` es uno de la lista o un subdominio de alguno (nunca un sufijo suelto)."""
    host = (host or "").lower().rstrip(".")
    if not host:
        return False
    for entry in allowed_hosts:
        entry = entry.lower().strip().rstrip(".")
        if entry and (host == entry or host.endswith("." + entry)):
            return True
    return False


def check_url(url, allowed_hosts):
    """La URL partida y su host, o `OfficialImageError` con el motivo."""
    parsed = urllib.parse.urlsplit((url or "").strip())
    if parsed.scheme.lower() != "https":
        raise OfficialImageError(_("Only https addresses are accepted."))
    if parsed.username or parsed.password:
        raise OfficialImageError(
            _("The address must not include a user name or password.")
        )
    host = parsed.hostname or ""
    if not host or not host.isascii():
        raise OfficialImageError(_("The address has no valid host."))
    try:
        port = parsed.port
    except ValueError as exc:
        raise OfficialImageError(_("The address has no valid host.")) from exc
    if port not in (None, 443):
        raise OfficialImageError(_("Only the standard https port is accepted."))
    if not host_is_allowed(host, allowed_hosts):
        raise OfficialImageError(
            _("The host %(host)s is not on the list of allowed sources.")
            % {"host": host}
        )
    return parsed, host


def _resolve(host):
    """Las direcciones del nombre. Aparte para que las pruebas lo sustituyan."""
    return {
        info[4][0] for info in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    }


def is_public_address(raw):
    ip = ipaddress.ip_address(str(raw).split("%", 1)[0])
    if ip.version == 6 and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or not ip.is_global
    )


def public_address(host):
    """Una dirección pública del host, o error si **cualquiera** de las suyas no lo es."""
    try:
        addresses = _resolve(host)
    except (OSError, UnicodeError) as exc:
        raise OfficialImageError(_("The host could not be resolved.")) from exc
    if not addresses:
        raise OfficialImageError(_("The host could not be resolved."))
    for address in addresses:
        try:
            public = is_public_address(address)
        except ValueError as exc:
            raise OfficialImageError(_("The host could not be resolved.")) from exc
        if not public:
            raise OfficialImageError(
                _("The address points to a private or local network.")
            )
    # IPv4 primero: el servidor puede no tener salida IPv6, y el orden del texto no sirve.
    return min(addresses, key=lambda address: (":" in address, address))


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS a una dirección ya comprobada, con el nombre en el SNI y en el certificado."""

    def __init__(self, host, address, *, timeout):
        super().__init__(
            host, 443, timeout=timeout, context=ssl.create_default_context()
        )
        self._pinned_address = address

    def connect(self):
        sock = socket.create_connection((self._pinned_address, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def _open(host, address, target, timeout):
    """La respuesta HTTP (sin seguir redirecciones: `http.client` no lo hace)."""
    connection = _PinnedHTTPSConnection(host, address, timeout=timeout)
    try:
        connection.request(
            "GET",
            target,
            headers={
                "Accept": "image/webp,image/png,image/jpeg",
                "User-Agent": "AeroControl official-image fetch",
            },
        )
        response = connection.getresponse()
    except Exception:
        connection.close()
        raise
    response.release = connection.close
    return response


def _too_big(max_bytes):
    return OfficialImageError(
        _("The image exceeds the maximum size of %(size)s MB.")
        % {"size": round(max_bytes / (1024 * 1024), 1)}
    )


def fetch_image(url, allowed_hosts, *, max_bytes=None, timeout=None):
    """`(bytes, host)` de la imagen en `url`, con todas las reglas del encabezado."""
    max_bytes = max_bytes or settings.OFFICIAL_IMAGE_MAX_BYTES
    timeout = timeout or settings.OFFICIAL_IMAGE_TIMEOUT_SECONDS
    parsed, host = check_url(url, allowed_hosts)
    address = public_address(host)
    target = parsed.path or "/"
    if parsed.query:
        target = f"{target}?{parsed.query}"
    deadline = time.monotonic() + timeout
    try:
        response = _open(host, address, target, timeout)
    except (OSError, http.client.HTTPException) as exc:
        raise OfficialImageError(_("The image could not be downloaded.")) from exc
    chunks, total = [], 0
    try:
        if 300 <= response.status < 400:
            raise OfficialImageError(
                _(
                    "The address redirects to another one. Paste the final address of the image."
                )
            )
        if response.status != 200:
            raise OfficialImageError(
                _("The server answered with status %(status)s.")
                % {"status": response.status}
            )
        length = response.getheader("Content-Length") or ""
        if length.isdigit() and int(length) > max_bytes:
            raise _too_big(max_bytes)
        while True:
            if time.monotonic() > deadline:
                raise OfficialImageError(_("The download took too long."))
            # `read1` devuelve lo que ya llegó: con `read` un goteo lento esquivaría el plazo.
            chunk = response.read1(READ_CHUNK)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise _too_big(max_bytes)
            chunks.append(chunk)
    except (OSError, http.client.HTTPException) as exc:
        raise OfficialImageError(_("The image could not be downloaded.")) from exc
    finally:
        response.close()
        release = getattr(response, "release", None)
        if release is not None:
            release()
    return b"".join(chunks), host


def read_upload(uploaded, *, max_bytes=None):
    """Los bytes de un archivo subido, con el mismo tope que la descarga."""
    max_bytes = max_bytes or settings.OFFICIAL_IMAGE_MAX_BYTES
    if uploaded.size is not None and uploaded.size > max_bytes:
        raise _too_big(max_bytes)
    uploaded.seek(0)
    data = uploaded.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise _too_big(max_bytes)
    return data


def normalize_image(data):
    """WebP de hasta ~300 KB, re-codificado desde los píxeles (sin metadatos)."""
    invalid = OfficialImageError(
        _("The file is not a valid image. Use a JPEG, PNG or WebP image.")
    )
    if not data:
        raise invalid
    try:
        with Image.open(io.BytesIO(data)) as probe:
            if probe.format not in ALLOWED_FORMATS:
                raise invalid
            width, height = probe.size
            if width * height > MAX_PIXELS:
                raise OfficialImageError(_("The image has too many pixels."))
            probe.verify()
        with Image.open(io.BytesIO(data)) as source:
            source.load()
            upright = ImageOps.exif_transpose(source)
            has_alpha = upright.mode in ("RGBA", "LA", "PA") or (
                upright.mode == "P" and "transparency" in upright.info
            )
            mode = "RGBA" if has_alpha else "RGB"
            converted = upright.convert(mode)
    except OfficialImageError:
        raise
    except (
        UnidentifiedImageError,
        Image.DecompressionBombError,
        OSError,
        SyntaxError,
        ValueError,
    ) as exc:
        raise invalid from exc
    # Una imagen nueva hecha sólo de píxeles: nada de `info` (EXIF, ICC, XMP) pasa al WebP.
    pixels = Image.frombytes(mode, converted.size, converted.tobytes())
    encoded = b""
    for side in (MAX_SIDE, 1280, 1024, 800, 640):
        candidate = pixels.copy()
        candidate.thumbnail((side, side))
        for quality in (82, 72, 62, 50):
            buffer = io.BytesIO()
            candidate.save(buffer, "WEBP", quality=quality, method=4)
            encoded = buffer.getvalue()
            if len(encoded) <= TARGET_BYTES:
                return encoded
    return encoded


def store_image(folder, data):
    """Guarda el WebP en el almacenamiento de documentos y devuelve su clave."""
    from apps.compliance.storage import get_document_storage

    key = f"{STORAGE_PREFIX}/{folder}/{uuid.uuid4().hex}.webp"
    buffer = io.BytesIO(data)
    buffer.content_type = CONTENT_TYPE
    get_document_storage().save(key, buffer)
    return key


def discard_image(key):
    """Borra un archivo reemplazado. Si falla queda huérfano, que no rompe nada."""
    from apps.compliance.storage import DocumentStorageError, get_document_storage

    if key:
        with suppress(DocumentStorageError, OSError):
            get_document_storage().delete(key)


def image_response(key):
    """La imagen guardada, con su tipo y caché privada (la URL cambia al reemplazarla)."""
    from apps.compliance.storage import (
        DocumentStorageError,
        DocumentStorageNotFound,
        get_document_storage,
    )

    try:
        handle = get_document_storage().open(key)
    except (DocumentStorageNotFound, DocumentStorageError) as exc:
        raise Http404 from exc
    try:
        data = handle.read()
    finally:
        handle.close()
    response = HttpResponse(data, content_type=CONTENT_TYPE)
    response["Cache-Control"] = "private, max-age=86400"
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Disposition"] = 'inline; filename="official-image.webp"'
    return response


def load_image(*, uploaded=None, url="", allowed_hosts=()):
    """`(webp, host)` desde un archivo subido o una URL. `host` vacío si se subió."""
    if uploaded is not None:
        return normalize_image(read_upload(uploaded)), ""
    data, host = fetch_image(url, allowed_hosts)
    return normalize_image(data), host
