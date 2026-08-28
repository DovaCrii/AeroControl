"""LV-177: propone el corte nombres/apellidos del padrón. Escribir exige --apply.

Dónde empieza el apellido **no es deducible sin equivocarse**: "Jose Luis Ogalde
Henríquez" son dos nombres y dos apellidos, "Bernardine Von Irmer Helle" lleva
una partícula, y "Ana Rivas" es uno y uno. Por eso este comando **propone y no
decide**, con el mismo molde que `find_duplicate_operators`: la máquina ordena el
trabajo, la persona que tiene el dato firma.

La heurística es deliberadamente boba y está declarada: en Chile el patrón
dominante es *nombres + apellido paterno + apellido materno*, así que con cuatro
palabras se parte 2/2 y con tres, 1/2. **Todo lo que no calce en ese patrón se
reporta como ambiguo y no se toca**: dos palabras (que tanto puede ser un nombre
y un apellido como dos apellidos), cinco o más, y cualquiera con partícula.

Se elige reportar de más antes que escribir de más: un corte equivocado ordena
mal justo el caso raro y nadie lo nota, porque la lista sigue viéndose ordenada.
"""

from django.core.management.base import BaseCommand

from apps.registry.models import Operator

# Partículas que pertenecen al apellido que las sigue. Su sola presencia manda la
# ficha a revisión: dónde empieza el apellido deja de ser contable por posición.
PARTICLES = {"de", "del", "la", "las", "los", "von", "van", "da", "di", "san"}


def propose(full_name):
    """`(nombres, apellidos)` o `None` cuando el patrón no alcanza."""
    words = (full_name or "").split()
    if any(word.casefold() in PARTICLES for word in words):
        return None
    if len(words) == 3:
        return " ".join(words[:1]), " ".join(words[1:])
    if len(words) == 4:
        return " ".join(words[:2]), " ".join(words[2:])
    return None


class Command(BaseCommand):
    help = "Propose the given-names/surnames split for operators (LV-177)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Write the proposals. Without it, nothing is saved.",
        )

    def handle(self, *args, **options):
        pending = Operator.objects.filter(surnames="").order_by("full_name")
        proposed, ambiguous = [], []
        for operator in pending:
            split = propose(operator.full_name)
            (ambiguous if split is None else proposed).append((operator, split))

        for operator, split in proposed:
            self.stdout.write(f"  {operator.full_name}  →  {split[1]}, {split[0]}")
        if ambiguous:
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING(
                    f"{len(ambiguous)} sin proponer — el patrón no alcanza, "
                    "hay que cortarlos a mano en la ficha:"
                )
            )
            for operator, _split in ambiguous:
                self.stdout.write(f"  {operator.full_name}")

        if not options["apply"]:
            self.stdout.write("")
            self.stdout.write(
                f"{len(proposed)} propuestos, {len(ambiguous)} a mano. "
                "Nada se escribió: repetir con --apply."
            )
            return

        for operator, split in proposed:
            operator.given_names, operator.surnames = split
            operator.save(update_fields=["given_names", "surnames", "updated_at"])
        self.stdout.write(self.style.SUCCESS(f"{len(proposed)} fichas actualizadas."))
