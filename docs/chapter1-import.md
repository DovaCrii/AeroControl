# Capítulo 1 — mapping v1

The canonical import mapping is versioned as chapter1-v1 and can be inspected
with:

    uv run python manage.py chapter1_mapping --json

The mapping normalizes source spreadsheets into the existing CostCenter,
Aircraft and Operator import contracts. Source-specific column names must be
translated to these canonical names before validation; no row is silently
discarded. The current CSV import screens are the first consumer of this
mapping, and the next step is an Excel adapter that applies the same rules.
