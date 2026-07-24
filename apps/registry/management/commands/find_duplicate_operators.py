from django.core.management.base import BaseCommand, CommandError

from apps.registry.merge import (
    COMPARED_FIELDS,
    completeness,
    find_duplicate_groups,
    merge_operators,
    reference_counts,
)
from apps.registry.models import Operator


class Command(BaseCommand):
    help = (
        "List operators that appear to be the same person entered twice, with "
        "their field-by-field differences. With --apply and --group, merge one "
        "group: references move to the surviving record and the duplicate is "
        "archived (never deleted)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Perform the merge. Requires --group.",
        )
        parser.add_argument(
            "--group",
            help="Group key to merge (shown in the report). One group per run.",
        )
        parser.add_argument(
            "--into",
            help=(
                "employee_id of the record to keep. Defaults to the suggested "
                "one (most referenced, then most complete, then oldest)."
            ),
        )
        parser.add_argument(
            "--include-archived",
            action="store_true",
            help="Also consider already archived operators when grouping.",
        )

    def handle(self, *args, **options):
        groups = find_duplicate_groups(include_archived=options["include_archived"])

        if not options["apply"]:
            self._report(groups)
            return

        # Merging is deliberately one group at a time and named explicitly: it
        # rewrites operational history, so there is no bulk mode to run by
        # accident.
        if not options["group"]:
            raise CommandError(
                "--apply requires --group. Run without --apply to see the keys."
            )
        group = next((g for g in groups if g["key"] == options["group"]), None)
        if group is None:
            raise CommandError(
                f"No duplicate group named {options['group']!r}. "
                "Run without --apply to see the available keys."
            )

        canonical = self._canonical(group, options["into"])
        duplicates = [op for op in group["operators"] if op.pk != canonical.pk]

        result = merge_operators(canonical, duplicates)
        self.stdout.write(
            self.style.SUCCESS(
                f"Merged {len(duplicates)} record(s) into {canonical.employee_id} "
                f"({canonical.full_name})."
            )
        )
        for label, count in sorted(result["moved"].items()):
            self.stdout.write(f"  moved {count} x {label}")
        if not result["moved"]:
            self.stdout.write("  no references needed moving")
        self.stdout.write(f"  archived: {', '.join(result['archived'])}")

    @staticmethod
    def _canonical(group, into):
        if not into:
            return group["suggested"]
        for operator in group["operators"]:
            if operator.employee_id == into:
                return operator
        available = ", ".join(op.employee_id for op in group["operators"])
        raise CommandError(f"{into!r} is not part of this group. Members: {available}")

    def _report(self, groups):
        if not groups:
            self.stdout.write("No duplicate operators found.")
            return

        self.stdout.write(
            self.style.WARNING(f"{len(groups)} duplicate group(s) found:\n")
        )
        for group in groups:
            members = group["operators"]
            self.stdout.write(self.style.MIGRATE_HEADING(f"group: {group['key']}"))
            for operator in members:
                marker = "*" if operator.pk == group["suggested"].pk else " "
                refs = reference_counts(operator)
                ref_text = (
                    ", ".join(
                        f"{label}={count}" for label, count in sorted(refs.items())
                    )
                    or "no references"
                )
                self.stdout.write(
                    f"  {marker} {operator.employee_id}: {operator.full_name} "
                    f"(fields={completeness(operator)}/{len(COMPARED_FIELDS)}, "
                    f"created={operator.created_at:%Y-%m-%d}, {ref_text})"
                )
            if group["differences"]:
                self.stdout.write("    differences:")
                for field, values in group["differences"].items():
                    self.stdout.write(f"      {field}: {' | '.join(values)}")
            else:
                self.stdout.write("    identical on all compared fields")
            self.stdout.write(
                f"    merge with: manage.py find_duplicate_operators --apply "
                f"--group {group['key']}\n"
            )
        self.stdout.write("(* = suggested record to keep)")
        self.stdout.write(
            f"{Operator.objects.filter(is_active=True).count()} active operators total."
        )
