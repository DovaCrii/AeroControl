#!/usr/bin/env python3
"""Consulta rápida de MASTER_PLAN.md sin leerlo entero (solo biblioteca estándar).

Uso (desde la raíz del repo):
  python plan_query.py --summary                  # conteo de filas por estado
  python plan_query.py --pending                  # filas ⬜ 🔄 ⛔, una línea cada una
  python plan_query.py --pending --section FASE   # filtra por texto del encabezado
  python plan_query.py --id LV-267                # fila completa de un ID (o prefijo: --id T1.)
  python plan_query.py --ghosts                   # IDs LV-N del git log sin fila en el plan
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

STATUS = {
    "⬜": "pendiente",
    "🔄": "en progreso",
    "✅": "hecho",
    "⛔": "bloqueado",
    # 🔶 = a medias (p. ej. `LV-218`: la mitad hecha, la otra espera a la DGAC). Sin
    # este estado la fila no se reconoce y `--pending` la esconde.
    "🔶": "parcial",
    "⏸": "diferido",
    "↪": "consolidado",
    "❌": "obsoleto",
}
ROW = re.compile(r"^\|\s*([A-Za-z][A-Za-z0-9.\-]*\d[A-Za-z0-9.]*)\s*\|\s*(.*)$")


def parse(path):
    section, rows = "", []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.startswith("#"):
            section = line.lstrip("# ").strip()
            continue
        m = ROW.match(line)
        if not m:
            continue
        rest = [c.strip() for c in m.group(2).split("|")]
        status = next((s for s in STATUS if rest and s in rest[0]), None)
        if status is None:
            continue
        text = max(rest[2:], key=len) if len(rest) > 2 else ""
        if not text.strip():
            text = rest[0].lstrip("".join(STATUS)).strip()
        rows.append(
            {
                "id": m.group(1),
                "status": status,
                "section": section,
                "line": n,
                "text": text,
                "raw": line,
            }
        )
    return rows


def short(text, width=150):
    text = re.sub(r"\*\*|`", "", text)
    return text if len(text) <= width else text[: width - 1] + "…"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", default="MASTER_PLAN.md")
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--pending", action="store_true")
    ap.add_argument("--section")
    ap.add_argument("--id")
    ap.add_argument("--ghosts", action="store_true")
    a = ap.parse_args()

    path = Path(a.plan)
    if not path.exists():
        sys.exit(f"No encuentro {path}: ejecutar desde la raíz del repo.")
    all_rows = parse(path)
    rows = all_rows
    if a.section:
        rows = [r for r in rows if a.section.lower() in r["section"].lower()]

    if a.summary:
        totals = {}
        for r in rows:
            totals[r["status"]] = totals.get(r["status"], 0) + 1
        print(f"{len(rows)} filas con estado")
        for s, c in sorted(totals.items(), key=lambda x: -x[1]):
            print(f"  {s} {STATUS[s]:<12}{c}")

    if a.pending:
        for r in rows:
            if r["status"] in "⬜🔄⛔🔶":
                print(
                    f"{r['status']} {r['id']:<8} L{r['line']:<5} "
                    f"[{short(r['section'], 38)}] {short(r['text'])}"
                )

    if a.id:
        hits = [r for r in all_rows if r["id"] == a.id or r["id"].startswith(a.id)]
        for r in hits:
            print(
                f"--- {r['id']} {r['status']} (línea {r['line']}, "
                f"sección: {r['section']})\n{r['raw']}\n"
            )
        if not hits:
            print(f"Sin fila para {a.id}")

    if a.ghosts:
        log = subprocess.run(
            ["git", "log", "--pretty=%s", "-n", "300"], capture_output=True, text=True
        ).stdout
        # `LV-168b` es un sub-ítem de la fila `LV-168`, no una fila propia.
        in_log = {
            re.sub(r"(?<=\d)[a-z]$", "", found)
            for found in re.findall(r"\bLV-\d+[a-z]?\b", log)
        }
        in_plan = {r["id"] for r in all_rows}
        missing = sorted(in_log - in_plan, key=lambda x: int(re.sub(r"\D", "", x)))
        print(
            "Filas fantasma (en commits, no en el plan):",
            ", ".join(missing) or "ninguna",
        )


if __name__ == "__main__":
    main()
