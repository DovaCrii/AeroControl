import csv
import hashlib
import json
import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from docx import Document

from apps.core.models import ImportBatch
from apps.registry.models import Aircraft, CostCenter, Operator


FIELD_LABELS = re.compile(
    r"(?P<label>NOMBRE|RUT|Credencia(?:l)?\s*N[°ºo]?|Tipo|Habilitaciones|"
    r"Direcci[^\s:]*n|Tel[^\s:]*fono|Email)\s*:\s*",
    re.IGNORECASE,
)
# El comienzo de una ficha de operador dentro de la sección 1.5.
#
# `LV-133`: **el número es opcional**. Hasta la Rev 16 cada ficha venía numerada
# ("1.- NOMBRE : …") y este patrón lo exigía; el Capítulo 1 **Rev 17** las escribe
# derecho, con la numeración movida al grupo ("1) PERMANENTES") y tabulaciones
# delante de cada etiqueta. Con el número obligatorio el importador no encontraba
# ni una ficha y moría con "No permanent operators were extracted" — sobre un
# documento que trae dieciséis. Un cambio de formato del manual no debería
# parecer un archivo vacío.
#
# `[ \t]*` y no `\s*`: con `MULTILINE`, `\s` cruza saltos de línea y el comienzo
# de una ficha podría "empezar" en la línea anterior, partiendo el bloque en el
# lugar equivocado.
RECORD_START = re.compile(
    r"^[ \t]*(?:\d{1,3}[ \t]*[-.]?[ \t]*[-.]?[ \t]*)?NOMBRE\b",
    re.IGNORECASE | re.MULTILINE,
)


def clean_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip(" \t:;.")


def rut_key(value):
    return re.sub(r"[^0-9K]", "", value.upper())


def parse_decimal(value):
    value = clean_text(value).replace(",", ".")
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise CommandError(f"Invalid weight value: {value}") from exc


class Command(BaseCommand):
    help = "Validate and optionally apply the official Chapter 1 DOCX source."

    def add_arguments(self, parser):
        parser.add_argument("--source", type=Path, required=True)
        parser.add_argument("--cost-centers", type=Path)
        parser.add_argument("--export-dir", type=Path)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument(
            "--skip-existing",
            action="store_true",
            help=(
                "Add only what is missing: leave every record already on file "
                "untouched instead of refusing the whole run."
            ),
        )
        parser.add_argument("--json", action="store_true", dest="as_json")

    def read_cost_centers(self, path):
        if not path:
            return []
        if not path.is_file():
            raise CommandError(f"Missing cost center source: {path}")
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            expected = ["code", "name", "responsible"]
            if reader.fieldnames != expected:
                raise CommandError(
                    f"cost centers columns must be: {','.join(expected)}"
                )
            rows = [
                {field: clean_text(value) for field, value in row.items()}
                for row in reader
            ]
        codes = [row["code"] for row in rows]
        if any(not code for code in codes) or len(codes) != len(set(codes)):
            raise CommandError("cost centers contains empty or duplicate codes")
        if any(not row["name"] for row in rows):
            raise CommandError("cost centers requires a name for every code")
        return rows

    def extract_operators(self, document):
        text = "\n".join(paragraph.text for paragraph in document.paragraphs)
        start_match = re.search(r"1\.5\s*[-.]?\s*DOTACI", text, re.IGNORECASE)
        end_match = re.search(r"EVENTUALES\s*\(\s*NO APLICA", text, re.IGNORECASE)
        if not start_match:
            raise CommandError("Could not locate the permanent operator section")
        section = text[start_match.start() : end_match.start() if end_match else None]
        starts = [match.start() for match in RECORD_START.finditer(section)]
        records = []
        for index, boundary in enumerate(starts):
            block = section[
                boundary : starts[index + 1] if index + 1 < len(starts) else None
            ]
            values = {
                "full_name": "",
                "rut": "",
                "dgac_credential": "",
                "operator_type": "",
                "authorizations": "",
                "address": "",
                "phone": "",
                "email": "",
            }
            matches = list(FIELD_LABELS.finditer(block))
            for position, match in enumerate(matches):
                raw_label = re.sub(r"[^a-z]", "", match.group("label").lower())
                field = {
                    "nombre": "full_name",
                    "rut": "rut",
                    "credencialn": "dgac_credential",
                    "credencian": "dgac_credential",
                    "tipo": "operator_type",
                    "habilitaciones": "authorizations",
                    "direccion": "address",
                    "direccin": "address",
                    "telefono": "phone",
                    "telfono": "phone",
                    "email": "email",
                }.get(raw_label)
                if not field:
                    continue
                end = (
                    matches[position + 1].start()
                    if position + 1 < len(matches)
                    else len(block)
                )
                values[field] = clean_text(block[match.end() : end])
                if field == "email":
                    values[field] = values[field].split("2)", 1)[0].strip()
            if not values["full_name"] or not values["rut"]:
                continue
            values["source_index"] = len(records) + 1
            records.append(values)
        if not records:
            raise CommandError("No permanent operators were extracted from the source")
        return records

    def extract_aircraft(self, document):
        if len(document.tables) < 2:
            raise CommandError("The source must contain the aircraft inventory table")
        service_table = document.tables[0]
        shared_services = clean_text(
            service_table.rows[1].cells[2].text if len(service_table.rows) > 1 else ""
        )
        inventory = document.tables[1]
        aircraft = []
        for row in inventory.rows[1:]:
            values = [clean_text(cell.text) for cell in row.cells]
            if len(values) < 8 or not values[3]:
                continue
            model_text = values[1]
            manufacturer, model = (model_text.split("/", 1) + [""])[:2]
            if not model:
                manufacturer, model = "", model_text
            registration_match = re.search(
                r"RPA\s*[- ]?\s*(\d+)", values[3], re.IGNORECASE
            )
            registration = (
                f"RPA-{registration_match.group(1)}"
                if registration_match
                else values[3]
            )
            aircraft.append(
                {
                    "registration": registration,
                    "type": "RPA",
                    "model": clean_text(model),
                    "manufacturer": clean_text(manufacturer),
                    "year": None,
                    "serial_number": values[2],
                    "max_takeoff_weight_kg": parse_decimal(values[4]),
                    "basic_weight_kg": parse_decimal(values[5]),
                    "vlos": values[6],
                    "parachute": values[7],
                    "authorized_services": shared_services,
                }
            )
        if not aircraft:
            raise CommandError("No aircraft were extracted from the source")
        return aircraft

    def duplicate_report(self, operators):
        groups = defaultdict(list)
        for operator in operators:
            groups[rut_key(operator["rut"])].append(operator)
        duplicate_groups = []
        clean_records = []
        for key, records in groups.items():
            if len(records) == 1:
                clean_records.append(records[0])
                continue
            comparable = [
                tuple(
                    record[field]
                    for field in (
                        "full_name",
                        "email",
                        "phone",
                        "address",
                        "authorizations",
                    )
                )
                for record in records
            ]
            kind = (
                "exact_duplicate"
                if len(set(comparable)) == 1
                else "conflicting_duplicate"
            )
            duplicate_groups.append({"rut": key, "kind": kind, "records": records})
            if kind == "exact_duplicate":
                clean_records.append(records[0])
        return clean_records, duplicate_groups

    def build_report(self, source, cost_centers):
        document = Document(source)
        operators = self.extract_operators(document)
        aircraft = self.extract_aircraft(document)
        clean_operators, duplicate_groups = self.duplicate_report(operators)
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        return {
            "mapping": "chapter1-v1-docx",
            "source": source.name,
            "sha256": digest,
            "cost_centers": cost_centers,
            "aircraft": aircraft,
            "operators": clean_operators,
            "duplicate_groups": duplicate_groups,
            "counts": {
                "aircraft_extracted": len(aircraft),
                "operators_extracted": len(operators),
                "operators_ready": len(clean_operators),
                "duplicate_groups": len(duplicate_groups),
                "cost_centers": len(cost_centers),
            },
        }

    def export_report(self, report, directory):
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "chapter1-report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        for name, rows in (
            ("chapter1-aircraft.csv", report["aircraft"]),
            ("chapter1-operators.csv", report["operators"]),
        ):
            if not rows:
                continue
            fields = [field for field in rows[0] if field != "source_index"]
            with (directory / name).open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerows(
                    {field: row.get(field, "") for field in fields} for row in rows
                )

    def partition(self, report):
        """Qué falta, qué ya está, y qué no se puede decidir sin una persona.

        `LV-134`: hasta acá `--apply` era todo o nada. Con **un** registro ya
        presente abortaba la corrida entera, y por eso servía sólo contra una
        base vacía — que es como se usó la primera vez y nunca más, porque una
        base en producción nunca vuelve a estar vacía. Cargar una aeronave nueva
        desde el manual exigía entonces tipearla a mano, teniendo el documento
        oficial en la mano.

        **Saltar no es sobrescribir.** Lo que ya está no se toca: si el manual y
        la base discrepan en algo, la decisión es de una persona con el papel al
        frente, no de un importador que "actualiza".

        La aeronave se busca por **matrícula y por número de serie**, no sólo por
        matrícula, y ésa es la parte que evita el duplicado real: `serial_number`
        es único desde `X.1`, así que una fila cuya matrícula no está pero cuya
        serie sí **no es nueva** — es la misma aeronave reinscrita o un dato mal
        transcrito, y crearla explotaría contra el índice único. Sale como
        conflicto, con los dos valores, para que se resuelva mirando el registro
        DGAC.
        """
        by_registration = dict(Aircraft.objects.values_list("registration", "pk"))
        by_serial = {
            serial: pk
            for serial, pk in Aircraft.objects.values_list("serial_number", "pk")
            if serial
        }
        existing_operators = set(Operator.objects.values_list("employee_id", flat=True))
        existing_centers = set(CostCenter.objects.values_list("code", flat=True))

        missing = {"cost_centers": [], "aircraft": [], "operators": []}
        skipped, conflicts = [], []

        for row in report["cost_centers"]:
            if row["code"] in existing_centers:
                skipped.append(f"cost_center:{row['code']}")
            else:
                missing["cost_centers"].append(row)

        for row in report["aircraft"]:
            registration, serial = row["registration"], row["serial_number"]
            known_by_registration = by_registration.get(registration)
            known_by_serial = by_serial.get(serial) if serial else None
            if known_by_registration and known_by_serial == known_by_registration:
                skipped.append(f"aircraft:{registration}")
            elif known_by_registration or known_by_serial:
                conflicts.append(
                    f"aircraft:{registration}/{serial or '—'} "
                    f"(matrícula {'ya existe' if known_by_registration else 'nueva'}, "
                    f"serie {'ya existe' if known_by_serial else 'nueva'})"
                )
            else:
                missing["aircraft"].append(row)

        for row in report["operators"]:
            employee_id = f"RUT-{rut_key(row['rut'])}"
            if employee_id in existing_operators:
                skipped.append(f"operator:{employee_id}")
            else:
                missing["operators"].append(row)

        return missing, skipped, conflicts

    def apply_report(self, report, skip_existing=False):
        missing, skipped, conflicts = self.partition(report)
        if skipped and not skip_existing:
            raise CommandError(
                "Existing records would be overwritten: "
                + ", ".join(skipped)
                + ". Use --skip-existing to add only what is missing."
            )
        # Un conflicto detiene la corrida **siempre**, con o sin la bandera: no
        # es "ya está", es "la base y el manual no coinciden", y adivinar cuál
        # manda sobre una aeronave es cómo se crea el registro fantasma que
        # después nadie sabe de dónde salió.
        if conflicts:
            raise CommandError(
                "The manual and the database disagree; resolve these first: "
                + ", ".join(conflicts)
            )
        report = report | {
            "cost_centers": missing["cost_centers"],
            "aircraft": missing["aircraft"],
            "operators": missing["operators"],
            "skipped": skipped,
        }
        created_ids = []
        with transaction.atomic():
            for row in report["cost_centers"]:
                created_ids.append(str(CostCenter.objects.create(**row).pk))
            source_note = f"Fuente oficial Capítulo 1: {report['source']} ({report['sha256'][:12]})"
            for row in report["aircraft"]:
                payload = {**row, "notes": source_note}
                created_ids.append(str(Aircraft.objects.create(**payload).pk))
            for row in report["operators"]:
                operator_data = dict(row)
                rut = operator_data["rut"]
                payload = {
                    **operator_data,
                    "employee_id": f"RUT-{rut_key(rut)}",
                    "notes": source_note,
                }
                payload.pop("source_index", None)
                created_ids.append(str(Operator.objects.create(**payload).pk))
            stored_report = json.loads(
                json.dumps(report, ensure_ascii=False, default=str)
            )
            batch = ImportBatch.objects.create(
                actor=None,
                entity="chapter1.docx",
                rows=stored_report,
                created_ids=created_ids,
            )
        return batch

    def handle(self, *args, **options):
        source = options["source"]
        if not source.is_file():
            raise CommandError(f"Missing source DOCX: {source}")
        report = self.build_report(
            source, self.read_cost_centers(options.get("cost_centers"))
        )
        if options.get("export_dir"):
            self.export_report(report, options["export_dir"])
        applied = None
        if options["apply"]:
            applied = self.apply_report(report, options["skip_existing"])
        else:
            # Sin `--apply` la corrida es un informe, y decir **qué haría** es
            # justo lo que se quiere leer antes de tocar producción.
            _missing, skipped, conflicts = self.partition(report)
            report = report | {"skipped": skipped, "conflicts": conflicts}
        output = report | {"apply": options["apply"]}
        if applied is not None:
            output = output | {"created": len(applied.created_ids)}
        if options["as_json"]:
            self.stdout.write(json.dumps(output, ensure_ascii=False, default=str))
            return
        self.stdout.write(f"mapping: {report['mapping']}")
        self.stdout.write(f"source: {report['source']}")
        for key, value in report["counts"].items():
            self.stdout.write(f"{key}: {value}")
        for duplicate in report["duplicate_groups"]:
            self.stdout.write(f"duplicate {duplicate['kind']} RUT {duplicate['rut']}")
        # LV-134: lo que ya está y lo que no cuadra, contado y nombrado. "Cuántos
        # se saltaron" es la cifra que dice si esta corrida iba a crear algo.
        skipped = report.get("skipped") or []
        self.stdout.write(f"already_on_file: {len(skipped)}")
        for entry in skipped:
            self.stdout.write(f"  skipped {entry}")
        for entry in report.get("conflicts") or []:
            self.stdout.write(f"  CONFLICT {entry}")
        if applied is not None:
            self.stdout.write(f"created: {len(applied.created_ids)}")
