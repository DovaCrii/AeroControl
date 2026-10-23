"""Buscador puro del espacio aéreo (LV-357, fase 2).

`parse_query` decide qué le están preguntando al buscador único y lo
normaliza; `search_index` lo aplica sobre un índice de entradas
(``{"name": ..., "code": ...}``). Sin modelos, sin ORM, sin texto visible.

Tipos de consulta (``parse_query(...)["type"]``):

* ``empty``: nada que buscar.
* ``coordinate``: ``lat`` y ``lon`` decimales, venga como decimal o GMS.
* ``invalid_coordinate``: parecía una coordenada pero no lo es (fuera de
  rango, minutos >= 60, signo y hemisferio a la vez...); ``reason`` dice por
  qué. Nunca lanza.
* ``zone``: código de zona normalizado, p. ej. ``SC-R41``.
* ``oaci``: cuatro letras, p. ej. ``SCEL``.
* ``name``: todo lo demás.

Todas las respuestas llevan ``name``: el texto normalizado (sin tildes, en
minúsculas) por si quien llama quiere caer a la búsqueda por nombre, por
ejemplo cuando cuatro letras eran en realidad una palabra.
"""

import re
import unicodedata

DEFAULT_ZONE_PREFIX = "SC"

_DASHES = "‐‑‒–—―−"

_ZONE_RE = re.compile(r"^(?:([A-Z]{2}))?\s*-?\s*([PRD])\s*-?\s*0*(\d{1,3})$")
_OACI_RE = re.compile(r"^[A-Z]{4}$")
_NUMBER_RE = re.compile(r"^[+-]?\d+(?:\.\d+)?$")
_DMS_TOKEN_RE = re.compile(r"[NSEW]|[+-]?\d+(?:[.,]\d+)?")
_DMS_SYMBOLS = "°º˚′’'″\"”“`´"


def normalize_text(text):
    """Minúsculas, sin tildes, sólo letras/dígitos separados por un espacio."""
    decomposed = unicodedata.normalize("NFKD", str(text or ""))
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", stripped.casefold()).strip()


def normalize_zone_code(text):
    """`sc r-41`, `SC – P 30`, `R41`, `P 50` -> `SC-R41`; None si no es un código."""
    cleaned = str(text or "").upper()
    for dash in _DASHES:
        cleaned = cleaned.replace(dash, "-")
    match = _ZONE_RE.match(cleaned.strip())
    if not match:
        return None
    prefix, letter, number = match.groups()
    return f"{prefix or DEFAULT_ZONE_PREFIX}-{letter}{int(number)}"


def _invalid(reason, name):
    return {"type": "invalid_coordinate", "reason": reason, "name": name}


def _check_range(lat, lon):
    if not (-90.0 <= lat <= 90.0):
        return "latitude_out_of_range"
    if not (-180.0 <= lon <= 180.0):
        return "longitude_out_of_range"
    return None


def _parse_decimal_pair(text):
    """Dos números decimales separados por coma, punto y coma o espacio."""
    cleaned = text.replace("°", " ").strip()
    if ";" in cleaned:
        parts = [p.replace(",", ".").strip() for p in cleaned.split(";")]
    elif cleaned.count(",") == 1:
        parts = [p.strip() for p in cleaned.split(",")]
    else:
        # Sin separador explícito: espacios, y la coma es decimal.
        parts = [p.replace(",", ".") for p in cleaned.split()]
    if len(parts) != 2 or not all(_NUMBER_RE.match(p) for p in parts):
        return None
    return float(parts[0]), float(parts[1])


def _group_value(numbers):
    """Grados, minutos, segundos -> grados decimales. None si es inválido."""
    if not 1 <= len(numbers) <= 3:
        return None
    values = [float(n.replace(",", ".")) for n in numbers]
    if any(v < 0 for v in values):
        return None
    if len(values) > 1 and values[1] >= 60:
        return None
    if len(values) > 2 and values[2] >= 60:
        return None
    degrees = values[0]
    minutes = values[1] if len(values) > 1 else 0.0
    seconds = values[2] if len(values) > 2 else 0.0
    return degrees + minutes / 60.0 + seconds / 3600.0


def _parse_hemisphere_pair(text):
    """GMS o decimal con hemisferio: `33 26 28 S 70 39 17 W`, `S33 26 28 W70...`.

    Devuelve None si no tiene la forma, o (lat, lon) | ("error", motivo)."""
    cleaned = text.upper()
    for symbol in _DMS_SYMBOLS:
        cleaned = cleaned.replace(symbol, " ")
    tokens = _DMS_TOKEN_RE.findall(cleaned)
    # Todo el texto debe ser tokens reconocibles: nada de sobrantes.
    if re.sub(_DMS_TOKEN_RE, "", cleaned).strip(" ,;"):
        return None
    letters = [t for t in tokens if t in "NSEW"]
    if len(letters) != 2:
        return None
    leading = tokens[0] in "NSEW"
    parsed = []
    current = []
    for token in tokens:
        if token in "NSEW":
            if leading:
                current = []
                parsed.append((token, current))
            else:
                parsed.append((token, current))
                current = []
        else:
            current.append(token)
    if not leading and current:  # números sobrantes tras la última letra
        return None
    if len(parsed) != 2:
        return None
    axes = {"N": "lat", "S": "lat", "E": "lon", "W": "lon"}
    if {axes[parsed[0][0]], axes[parsed[1][0]]} != {"lat", "lon"}:
        return ("error", "same_axis_twice")
    result = {}
    for letter, numbers in parsed:
        if any(n.startswith(("-", "+")) for n in numbers):
            return ("error", "sign_and_hemisphere")
        value = _group_value(numbers)
        if value is None:
            return ("error", "invalid_minutes_or_seconds")
        result[axes[letter]] = -value if letter in "SW" else value
    return result["lat"], result["lon"]


def parse_coordinate(text):
    """(lat, lon, formato) | ("error", motivo) | None si no parece coordenada."""
    stripped = str(text or "").strip()
    if not stripped:
        return None
    if re.search(r"[NSEW]", stripped.upper()):
        # Con letras sólo es coordenada si hay dígitos y 2 hemisferios claros.
        if not re.search(r"\d", stripped):
            return None
        pair = _parse_hemisphere_pair(stripped)
        if pair is None:
            return None
        if pair[0] == "error":
            return pair
        return pair[0], pair[1], "dms"
    pair = _parse_decimal_pair(stripped)
    if pair is None:
        return None
    return pair[0], pair[1], "decimal"


def parse_query(text):
    """Clasifica y normaliza la consulta. Ver el docstring del módulo."""
    raw = str(text or "").strip()
    name = normalize_text(raw)
    if not raw:
        return {"type": "empty", "name": ""}
    coordinate = parse_coordinate(raw)
    if coordinate is not None:
        if coordinate[0] == "error":
            return _invalid(coordinate[1], name)
        lat, lon, fmt = coordinate
        reason = _check_range(lat, lon)
        if reason:
            return _invalid(reason, name)
        return {
            "type": "coordinate",
            "lat": lat,
            "lon": lon,
            "format": fmt,
            "name": name,
        }
    zone = normalize_zone_code(raw)
    if zone:
        return {"type": "zone", "code": zone, "name": name}
    upper = raw.upper()
    if _OACI_RE.match(upper):
        return {"type": "oaci", "code": upper, "name": name}
    return {"type": "name", "name": name}


def name_score(query_name, candidate_name):
    """Puntaje de un nombre: exacto 100 > prefijo 80 > palabra 60 > subcadena 40.

    Ambos textos ya normalizados con `normalize_text`. 0 si no coincide.
    «Palabra» = cada palabra de la consulta empieza una palabra del nombre."""
    if not query_name or not candidate_name:
        return 0
    if candidate_name == query_name:
        return 100
    if candidate_name.startswith(query_name):
        return 80
    words = candidate_name.split()
    if all(any(w.startswith(q) for w in words) for q in query_name.split()):
        return 60
    if query_name in candidate_name:
        return 40
    return 0


def search_index(query, entries, limit=20):
    """Busca en `entries` (dicts con `name` y opcionalmente `code`).

    Devuelve ``{"query": parse_query(...), "results": [{"entry", "score"}]}``,
    ordenado por puntaje y luego por nombre. Una consulta de coordenada no
    devuelve resultados: quien llama usa `lat`/`lon` (p. ej. «qué hay cerca»).
    Un código OACI o de zona que no existe en el índice cae a nombre."""
    parsed = parse_query(query)
    kind = parsed["type"]
    if kind in ("empty", "coordinate", "invalid_coordinate"):
        return {"query": parsed, "results": []}
    results = []
    if kind in ("oaci", "zone"):
        wanted = parsed["code"]
        for entry in entries:
            code = str(entry.get("code") or "")
            if kind == "zone":
                code = normalize_zone_code(code) or code.upper()
            else:
                code = code.upper()
            if code == wanted:
                results.append({"entry": entry, "score": 100})
        if results:
            return {"query": parsed, "results": results[:limit]}
    for entry in entries:
        score = max(
            name_score(parsed["name"], normalize_text(entry.get("name"))),
            name_score(parsed["name"], normalize_text(entry.get("code"))),
        )
        if score:
            results.append({"entry": entry, "score": score})
    results.sort(key=lambda r: (-r["score"], normalize_text(r["entry"].get("name"))))
    return {"query": parsed, "results": results[:limit]}


ADMIN_ID_PREFIX = "admin:"


def admin_entries(index):
    """Las comunas y regiones del padrón de `administrative_layer.search_index()` como entradas de
    búsqueda (LV-367, fase 7): `id` con prefijo `admin:`, sin código (el código BCN no es algo que se
    escriba) y el resto tal cual. `airspace-search.js` tiene el mismo `adminEntries`; los dos corren los
    mismos casos en `apps/airspace/test_lv367_admin_search.py`."""
    return [
        {
            "id": ADMIN_ID_PREFIX + str(item["code"]),
            "code": "",
            "name": item["name"],
            "kind": item["kind"],
            "region": item.get("region") or "",
            "bbox": item["bbox"],
        }
        for item in index
    ]
