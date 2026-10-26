"""LV-378 (PR 2): los permisos vigentes agrupados por faena, **sólo desde el payload**.

La sección 2 del informe de octubre repetía siete veces la misma fila de CC738
(28-08 → 28-11, RPA-4883, un operador) y tres más de CC691: una tabla permiso a
permiso donde la persona que lee quiere saber **qué faena vence cuándo**. Esto arma la
vista agrupada, igual que `summary.py` arma la hoja ejecutiva: una función pura sobre
el payload congelado, sin consultar la base, y devolviendo datos y no frases (las
palabras las pone la plantilla).

**Regla de agrupación.** Primero por faena. Dentro de la faena, por la tupla `(inicio,
fin, aeronaves, operadores)`: si todos los permisos de la faena comparten la tupla, la
faena es **una línea**; si no, una sublínea por tupla. **Los folios se listan siempre
explícitos, sin rangos**: un rango «001–007» esconde que falta el 004, y en un papel
que va a la DGAC un folio ausente tiene que verse.

Las faenas con operación van en `operating`, ordenadas por urgencia (la que vence
primero, arriba); las demás —terminadas, que no vuelan o archivadas— en `outside`,
porque su permiso vigente existe ante la DGAC pero **no se renueva** y no entra en la
cobertura ni en las cifras de renovación (regla a′ de LV-378). En trámite y vencidos
sin cerrar van aparte y planos: son pocos y cada fila cuenta.
"""

from apps.compliance.kpis import permit_band

#: Cuántos días abarca la tira de vencimientos. Más allá se junta en «›90».
STRIP_DAYS = 90


def _folio_key(row):
    return row.get("folio") or ""


def _line_key(row):
    return (
        row.get("valid_from") or "",
        row.get("valid_until") or "",
        tuple(sorted(row.get("aircraft") or [])),
        tuple(sorted(row.get("operators") or [])),
    )


def _lines(rows):
    """Las sublíneas de una faena: una por tupla `(inicio, fin, aeronaves, operadores)`."""
    by_tuple = {}
    for row in rows:
        by_tuple.setdefault(_line_key(row), []).append(row)
    lines = []
    for key in sorted(by_tuple):
        members = sorted(by_tuple[key], key=_folio_key)
        days = min(row["days_remaining"] for row in members)
        lines.append(
            {
                "valid_from": members[0].get("valid_from"),
                "valid_until": members[0].get("valid_until"),
                "aircraft": list(key[2]),
                "operators": len(key[3]),
                "count": len(members),
                "folios": [row["folio"] for row in members],
                # El N° DGAC va junto al folio: hasta que el anexo de registro lo
                # traiga, es la única hoja del papel que lo dice.
                "permits": [
                    {"folio": row["folio"], "dgac": row.get("dgac_number")}
                    for row in members
                ],
                "days": days,
                "band": permit_band(days),
            }
        )
    return lines


def _group(code, name, rows):
    lines = _lines(rows)
    days = min(line["days"] for line in lines)
    return {
        "code": code,
        "name": name,
        "count": len(rows),
        "days": days,
        "band": permit_band(days),
        "next_expiry": min(row["valid_until"] for row in rows),
        "lines": lines,
        # Una sola tupla: la faena es una línea y sus datos van en la cabecera.
        "single": len(lines) == 1,
        "folios": sorted((row["folio"] for row in rows)),
    }


def permit_groups(payload):
    """Todo lo que la sección 2 v2 dibuja, calculado una sola vez desde el payload."""
    permits = payload.get("permits") or []
    names = {
        row["code"]: row.get("name") or "" for row in payload.get("cost_centres") or []
    }
    outside_info = {row["code"]: row for row in payload.get("outside_centres") or []}

    in_force = [row for row in permits if row.get("in_force")]
    by_centre = {}
    outside_by_centre = {}
    for row in in_force:
        target = by_centre if row.get("in_operation") else outside_by_centre
        target.setdefault(row["cost_centre"], []).append(row)

    operating = sorted(
        (_group(code, names.get(code, ""), rows) for code, rows in by_centre.items()),
        key=lambda group: (group["days"], group["code"]),
    )
    outside = []
    for code in sorted(outside_by_centre):
        group = _group(
            code, outside_info.get(code, {}).get("name", ""), outside_by_centre[code]
        )
        group["reason"] = outside_info.get(code, {}).get("reason")
        outside.append(group)

    awaiting = [row for row in permits if row.get("status") == "requested"]
    lapsed = [
        row
        for row in permits
        if not row.get("in_force") and row.get("status") == "approved"
    ]
    return {
        "operating": operating,
        "outside": outside,
        "awaiting": awaiting,
        "lapsed": lapsed,
        "operating_in_force": sum(group["count"] for group in operating),
        "outside_in_force": sum(group["count"] for group in outside),
        "centres": len(operating),
    }


def strip_marks(groups):
    """Los puntos de la tira de vencimientos: `(días, cantidad, código, banda)`.

    Uno por faena y fecha. Lo que vence después de `STRIP_DAYS` no se dibuja: se
    cuenta aparte (`beyond`), porque una marca fuera de escala se lee como un
    vencimiento en el borde.
    """
    merged, beyond = {}, 0
    for group in groups:
        for line in group["lines"]:
            if line["days"] > STRIP_DAYS:
                beyond += line["count"]
                continue
            # Una marca por faena **y fecha**: siete permisos con la misma
            # fecha, aunque difieran en aeronave, son un solo vencimiento.
            key = (max(line["days"], 0), group["code"], line["band"])
            merged[key] = merged.get(key, 0) + line["count"]
    marks = sorted(
        ((days, count, code, band) for (days, code, band), count in merged.items()),
        key=lambda mark: (mark[0], mark[2]),
    )
    return marks, beyond
