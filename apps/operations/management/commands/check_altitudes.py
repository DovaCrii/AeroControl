"""LV-221: qué altitudes de permiso parecen estar cargadas en metros.

Pedido del usuario, textual: *"sumar eso, la altitud es en unidad metros como
trabajamos"*. El campo se llama `max_altitude_ft` y su etiqueta dice "Altitud
máxima (ft)", pero en la captura que mandó hay escrito **120** — y 120 pies son
36,6 m, mientras que 120 **metros** es el techo con el que se opera (394 ft).

**Así que el riesgo no es de rótulo: puede haber datos mal cargados**, y eso no se
deduce leyendo el código. Este comando existe para verlo antes de tocar el campo:
si hay permisos con la altitud en metros bajo una etiqueta que dice pies, cambiar
la unidad sin corregirlos convertiría un dato equivocado en otro dato equivocado
con otra etiqueta.

**Read-only**: no corrige nada. Cuál de estos valores está mal lo sabe quien tiene
la autorización de la DGAC en la mano, no una heurística.

Los dos umbrales, y de dónde salen:

- **Por debajo de 150 ft (45,7 m) es sospechoso.** No es una altitud de trabajo
  para un levantamiento: 120 ft son 36 m, y a esa altura la resolución exigida
  obligaría a un plan de vuelo que nadie hace. Un número bajo en esa casilla se
  explica mejor porque alguien pensó en metros.
- **Por encima de 500 ft (152 m) también.** El techo de la DAN 151 son 130 m AGL
  (426 ft), así que un valor mayor no puede venir de una autorización normal — o
  está en otra unidad, o hay un dígito de más.
"""

from django.core.management.base import BaseCommand

# 1 m = 3.28084 ft, el mismo factor que `LV-137` usa para convertir del KMZ.
FT_PER_M = 3.28084
SUSPICIOUS_BELOW_FT = 150
SUSPICIOUS_ABOVE_FT = 500


class Command(BaseCommand):
    help = "Report flight-permit altitudes that look like they were entered in metres."

    def handle(self, *args, **options):
        from apps.operations.models import FlightPermission

        permits = (
            FlightPermission.objects.filter(
                is_active=True, max_altitude_ft__isnull=False
            )
            .select_related("cost_center")
            .order_by("max_altitude_ft")
        )
        blank = FlightPermission.objects.filter(
            is_active=True, max_altitude_ft__isnull=True
        ).count()

        self.stdout.write(
            f"Altitudes cargadas en {permits.count()} permisos activos "
            f"({blank} sin dato):\n"
        )
        suspicious = 0
        for permit in permits:
            feet = permit.max_altitude_ft
            as_metres = feet / FT_PER_M
            # Si el número escrito fuera metros, esto es lo que debería decir la
            # casilla. Es la cifra que sirve para corregir.
            if_metres_then_ft = round(feet * FT_PER_M)
            label = f"{permit.internal_folio} {permit.cost_center.code}".strip()
            if feet < SUSPICIOUS_BELOW_FT:
                suspicious += 1
                self.stdout.write(
                    self.style.ERROR(
                        f"  REVISAR  {label:28} {feet:>5} ft = {as_metres:5.1f} m"
                        f"   → si eran {feet} m, la casilla debería decir "
                        f"{if_metres_then_ft} ft"
                    )
                )
            elif feet > SUSPICIOUS_ABOVE_FT:
                suspicious += 1
                self.stdout.write(
                    self.style.ERROR(
                        f"  REVISAR  {label:28} {feet:>5} ft = {as_metres:5.1f} m"
                        f"   → sobre el techo de la DAN 151 (130 m / 426 ft)"
                    )
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  ok       {label:28} {feet:>5} ft = {as_metres:5.1f} m"
                    )
                )
        summary = (
            f"\n{permits.count() - suspicious} plausibles, {suspicious} a revisar."
        )
        self.stdout.write(
            self.style.SUCCESS(summary)
            if not suspicious
            else self.style.WARNING(summary)
        )
        if suspicious:
            self.stdout.write(
                "Confirmar cada uno contra la autorización de la DGAC antes de "
                "corregir. Este comando no escribe nada."
            )
