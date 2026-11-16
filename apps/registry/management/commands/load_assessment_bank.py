"""LV-444: cargar el banco de preguntas de las evaluaciones (REG-019) desde un archivo.

El banco **no vive en el repositorio** (es público y las preguntas con su clave son
el examen). Este comando lo lee de un archivo JSON fuera del árbol versionado
—`private/` o una ruta de la VM— y lo deja en `AssessmentQuestion`. El formato está
en `docs/assessment-bank-format.md`.

    uv run python manage.py load_assessment_bank private/banco.json --dry-run
    uv run python manage.py load_assessment_bank private/banco.json
    uv run python manage.py load_assessment_bank private/banco.json --replace

**Idempotente** por `(tipo, modelo, número)`: correrlo dos veces no duplica; una
pregunta con el mismo número se actualiza. `--replace` **archiva** (nunca borra)
las preguntas de los tipos presentes en el archivo que ya no vienen en él. Todo o
nada: si una pregunta es inválida no se escribe ninguna.
"""

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.registry.assessments import _unwrapped
from apps.registry.models import AssessmentQuestion, QualificationType

KINDS = {kind for kind, _label in AssessmentQuestion.KIND_CHOICES}


def _read(path):
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CommandError(f"Cannot read {path}: {exc}") from exc
    except ValueError as exc:
        raise CommandError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("questions"), list):
        raise CommandError('The file must be an object with a "questions" list.')
    return payload["questions"]


def _parse(index, raw, families, errors):
    """Una pregunta validada, o `None` con sus problemas agregados a `errors`."""
    label = f"question #{index}"
    problems = []
    if not isinstance(raw, dict):
        errors.append(f"{label}: must be an object")
        return None
    kind = raw.get("kind")
    if kind not in KINDS:
        problems.append(f'"kind" must be one of {sorted(KINDS)}')
    number = raw.get("number")
    if not isinstance(number, int) or isinstance(number, bool) or number < 1:
        problems.append('"number" must be a positive integer')
    text = raw.get("text")
    text = _unwrapped(text) if isinstance(text, str) else ""
    if not text:
        problems.append('"text" is required')
    options = []
    raw_options = raw.get("options")
    if not isinstance(raw_options, list) or len(raw_options) < 2:
        problems.append('"options" needs at least two options')
    else:
        for option in raw_options:
            key = (
                str(option.get("key", "")).strip().lower()
                if isinstance(option, dict)
                else ""
            )
            option_text = (
                _unwrapped(str(option.get("text", "")))
                if isinstance(option, dict)
                else ""
            )
            if len(key) != 1 or not option_text:
                problems.append('every option needs a one-letter "key" and a "text"')
                break
            options.append({"key": key, "text": option_text})
        keys = [option["key"] for option in options]
        if len(set(keys)) != len(keys):
            problems.append("option keys must be distinct")
    answer = str(raw.get("answer", "")).strip().lower()
    if options and answer not in {option["key"] for option in options}:
        problems.append('"answer" must be one of the option keys')
    family = None
    code = raw.get("family")
    if code:
        if kind != "limitations":
            problems.append('"family" only applies to limitations questions')
        family = families.get(str(code))
        if family is None:
            problems.append(
                f'unknown "family" code {code!r} (a QualificationType code)'
            )
    if problems:
        errors.append(f"{label}: " + "; ".join(problems))
        return None
    return {
        "kind": kind,
        "number": number,
        "family": family,
        "text": text,
        "options": options,
        "answer": answer,
        "source_ref": str(raw.get("source_ref", ""))[:150],
    }


class Command(BaseCommand):
    help = (
        "Load the assessment question bank (REG-019) from a JSON file outside the repo."
    )

    def add_arguments(self, parser):
        parser.add_argument("path", help="JSON bank file (outside git; e.g. private/).")
        parser.add_argument(
            "--dry-run", action="store_true", help="Validate and report; write nothing."
        )
        parser.add_argument(
            "--replace",
            action="store_true",
            help="Archive (never delete) the questions of the kinds in the file that it no longer lists.",
        )

    def handle(self, *args, path, dry_run=False, replace=False, **options):
        file = Path(path).resolve()
        tracked = (Path(settings.BASE_DIR) / "apps").resolve()
        if tracked in file.parents:
            raise CommandError(
                "The bank must live outside the versioned code (use private/ or a path on the server)."
            )
        raw_questions = _read(file)
        families = {t.code: t for t in QualificationType.objects.all()}
        errors, parsed = [], []
        for index, raw in enumerate(raw_questions, start=1):
            question = _parse(index, raw, families, errors)
            if question:
                parsed.append(question)
        seen = set()
        for question in parsed:
            key = (
                question["kind"],
                question["family"].pk if question["family"] else None,
                question["number"],
            )
            if key in seen:
                errors.append(
                    f"duplicate question {question['kind']} #{question['number']}"
                )
            seen.add(key)
        if errors:
            raise CommandError(
                "The bank file is invalid, nothing was loaded:\n  "
                + "\n  ".join(errors)
            )
        if not parsed:
            raise CommandError("The bank file has no questions.")

        created = updated = archived = 0
        loaded = []
        with transaction.atomic():
            for question in parsed:
                obj, was_created = AssessmentQuestion.objects.update_or_create(
                    kind=question["kind"],
                    aircraft_family=question["family"],
                    number=question["number"],
                    defaults={
                        "text": question["text"],
                        "options": question["options"],
                        "answer": question["answer"],
                        "source_ref": question["source_ref"],
                        "is_active": True,
                    },
                )
                loaded.append(obj.pk)
                created += was_created
                updated += not was_created
            if replace:
                stale = AssessmentQuestion.objects.filter(
                    is_active=True, kind__in={q["kind"] for q in parsed}
                ).exclude(pk__in=loaded)
                for question in stale:
                    question.is_active = False
                    question.save(update_fields=["is_active", "updated_at"])
                    archived += 1
            if dry_run:
                transaction.set_rollback(True)

        prefix = "[dry-run] " if dry_run else ""
        self.stdout.write(
            f"{prefix}{created} created, {updated} updated, {archived} archived."
        )
