from django.core.management.base import BaseCommand
from django.db import transaction

from apps.workboard.models import KanbanBoard, KanbanLabel, KanbanStage

BOARD_NAME = "Cumplimiento DGAC"

STAGES = [
    ("Por vencer", "pending", "#64748B"),
    ("Recopilando antecedentes", "in_progress", "#3B82F6"),
    ("Enviado a DGAC", "in_progress", "#F59E0B"),
    ("Observado", "blocked", "#EF4444"),
    ("Aprobado", "completed", "#10B981"),
    ("Archivado", "completed", "#6B7280"),
]

LABELS = [
    ("Credencial", "#2EC4B6"),
    ("Permiso de vuelo", "#3B82F6"),
    ("Inscripción aeronave", "#8B5CF6"),
    ("Seguro", "#F59E0B"),
    ("Habilitación", "#10B981"),
]


class Command(BaseCommand):
    help = "Create the 'Cumplimiento DGAC' Kanban board with its stages and labels."

    @transaction.atomic
    def handle(self, *args, **options):
        board, created = KanbanBoard.objects.get_or_create(name=BOARD_NAME)
        for order, (name, status_type, color) in enumerate(STAGES):
            KanbanStage.objects.get_or_create(
                board=board,
                name=name,
                defaults={"status_type": status_type, "color": color, "order": order},
            )
        for order, (name, color) in enumerate(LABELS):
            KanbanLabel.objects.get_or_create(
                board=board,
                name=name,
                defaults={"color": color, "order": order},
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"{'Created' if created else 'Ensured'} board '{BOARD_NAME}' "
                f"with {len(STAGES)} stages and {len(LABELS)} labels."
            )
        )
