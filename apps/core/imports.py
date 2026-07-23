"""Shared, bounded CSV import parsing primitives."""

import csv
import io
from dataclasses import dataclass


@dataclass(frozen=True)
class CsvImportSpec:
    fields: tuple[str, ...]
    key_field: str
    max_bytes: int = 2 * 1024 * 1024
    max_rows: int = 500

    def parse(self, upload, existing_keys, row_builder):
        if not upload or upload.size > self.max_bytes:
            return [], ["El archivo es obligatorio y no puede superar 2 MB."]
        try:
            reader = csv.DictReader(io.StringIO(upload.read().decode("utf-8-sig")))
            raw_rows = list(reader)
        except (UnicodeDecodeError, csv.Error):
            return [], ["El archivo debe ser CSV UTF-8 válido."]
        if reader.fieldnames != list(self.fields):
            return [], ["Las columnas deben ser exactamente: " + ",".join(self.fields)]
        if len(raw_rows) > self.max_rows:
            return [], [f"El máximo por lote es de {self.max_rows} filas."]

        rows, errors, seen = [], [], set()
        for line, raw in enumerate(raw_rows, start=2):
            key = str(raw.get(self.key_field, "")).strip()
            if not key or key in seen or key in existing_keys:
                errors.append(f"Línea {line}: {self.key_field} vacío o duplicado.")
                continue
            try:
                value = row_builder(raw, line)
            except ValueError as exc:
                errors.append(f"Línea {line}: {exc}")
                continue
            if isinstance(value, str):
                errors.append(f"Línea {line}: {value}")
                continue
            seen.add(key)
            rows.append(value)
        return rows, errors
