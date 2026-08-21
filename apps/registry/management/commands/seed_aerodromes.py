"""R9.2: sembrar el catálogo de aeródromos que SIGO ofrece como AMC.

**La lista viene de las capturas del selector de SIGO** que aportó el usuario el
2026-08-20, no de una base aeronáutica externa. Decisión suya, textual: *"son
solo esas las disponibles de momento, por lo cual se debe respetar y extraer
las de las imágenes como listado principal"*. Ofrecer un nombre que el selector
del Estado no tiene no sirve de nada: el dato se va a copiar a mano allá.

Es una lista **global** — Abu Dhabi, Taranto, Anchorage conviven con los
chilenos — porque así la muestra SIGO. El selector aparecía alfabético por
nombre y las capturas cubren de la A hasta "Bermuda Intl", así que **el
catálogo está incompleto a sabiendas**: se completa desde la app cuando
aparezca un valor nuevo, sin desplegar (mismo criterio que `DocumentType`).

**Coordenadas: sólo las verificables.** Sembrar cincuenta posiciones aproximadas
produciría una distancia al AMC con dos decimales y ningún respaldo — la clase
de dato que se ve autoritativo y no lo es, que es exactamente lo que `LV-93`
enseñó a no hacer. Van sólo las de aeródromos chilenos de posición notoria; el
resto queda en blanco, no participa del cálculo y la pantalla lo dice.

Idempotente por `code`, como el resto de los seeds del repo: un rerun no pisa
una coordenada que alguien completó a mano desde la ficha.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.registry.models import Aerodrome

# (code, name, latitude, longitude) -- None/None cuando la posición no está
# verificada. Orden alfabético por nombre, como los presenta SIGO.
AERODROMES = [
    ("SKCL", "A.Bonilla Aragón Intl.", None, None),
    ("OMAA", "Abu Dhabi", None, None),
    ("TBPB", "Adams Intl.", None, None),
    ("SCFR", "Ad. Frutillar", None, None),
    ("SCER", "Ad. Militar Quintero", -32.790200, -71.521600),
    ("SCQP", "Aeródromo La Araucanía", -38.925600, -72.651500),
    ("SCTC", "Aeródromo Maquehue", -38.766800, -72.637100),
    ("SHFY", "Aerofly", None, None),
    ("SHAE", "Aerorescate", None, None),
    ("SCUZ", "Aerosanta Cruz", None, None),
    ("SHAS", "Aerosentrans", None, None),
    ("SABE", "Aeroparque", None, None),
    ("LIBG", "Aeroporto di Taranto-Grottaglie", None, None),
    ("LECU", "Aeropuerto Cuatro Vientos", None, None),
    ("LEJR", "Aeropuerto de Jerez de la Frontera", None, None),
    ("LPFR", "Aeropuerto Intern. de Faro", None, None),
    ("TJBQ", "Aeropuerto Rafael Hernández", None, None),
    ("LBSF", "Aeropuerto Sofia", None, None),
    ("LEZL", "Aeropuerto Utrera", None, None),
    ("SDHG", "Agusta Westland do Brasil", None, None),
    ("SCSA", "Alberto Santos Dumont", None, None),
    ("SPZO", "Alejandro Velasco Astete", None, None),
    ("SBCT", "Alfonso Pena Intl.", None, None),
    ("LET", "Alfredo Vásquez Cobo", None, None),
    ("SCHG", "Almahue", None, None),
    ("SCDW", "Almirante Schroders", None, None),
    ("SCAP", "Alto Palena", None, None),
    ("GVSC", "Amílcar Cabral", None, None),
    ("PANC", "Anchorage Intl.", None, None),
    ("SCFA", "Andrés Sabella", -23.444500, -70.445100),
    ("KANE", "Anoka County-Blaine Airport", None, None),
    ("LGAV", "AP Internacional Eleftherios Venizelos", None, None),
    ("ADZ", "AP. Intern. Gustavo Rojas Pinilla", None, None),
    ("KSMX", "AP Publico Santa Maria (KSMX USA)", None, None),
    ("NZAR", "Ardmore", None, None),
    ("SPQU", "Arequipa/ Rodríguez Ballón/Perú", None, None),
    ("SCEL", "Arturo Merino Benítez (SCEL)", -33.393000, -70.785800),
    ("SVVA", "Arturo Michelena", None, None),
    ("NZAA", "Auckland International", None, None),
    ("MNMG", "Augusto Sandino", None, None),
    ("SBNT", "Augusto Severo", None, None),
    ("SCAY", "Ayacara", None, None),
    ("SCBA", "Balmaceda", -45.916000, -71.694700),
    ("KBGR", "Bangor", None, None),
    ("GBYD", "Banjul Intl.", None, None),
    ("LEMD", "Barajas Intl.", None, None),
    ("SPLP", "Base Aérea Las Palmas", None, None),
    ("KBEC", "Beech Factory Airport", None, None),
    ("SCBV", "Bellavista", None, None),
    ("TXKF", "Bermuda Intl", None, None),
]


class Command(BaseCommand):
    help = "Create the SIGO aerodrome catalog used to compute the nearest AMC."

    @transaction.atomic
    def handle(self, *args, **options):
        created_count = 0
        for code, name, latitude, longitude in AERODROMES:
            _obj, created = Aerodrome.objects.get_or_create(
                code=code,
                defaults={
                    "name": name,
                    "latitude": latitude,
                    "longitude": longitude,
                },
            )
            created_count += int(created)
        located = Aerodrome.objects.filter(
            latitude__isnull=False, longitude__isnull=False
        ).count()
        total = Aerodrome.objects.count()
        self.stdout.write(
            self.style.SUCCESS(
                f"Ensured {len(AERODROMES)} aerodromes ({created_count} created)."
            )
        )
        # Se dice siempre, no sólo cuando faltan: es el número que decide si el
        # AMC calculado significa algo, y esconderlo en un día bueno enseñaría
        # a no leerlo en uno malo.
        self.stdout.write(
            f"{located} of {total} have coordinates and take part in the AMC "
            f"calculation; the rest need theirs filled in from the fiche."
        )
