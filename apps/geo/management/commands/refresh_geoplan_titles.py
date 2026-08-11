"""LV-70: rewrite geo plan titles frozen with the pre-R2.2 permission repr.

`GeoPlan.title` is denormalised text: `GeoPlanImportForm._autogenerate_title`
builds `f"{permission} · {file_stem}"` at import time and stores the result. The
two real plans on production were imported on 2026-08-04/06, before R2.2/R2.3
(2026-08-10) gave every permission an `internal_folio` and made `__str__` return
it -- so they still carry the old `status · purpose` fallback, e.g.
`Solicitado · Fotogrametría - Fotos - Videos · CC861_area_permiso`.

That is not merely cosmetic: the title carries `purpose` as if it were an
identifier, which is exactly the confusion R2.2/R2.3 removed everywhere else,
and it means a plan cannot be cross-referenced against its permission by folio.

Same shape as `refresh_alert_task_titles`, which fixes this class of problem for
KanbanTask: report by default, `--apply` to persist.

Only touches plans that **have a linked permission** (there is nothing to derive
a better title from otherwise) and only when the rebuilt title actually differs,
so a rerun is a no-op and a hand-edited title is left alone unless it happens to
match the stale pattern.
"""

from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.geo.models import GeoPlan


class Command(BaseCommand):
    help = (
        "Rebuild geo plan titles from their flight permission, for plans "
        "imported before the permission had an internal folio (LV-70)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Persist the changes. Without it, only report what would change.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        plans = GeoPlan.objects.filter(flight_permission__isnull=False).select_related(
            "flight_permission"
        )
        changed = 0
        for plan in plans:
            new_title = self._rebuild(plan)
            if new_title is None or new_title == plan.title:
                continue
            self.stdout.write(f"{plan.title!r} -> {new_title!r}")
            if options["apply"]:
                plan.title = new_title
                plan.save(update_fields=["title", "updated_at"])
            changed += 1
        verb = "Updated" if options["apply"] else "Would update"
        self.stdout.write(self.style.SUCCESS(f"{verb} {changed} plan titles."))

    @staticmethod
    def _rebuild(plan):
        """`<permission> · <original file stem>`, mirroring the import form.

        The file stem is recovered from the **existing title's last segment**
        rather than from the source document: the title is the only place it is
        guaranteed to be, because the source `Document` may have been replaced
        or archived since the import, and its stored filename is uuid-prefixed
        by `document_upload_path`. Returns None when the title has no separator
        to split on (a fully hand-written title), leaving it untouched.
        """
        if " · " not in plan.title:
            return None
        file_stem = plan.title.rsplit(" · ", 1)[-1]
        return f"{plan.flight_permission} · {Path(file_stem).stem}"[:200]
