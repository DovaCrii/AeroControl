# Capítulo 1 — mapping v1

The canonical import mapping is versioned as chapter1-v1 and can be inspected
with:

    uv run python manage.py chapter1_mapping --json

The mapping normalizes source spreadsheets into the existing CostCenter,
Aircraft and Operator import contracts. Source-specific column names must be
translated to these canonical names before validation; no row is silently
discarded. The current CSV import screens are the first consumer of this
mapping, and the next step is an Excel adapter that applies the same rules.

Excel workbooks can be validated/applied with:

    uv run python manage.py chapter1_import --workbook capitulo1.xlsx
    uv run python manage.py chapter1_import --workbook capitulo1.xlsx --apply

Expected sheet names are cost_centers, aircraft and operators. Each sheet must
use the canonical header order from chapter1-v1.

Before applying the official source, run the command without `--apply` and
review duplicate, reference and schema errors. The source workbook is not part
of the repository; the load remains pending until the official file is
provided.

## Fuente oficial DOCX

La adaptación para el Capítulo 1 vigente permite validar y cargar directamente
el documento oficial sin copiarlo al repositorio:

    uv run python manage.py chapter1_docx_import --source "D:\ruta\1 Capítulo 1 202607_R16.docx" --cost-centers "D:\I+D\AeroOpsDesk_Data\imports\20260723_centros_costo.csv" --export-dir "D:\I+D\AeroOpsDesk_Data\imports\chapter1-YYYYMMDD"

El comando genera un informe JSON y CSV fuera del repositorio. Sólo después de
revisar duplicados y el informe de calidad se aplica la carga agregando
`--apply`.

La carga conserva aeronaves y operadores con centro de costo vacío cuando la
fuente no trae esa relación. Esto evita inventar asignaciones y permite que
`validate_operational_data` informe `unassigned_cost_center` hasta que exista
una matriz oficial de asignación.

La fuente 202607/R16 revisada contiene 14 aeronaves y 50 fichas permanentes.
Se cargan 41 operadores sin conflicto, se consolida un duplicado exacto y se
mantienen cuatro grupos de RUT con datos contradictorios en el reporte externo.
