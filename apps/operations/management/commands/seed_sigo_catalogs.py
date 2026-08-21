"""R9.3: sembrar los dos vocabularios del formulario de SIGO.

"Área de Trabajo" y "Objetivo del Vuelo" son los dos desplegables que la
solicitud pide, y cuyo par se agrega a una tabla. Los valores vienen de las
capturas del selector real que aportó el usuario el 2026-08-20.

**Ambas listas están incompletas a sabiendas.** El desplegable de Área de
Trabajo se veía entero (cinco entradas, alfabético); el de Objetivo del Vuelo
aparecía desplazado y "BATIMETRÍA" quedaba cortada en el borde superior, así
que hay al menos una entrada por sobre ella que no se pudo leer. Por eso son
catálogos editables y no `choices` en el código: afirmar que la lista está
completa cuando se sabe que no lo está es peor que dejarla abierta.

Idempotente por `code`, como el resto de los seeds del repo.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.operations.models import FlightObjective, WorkAreaType

# (code, name, chapter) -- el capítulo va como SIGO lo muestra entre paréntesis.
WORK_AREAS = [
    ("agricolas", "Agrícolas", "Capítulo E - DAN 137"),
    (
        "fotografia-filmacion-aerea",
        "Fotografía y filmación aérea",
        "Capítulo J - DAN 137",
    ),
    ("instruccion-de-vuelo", "Instrucción de vuelo", "Capítulo G - DAN 137"),
    (
        "publicidad-propaganda-aerea",
        "Publicidad y propaganda aérea",
        "Capítulo H - DAN 137",
    ),
    ("otros", "Otros", ""),
]

# (code, name). Alfabético, como el desplegable.
OBJECTIVES = [
    ("batimetria", "Batimetría"),
    ("fotografia-filmacion", "Fotografía y filmación"),
    ("fotogrametria", "Fotogrametría"),
    ("inspeccion-at", "Inspección AT"),
    ("inspeccion-obras-civiles", "Inspección obras civiles"),
    ("magnetometria", "Magnetometría"),
    ("termografia-aerea", "Termografía aérea"),
    ("vigilancia-aerea", "Vigilancia aérea"),
]


class Command(BaseCommand):
    help = "Create the SIGO work-area and flight-objective catalogs (R9.3)."

    @transaction.atomic
    def handle(self, *args, **options):
        areas_created = 0
        for code, name, chapter in WORK_AREAS:
            _obj, created = WorkAreaType.objects.get_or_create(
                code=code, defaults={"name": name, "chapter": chapter}
            )
            areas_created += int(created)

        objectives_created = 0
        for code, name in OBJECTIVES:
            _obj, created = FlightObjective.objects.get_or_create(
                code=code, defaults={"name": name}
            )
            objectives_created += int(created)

        self.stdout.write(
            self.style.SUCCESS(
                f"Ensured {len(WORK_AREAS)} work areas ({areas_created} created) "
                f"and {len(OBJECTIVES)} objectives ({objectives_created} created)."
            )
        )
        # Dicho en cada corrida, no sólo la primera: es la advertencia que
        # impide que alguien lea este catálogo como la lista oficial completa.
        self.stdout.write(
            "Both lists come from screenshots of SIGO and are known to be "
            "incomplete; add any new value from the app when it appears."
        )
