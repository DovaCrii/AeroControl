import json

from django.core.management.base import BaseCommand
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


class Command(BaseCommand):
    help = "Report database and migration readiness before a scale migration."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", dest="as_json")

    def handle(self, *args, **options):
        checks = {}
        try:
            connection.ensure_connection()
            checks["database_connection"] = "ok"
            checks["database_vendor"] = connection.vendor
            executor = MigrationExecutor(connection)
            plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
            checks["pending_migrations"] = len(plan)
        except Exception as exc:
            checks["database_connection"] = "error"
            checks["error"] = str(exc)
        checks["rollback_required"] = True
        checks["recommendation"] = (
            "Create and verify a backup before switching DATABASES to PostgreSQL."
        )
        if options["as_json"]:
            self.stdout.write(json.dumps(checks, ensure_ascii=False))
        else:
            for key, value in checks.items():
                self.stdout.write(f"{key}: {value}")
