from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.compliance.models import Document
from apps.compliance.storage import DocumentStorageError, get_document_storage


class Command(BaseCommand):
    help = "List or remove files for archived documents past the retention window."

    def add_arguments(self, parser):
        parser.add_argument("--older-than-days", type=int, default=3650)
        parser.add_argument("--execute", action="store_true")

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=options["older_than_days"])
        storage = get_document_storage()
        documents = Document.objects.filter(
            is_active=False, updated_at__lt=cutoff
        ).exclude(file_path="")
        for document in documents.iterator():
            try:
                exists = storage.exists(document.file_path)
            except DocumentStorageError:
                exists = False
            if not exists:
                self.stdout.write(f"Skipped unsafe or missing path: {document.pk}")
                continue
            # ⚠️ LV-200 paso 2: **un archivo puede pertenecer a más de un
            # documento**, y sin esta comprobación este trabajo borraría el papel
            # de un registro vivo.
            #
            # Desde que la misma carta puede servir a varios permisos, la fila
            # nueva apunta al `file_path` que ya existía en vez de guardar una
            # copia. Así que archivar una de esas filas y limpiarla **no** puede
            # llevarse el archivo: el otro permiso sigue necesitándolo, y esto
            # corre con diez años de retención, cuando nadie recuerda que dos
            # registros compartían un papel.
            #
            # Es la clase de pérdida que no avisa: la fila viva conserva su
            # `file_path`, el expediente sigue mostrando el renglón en verde, y el
            # archivo ya no está. Se descubriría al intentar abrirlo, quizá en una
            # auditoría.
            shared_with = (
                Document.objects.filter(file_path=document.file_path, is_active=True)
                .exclude(pk=document.pk)
                .count()
            )
            if shared_with:
                self.stdout.write(
                    f"Kept (shared with {shared_with} active document"
                    f"{'s' if shared_with > 1 else ''}): {document.file_path}"
                )
                continue
            self.stdout.write(
                f"{'Removing' if options['execute'] else 'Would remove'}: {document.file_path}"
            )
            if options["execute"]:
                storage.delete(document.file_path)
                document.file_path = ""
                document.save(update_fields=["file_path", "updated_at"])
