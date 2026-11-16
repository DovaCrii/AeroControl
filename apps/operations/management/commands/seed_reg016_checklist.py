"""LV-441: sembrar la lista de chequeo prevuelo del REG-016 Rev. 2, sección 4.

La Actualización 19 del Manual de Operaciones introduce el «Registro Único de
Misión» (JEJ-GTE-CT-REG-016 Rev. 2). Su sección 4 es la verificación en terreno:
17 ítems, con los críticos marcados ★. Se siembran como una `PreflightChecklist`
sin palabras clave (aplica a toda aeronave) y los ★ como `is_required`: un
punto crítico no se puede dejar en «no aplica».

Idempotente: la lista se busca por nombre y cada ítem por `order` dentro de la
lista. Una corrida posterior **no pisa** un texto que alguien editó en el admin,
y renombrar la lista en el admin haría que se creara otra: no renombrar.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.operations.models import PreflightChecklist, PreflightChecklistItem

CHECKLIST_NAME = "REG-016 Rev. 2 · Verificación prevuelo (sección 4)"

POPULATED = " (solo área poblada)"

# (order, text, critical). Textos del REG-016 Rev. 2, sección 4.
# Los ítems 14-16 («solo área poblada») son ★ en el formulario pero se siembran
# con is_required=False: la Act. 19 mantiene la operación sólo en área no poblada
# hasta la Act. 20, así que hoy no aplican y no deben bloquear la firma.
# Condición para volverlos obligatorios: que la Act. 20 habilite el área poblada;
# entonces pasar a True (en el admin, o con un nuevo seed/migración de datos).
ITEMS = [
    (
        1,
        "Meteorología dentro de límites del fabricante y VMC (viento, visibilidad, lluvia)",
        True,
    ),
    (2, "NOTAM revisados y sin restricción para el lugar y la hora", True),
    (
        3,
        "Obstáculos identificados (cables y torres de alta tensión, árboles, edificios, aves)",
        True,
    ),
    (4, "Personas ajenas fuera del área de vuelo y acceso controlado", True),
    (
        5,
        "Zona de despegue con lona y 4 conos; extintor y botiquín disponibles",
        True,
    ),
    (6, "Briefing a la tripulación: roles, ruta de aborto y emergencias", True),
    (7, "Hélices instaladas, correctas y sin daño", True),
    (8, "Batería asegurada, con carga y temperatura verificadas", True),
    (
        9,
        "Brazos, compartimientos, cámara/gimbal y tarjeta de memoria asegurados",
        True,
    ),
    (10, "Control remoto: enlace, carga, antenas y modo manual disponible", True),
    (11, "Señal GPS suficiente y punto de inicio (Home) registrado", True),
    (
        12,
        "Retorno a casa fijado sobre el obstáculo más alto; geocerca y altura máx. 120 m",
        True,
    ),
    (
        13,
        "Documentos de la operación portados (registro, credencial, seguro, permiso SIGO, AOC)",
        True,
    ),
    (
        14,
        "Paracaídas de emergencia instalado, sin daños y con N° de serie registrado"
        + POPULATED,
        False,
    ),
    (
        15,
        "Despegue, vuelo y aterrizaje en modo manual (no se usa modo automático en área poblada)"
        + POPULATED,
        False,
    ),
    (
        16,
        "Separación de 30 m horizontales y 20 m verticales con personas, obstáculos e infraestructura"
        + POPULATED,
        False,
    ),
    (
        17,
        "Observador designado con credencial y comunicación directa (si aplica)",
        False,
    ),
]


class Command(BaseCommand):
    help = "Create the REG-016 Rev. 2 section 4 preflight checklist (LV-441)."

    @transaction.atomic
    def handle(self, *args, **options):
        checklist, list_created = PreflightChecklist.objects.get_or_create(
            name=CHECKLIST_NAME
        )
        created = 0
        for order, text, critical in ITEMS:
            _item, was_created = PreflightChecklistItem.objects.get_or_create(
                checklist=checklist,
                order=order,
                defaults={"text": text, "is_required": critical},
            )
            created += int(was_created)
        self.stdout.write(
            self.style.SUCCESS(
                f"Ensured REG-016 Rev. 2 checklist ({'created' if list_created else 'existing'}): "
                f"{len(ITEMS)} items ({created} created)."
            )
        )
