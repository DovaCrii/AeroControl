import json

from django.core.management.base import BaseCommand
from apps.registry.models import Aircraft, Assignment, Operator
from apps.operations.models import FlightPermission, FlightRecord


class Command(BaseCommand):
    help = "Validate cross-domain operational references without changing data."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", dest="as_json")

    def handle(self, *args, **options):
        errors = []
        for aircraft in Aircraft.objects.select_related("cost_center").filter(is_active=True):
            if not aircraft.cost_center.is_active:
                errors.append({"entity": "aircraft", "id": str(aircraft.pk), "issue": "inactive_cost_center"})
        for operator in Operator.objects.select_related("cost_center").filter(is_active=True):
            if not operator.cost_center.is_active:
                errors.append({"entity": "operator", "id": str(operator.pk), "issue": "inactive_cost_center"})
        for assignment in Assignment.objects.select_related("aircraft", "operator").filter(is_active=True):
            if not assignment.aircraft.is_active or not assignment.operator.is_active:
                errors.append({"entity": "assignment", "id": str(assignment.pk), "issue": "inactive_reference"})
            if assignment.end_date and assignment.end_date < assignment.start_date:
                errors.append({"entity": "assignment", "id": str(assignment.pk), "issue": "invalid_date_range"})
        for permission in FlightPermission.objects.select_related("operator", "aircraft", "cost_center").filter(is_active=True):
            if not permission.operator.is_active or not permission.aircraft.is_active or not permission.cost_center.is_active:
                errors.append({"entity": "flight_permission", "id": str(permission.pk), "issue": "inactive_reference"})
            if permission.operator.cost_center_id != permission.cost_center_id or permission.aircraft.cost_center_id != permission.cost_center_id:
                errors.append({"entity": "flight_permission", "id": str(permission.pk), "issue": "cost_center_mismatch"})
        for record in FlightRecord.objects.select_related("permission", "pilot", "aircraft").filter(is_active=True):
            if record.permission.aircraft_id != record.aircraft_id:
                errors.append({"entity": "flight_record", "id": str(record.pk), "issue": "aircraft_mismatch"})
        result = {"status": "ok" if not errors else "invalid", "errors": errors, "count": len(errors)}
        if options["as_json"]:
            self.stdout.write(json.dumps(result, ensure_ascii=False))
        else:
            self.stdout.write(f"status: {result['status']}")
            self.stdout.write(f"errors: {result['count']}")
            for error in errors:
                self.stdout.write(f"{error['entity']} {error['id']}: {error['issue']}")
        if errors:
            raise SystemExit(1)
