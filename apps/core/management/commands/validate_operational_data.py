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
        for aircraft in Aircraft.objects.select_related("cost_center").filter(
            is_active=True
        ):
            if aircraft.cost_center_id is None:
                errors.append(
                    {
                        "entity": "aircraft",
                        "id": str(aircraft.pk),
                        "issue": "unassigned_cost_center",
                    }
                )
            elif not aircraft.cost_center.is_active:
                errors.append(
                    {
                        "entity": "aircraft",
                        "id": str(aircraft.pk),
                        "issue": "inactive_cost_center",
                    }
                )
        for operator in Operator.objects.select_related("cost_center").filter(
            is_active=True
        ):
            if operator.cost_center_id is None:
                errors.append(
                    {
                        "entity": "operator",
                        "id": str(operator.pk),
                        "issue": "unassigned_cost_center",
                    }
                )
            elif not operator.cost_center.is_active:
                errors.append(
                    {
                        "entity": "operator",
                        "id": str(operator.pk),
                        "issue": "inactive_cost_center",
                    }
                )
        for assignment in Assignment.objects.select_related(
            "aircraft", "operator"
        ).filter(is_active=True):
            if not assignment.aircraft.is_active or not assignment.operator.is_active:
                errors.append(
                    {
                        "entity": "assignment",
                        "id": str(assignment.pk),
                        "issue": "inactive_reference",
                    }
                )
            if assignment.end_date and assignment.end_date < assignment.start_date:
                errors.append(
                    {
                        "entity": "assignment",
                        "id": str(assignment.pk),
                        "issue": "invalid_date_range",
                    }
                )
        # OPS-4: operators/aircraft are now a roster (M2M), not one of each, so
        # every check below scans the roster instead of a single reference.
        # select_related -> prefetch_related for the M2M half.
        for permission in (
            FlightPermission.objects.select_related("cost_center")
            .prefetch_related("operators", "aircraft_fleet")
            .filter(is_active=True)
        ):
            operators = list(permission.operators.all())
            aircraft_fleet = list(permission.aircraft_fleet.all())
            if (
                any(not operator.is_active for operator in operators)
                or any(not aircraft.is_active for aircraft in aircraft_fleet)
                or not permission.cost_center.is_active
            ):
                errors.append(
                    {
                        "entity": "flight_permission",
                        "id": str(permission.pk),
                        "issue": "inactive_reference",
                    }
                )
            if any(
                operator.cost_center_id != permission.cost_center_id
                for operator in operators
            ) or any(
                aircraft.cost_center_id != permission.cost_center_id
                for aircraft in aircraft_fleet
            ):
                errors.append(
                    {
                        "entity": "flight_permission",
                        "id": str(permission.pk),
                        "issue": "cost_center_mismatch",
                    }
                )
        for record in FlightRecord.objects.select_related(
            "permission", "pilot", "aircraft"
        ).filter(is_active=True):
            if not record.permission.aircraft_fleet.filter(
                pk=record.aircraft_id
            ).exists():
                errors.append(
                    {
                        "entity": "flight_record",
                        "id": str(record.pk),
                        "issue": "aircraft_mismatch",
                    }
                )
        result = {
            "status": "ok" if not errors else "invalid",
            "errors": errors,
            "count": len(errors),
        }
        if options["as_json"]:
            self.stdout.write(json.dumps(result, ensure_ascii=False))
        else:
            self.stdout.write(f"status: {result['status']}")
            self.stdout.write(f"errors: {result['count']}")
            for error in errors:
                self.stdout.write(f"{error['entity']} {error['id']}: {error['issue']}")
        if errors:
            raise SystemExit(1)
