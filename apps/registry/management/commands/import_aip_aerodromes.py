"""R10.7: posicionar el catálogo de SIGO con las coordenadas del AIP-Chile.

**Qué hace y qué no.** Rellena `latitude`/`longitude` de los aeródromos que ya
están en el catálogo, cruzando por designador OACI contra una copia del AIP de la
DGAC. **No crea aeródromos.** El AIP publica 452 y el selector de SIGO ofrece
muchos menos; sembrar los 452 dejaría a la app proponiendo como "más cercano" un
aeródromo que **la casilla del formulario del Estado no permite elegir**, que es
exactamente la decisión que el usuario tomó el 2026-08-20 y reafirmó el
2026-08-24: *"sólo debemos usar lo que estaban en las imágenes de la DGAC para
utilizar en el permiso, ya que son muchos más de lo que hoy están disponibles en
el portal SIGO para ser usados"*.

Corolario que conviene tener claro al leer una distancia: **el AMC que la app
propone es el más cercano _entre los que SIGO ofrece_**, no el más cercano del
país. Para las faenas de CC 738 eso da Quintero a ~124 km teniendo Pichidangui a
79 km, y no es un error: Pichidangui no se puede seleccionar allá. La forma de
mejorarlo es **capturar el resto del selector de SIGO** — las imágenes del
2026-08-20 llegaban de la "A" hasta "Bermuda Intl" — y volver a correr esto.

**La fuente.** `https://aipchile.dgac.gob.cl/api/aerodrome` es el endpoint que
alimenta el mapa del AIP-Chile; trae designador, nombre, posición, uso y estado.
Es la misma publicación contra la que la regla del proyecto manda confirmar
(`LV-93`: *la app propone, la carta AIP manda*), así que tomar posiciones de ahí
cumple el criterio de "sólo lo verificable" mejor que cualquier lista intermedia.

Los datos van **versionados** en `apps/registry/data/aip_aerodromes.csv`, no se
piden por red: un seed que depende de que un servicio del Estado esté arriba
falla en el peor momento, y la copia en git deja ver en el diff qué cambió cuando
el AIP se actualice. Para regenerarla:

    curl 'https://aipchile.dgac.gob.cl/api/aerodrome' -o aip.json

y volcar cada registro como `code,name,latitude,longitude,use,closed`, con el
marcador de uso (`PUB`/`PVT`/`MIL`) sacado del paréntesis final del nombre y la
posición a seis decimales, que es la precisión de `Aerodrome.latitude`.

**Tres reglas, y las tres importan:**

1. **El nombre no se toca.** El del catálogo vino del selector de SIGO y es el
   texto que la persona debe encontrar **allá**; el AIP los llama distinto
   ("Frutillar" vs "Ad. Frutillar"). Cambiarlo por el nombre "correcto" rompería
   el único motivo de tener la lista.
2. **La posición del AIP manda sobre la que ya estaba**, y cada corrección se
   imprime con cuánto se movió. Rellenar un hueco es obvio; sobrescribir merece
   verse, porque una posición vieja y una confirmada son indistinguibles después.
3. **Un aeródromo cerrado en el AIP queda desactivado.** No se borra —su nombre
   puede seguir en SIGO y en permisos viejos— pero `is_active=False` lo saca del
   cálculo por el filtro que `_locatable_aerodromes()` ya aplica. Proponer una
   pista cerrada como la más cercana es peor que no proponer nada.

Idempotente por `code`: un rerun no mueve nada que el AIP no haya movido.
"""

import csv
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.geo.sections import haversine_km
from apps.registry.models import Aerodrome

DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "aip_aerodromes.csv"

# Fecha de la copia del AIP. Va en `notes` de lo que se posiciona, porque "de
# dónde salió esta posición" es la primera pregunta al dudar de una distancia, y
# la respuesta no debería exigir leer el historial de git.
AIP_SNAPSHOT = "2026-08-24"

# Dos posiciones que difieren menos que esto son el mismo punto: el umbral separa
# "el AIP corrigió el dato" de "el redondeo del sexto decimal".
POSITION_TOLERANCE_M = 50.0

# **Cruces por código que el nombre desmiente.** El código OACI es la llave, pero
# cuando las dos fuentes describen lugares distintos la llave no alcanza: una de
# las dos está equivocada y el motor no puede saber cuál. Sembrar la posición
# igual sería afirmar una ubicación con cara de autoritativa y sin respaldo,
# que es lo que `LV-93` dejó prohibido. Quedan sin posición, se informan, y lo
# resuelve una persona con la carta al frente.
#
# `SCSA`: SIGO lo rotula "Alberto Santos Dumont" —que es Río de Janeiro, `SBRJ`—
# y el AIP-Chile lo da como "Rungue Dr. C. Barría B." (RM, privado). O el nombre
# de SIGO está mal o el código lo está.
NAME_MISMATCH = {
    "SCSA": (
        'SIGO lo llama "Alberto Santos Dumont" (Río de Janeiro) y el AIP-Chile '
        '"Rungue Dr. C. Barría B."'
    ),
}


def aip_rows():
    """El AIP versionado, indexado por designador OACI."""
    rows = {}
    with DATA_FILE.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            rows[row["code"].strip()] = {
                "name": row["name"].strip(),
                "latitude": Decimal(row["latitude"]) if row["latitude"] else None,
                "longitude": Decimal(row["longitude"]) if row["longitude"] else None,
                "use": row["use"].strip(),
                "closed": row["closed"] == "1",
            }
    return rows


class Command(BaseCommand):
    help = "Position the SIGO aerodrome catalog from the versioned AIP-Chile data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing anything.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        aip = aip_rows()
        filled, corrected, deactivated = [], [], []
        unknown, skipped = [], []

        for aerodrome in Aerodrome.objects.all().order_by("code"):
            if aerodrome.code in NAME_MISMATCH:
                skipped.append(aerodrome)
                continue
            row = aip.get(aerodrome.code)
            if row is None:
                unknown.append(aerodrome)
                continue

            changes = []
            if row["latitude"] is not None and row["longitude"] is not None:
                if not aerodrome.is_locatable:
                    filled.append(aerodrome)
                    changes += ["latitude", "longitude"]
                else:
                    moved_m = (
                        haversine_km(
                            float(aerodrome.latitude),
                            float(aerodrome.longitude),
                            float(row["latitude"]),
                            float(row["longitude"]),
                        )
                        * 1000
                    )
                    if moved_m > POSITION_TOLERANCE_M:
                        corrected.append((aerodrome, moved_m))
                        changes += ["latitude", "longitude"]
            if row["closed"] and aerodrome.is_active:
                deactivated.append(aerodrome)
                changes.append("is_active")

            if not changes:
                continue
            if "latitude" in changes:
                aerodrome.latitude = row["latitude"]
                aerodrome.longitude = row["longitude"]
                # Sólo si nadie escribió nada: una nota a mano es de una persona
                # y vale más que la procedencia, que el commit ya explica.
                if not aerodrome.notes:
                    aerodrome.notes = (
                        f"Posición: AIP-Chile ({AIP_SNAPSHOT}), "
                        f"{row['name']}, uso {row['use'] or '—'}."
                    )
                    changes.append("notes")
            if "is_active" in changes:
                aerodrome.is_active = False
            if not dry_run:
                aerodrome.save(update_fields=[*changes, "updated_at"])

        prefix = "Would " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}fill {len(filled)}, correct {len(corrected)}, "
                f"deactivate {len(deactivated)}."
            )
        )
        for aerodrome, moved_m in corrected:
            self.stdout.write(f"  {aerodrome.code} {aerodrome.name}: {moved_m:.0f} m")
        if skipped:
            self.stdout.write(
                "Left without a position because the two sources disagree "
                "on what the code is:"
            )
            for aerodrome in skipped:
                self.stdout.write(
                    f"  {aerodrome.code}: {NAME_MISMATCH[aerodrome.code]}"
                )
        if unknown:
            # Casi todos son extranjeros: es el AIP **de Chile**. Decir cuántos y
            # cuáles evita que alguien busque un error donde no hay ninguno.
            self.stdout.write(
                f"{len(unknown)} not in the Chilean AIP (foreign, or not "
                f"published): {', '.join(a.code for a in unknown)}"
            )
        located = Aerodrome.objects.filter(
            is_active=True, latitude__isnull=False, longitude__isnull=False
        ).count()
        total = Aerodrome.objects.count()
        self.stdout.write(
            f"{located} of {total} take part in the AMC calculation. The AMC the "
            f"app proposes is the nearest among the ones SIGO offers."
        )
