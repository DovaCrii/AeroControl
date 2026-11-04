"""LV-406: descarga la imagen característica de SIGO y SIPA para las tarjetas del panel.

Cada enlace de `apps/core/official_links.py` trae la URL de su imagen (`source_image_url`). Este
comando la baja con las mismas protecciones que cualquier descarga oficial (sólo `https`, host de
`OFFICIAL_LINK_IMAGE_ALLOWED_HOSTS`, anti-SSRF, tope de bytes y de tiempo), la normaliza a WebP sin
metadatos y la guarda en el almacenamiento privado. No va nada al repositorio.

Idempotente: sin `--force` sólo toca los enlaces que aún no tienen imagen activa. Un fallo en un
enlace no impide los demás; si alguno falló, el comando termina con error al final para que se note.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.compliance.storage import DocumentStorageError
from apps.core.models import OfficialLinkImage
from apps.core.official_images import (
    OfficialImageError,
    discard_image,
    fetch_image,
    normalize_image,
    store_image,
)
from apps.core.official_links import OFFICIAL_LINKS


class Command(BaseCommand):
    help = "Download the official image of each DGAC system (SIGO, SIPA) for the panel cards."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Download again even the links that already have an active image.",
        )

    def handle(self, *args, **options):
        failed = []
        for link in OFFICIAL_LINKS:
            key = link["key"]
            current = OfficialLinkImage.objects.filter(link_key=key).first()
            if current is not None and current.is_active and not options["force"]:
                self.stdout.write(f"{key}: already loaded, skipped")
                continue
            try:
                self._load(link, current)
            except (OfficialImageError, DocumentStorageError, OSError) as exc:
                failed.append(key)
                self.stderr.write(f"{key}: ERROR {exc}")
            else:
                self.stdout.write(self.style.SUCCESS(f"{key}: ok"))
        if failed:
            raise CommandError("Could not load: " + ", ".join(failed))

    def _load(self, link, current):
        url = link["source_image_url"]
        data, host = fetch_image(url, settings.OFFICIAL_LINK_IMAGE_ALLOWED_HOSTS)
        storage_key = store_image("official-links", normalize_image(data))
        previous_key = current.storage_key if current is not None else ""
        OfficialLinkImage.objects.update_or_create(
            link_key=link["key"],
            defaults={
                "storage_key": storage_key,
                "source_url": url,
                "source_host": host,
                "is_active": True,
            },
        )
        if previous_key and previous_key != storage_key:
            discard_image(previous_key)
