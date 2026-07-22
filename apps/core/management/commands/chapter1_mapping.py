import json

from django.core.management.base import BaseCommand


MAPPING = {
    "version": "chapter1-v1",
    "entities": {
        "cost_center": {"code": "code", "name": "name"},
        "aircraft": {
            "registration": "registration",
            "type": "type",
            "model": "model",
            "manufacturer": "manufacturer",
            "year": "year",
            "cost_center": "cost_center",
            "status": "status",
        },
        "operator": {
            "employee_id": "employee_id",
            "full_name": "full_name",
            "email": "email",
            "phone": "phone",
            "cost_center": "cost_center",
        },
    },
}


class Command(BaseCommand):
    help = "Print the versioned Chapter 1 canonical import mapping."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", dest="as_json")

    def handle(self, *args, **options):
        if options["as_json"]:
            self.stdout.write(json.dumps(MAPPING, ensure_ascii=False, sort_keys=True))
            return
        self.stdout.write(f"version: {MAPPING['version']}")
        for entity, fields in MAPPING["entities"].items():
            self.stdout.write(f"{entity}: {', '.join(fields)}")
