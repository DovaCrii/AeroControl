/* LV-357 (fase 3): el buscador único del espacio aéreo, del lado del cliente.

   Es un PORT de `apps/geo/airspace_search.py` (`parse_query`, `search_index`): mismas reglas, mismos
   puntajes. No se reinventa nada: `apps/airspace/test_search_parity.py` corre los mismos casos por
   Node contra la versión de Python y falla si divergen. Si cambia una, cambia la otra.

   Sin texto visible: los motivos de error viajan como claves (`latitude_out_of_range`, ...) y la
   pantalla los traduce. Sin DOM: este archivo sólo calcula. */
(function (root) {
  "use strict";

  var DEFAULT_ZONE_PREFIX = "SC";
  var DASHES = "‐‑‒–—―−";
  var ZONE_RE = /^(?:([A-Z]{2}))?\s*-?\s*([PRD])\s*-?\s*0*(\d{1,3})$/;
  var OACI_RE = /^[A-Z]{4}$/;
  var NUMBER_RE = /^[+-]?\d+(?:\.\d+)?$/;
  var DMS_TOKEN_SRC = "[NSEW]|[+-]?\\d+(?:[.,]\\d+)?";
  var DMS_SYMBOLS = "°º˚′’'″\"”“`´";

  function isLetter(token) {
    return /^[NSEW]$/.test(token);
  }

  function normalizeText(text) {
    var stripped = String(text == null ? "" : text)
      .normalize("NFKD")
      .replace(/[̀-ͯ]/g, "");
    return stripped.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  }

  function normalizeZoneCode(text) {
    var cleaned = String(text == null ? "" : text).toUpperCase();
    for (var i = 0; i < DASHES.length; i += 1) {
      cleaned = cleaned.split(DASHES[i]).join("-");
    }
    var match = ZONE_RE.exec(cleaned.trim());
    if (!match) {
      return null;
    }
    return (match[1] || DEFAULT_ZONE_PREFIX) + "-" + match[2] + parseInt(match[3], 10);
  }

  function invalid(reason, name) {
    return { type: "invalid_coordinate", reason: reason, name: name };
  }

  function checkRange(lat, lon) {
    if (!(lat >= -90 && lat <= 90)) {
      return "latitude_out_of_range";
    }
    if (!(lon >= -180 && lon <= 180)) {
      return "longitude_out_of_range";
    }
    return null;
  }

  function splitWhitespace(text) {
    return text.split(/\s+/).filter(function (part) {
      return part.length;
    });
  }

  function parseDecimalPair(text) {
    var cleaned = text.split("°").join(" ").trim();
    var parts;
    if (cleaned.indexOf(";") !== -1) {
      parts = cleaned.split(";").map(function (p) {
        return p.split(",").join(".").trim();
      });
    } else if (cleaned.split(",").length - 1 === 1) {
      parts = cleaned.split(",").map(function (p) {
        return p.trim();
      });
    } else {
      parts = splitWhitespace(cleaned).map(function (p) {
        return p.split(",").join(".");
      });
    }
    if (parts.length !== 2 || !parts.every(function (p) { return NUMBER_RE.test(p); })) {
      return null;
    }
    return [parseFloat(parts[0]), parseFloat(parts[1])];
  }

  function groupValue(numbers) {
    if (numbers.length < 1 || numbers.length > 3) {
      return null;
    }
    var values = numbers.map(function (n) {
      return parseFloat(n.split(",").join("."));
    });
    if (values.some(function (v) { return v < 0; })) {
      return null;
    }
    if (values.length > 1 && values[1] >= 60) {
      return null;
    }
    if (values.length > 2 && values[2] >= 60) {
      return null;
    }
    var minutes = values.length > 1 ? values[1] : 0;
    var seconds = values.length > 2 ? values[2] : 0;
    return values[0] + minutes / 60 + seconds / 3600;
  }

  // null | {error: reason} | {lat, lon}
  function parseHemispherePair(text) {
    var cleaned = text.toUpperCase();
    for (var i = 0; i < DMS_SYMBOLS.length; i += 1) {
      cleaned = cleaned.split(DMS_SYMBOLS[i]).join(" ");
    }
    var tokens = cleaned.match(new RegExp(DMS_TOKEN_SRC, "g")) || [];
    var leftover = cleaned.replace(new RegExp(DMS_TOKEN_SRC, "g"), "");
    if (leftover.replace(/^[ ,;]+|[ ,;]+$/g, "")) {
      return null;
    }
    var letters = tokens.filter(isLetter);
    if (letters.length !== 2) {
      return null;
    }
    var leading = isLetter(tokens[0]);
    var parsed = [];
    var current = [];
    tokens.forEach(function (token) {
      if (isLetter(token)) {
        if (leading) {
          current = [];
          parsed.push([token, current]);
        } else {
          parsed.push([token, current]);
          current = [];
        }
      } else {
        current.push(token);
      }
    });
    if (!leading && current.length) {
      return null;
    }
    if (parsed.length !== 2) {
      return null;
    }
    var axes = { N: "lat", S: "lat", E: "lon", W: "lon" };
    if (axes[parsed[0][0]] === axes[parsed[1][0]]) {
      return { error: "same_axis_twice" };
    }
    var result = {};
    for (var k = 0; k < parsed.length; k += 1) {
      var letter = parsed[k][0];
      var numbers = parsed[k][1];
      if (numbers.some(function (n) { return n[0] === "-" || n[0] === "+"; })) {
        return { error: "sign_and_hemisphere" };
      }
      var value = groupValue(numbers);
      if (value === null) {
        return { error: "invalid_minutes_or_seconds" };
      }
      result[axes[letter]] = letter === "S" || letter === "W" ? -value : value;
    }
    return { lat: result.lat, lon: result.lon };
  }

  // null (no parece coordenada) | {error} | {lat, lon, format}
  function parseCoordinate(text) {
    var stripped = String(text == null ? "" : text).trim();
    if (!stripped) {
      return null;
    }
    if (/[NSEW]/.test(stripped.toUpperCase())) {
      if (!/\d/.test(stripped)) {
        return null;
      }
      var pair = parseHemispherePair(stripped);
      if (pair === null) {
        return null;
      }
      if (pair.error) {
        return pair;
      }
      return { lat: pair.lat, lon: pair.lon, format: "dms" };
    }
    var decimal = parseDecimalPair(stripped);
    if (decimal === null) {
      return null;
    }
    return { lat: decimal[0], lon: decimal[1], format: "decimal" };
  }

  function parseQuery(text) {
    var raw = String(text == null ? "" : text).trim();
    var name = normalizeText(raw);
    if (!raw) {
      return { type: "empty", name: "" };
    }
    var coordinate = parseCoordinate(raw);
    if (coordinate !== null) {
      if (coordinate.error) {
        return invalid(coordinate.error, name);
      }
      var reason = checkRange(coordinate.lat, coordinate.lon);
      if (reason) {
        return invalid(reason, name);
      }
      return {
        type: "coordinate",
        lat: coordinate.lat,
        lon: coordinate.lon,
        format: coordinate.format,
        name: name,
      };
    }
    var zone = normalizeZoneCode(raw);
    if (zone) {
      return { type: "zone", code: zone, name: name };
    }
    var upper = raw.toUpperCase();
    if (OACI_RE.test(upper)) {
      return { type: "oaci", code: upper, name: name };
    }
    return { type: "name", name: name };
  }

  function nameScore(queryName, candidateName) {
    if (!queryName || !candidateName) {
      return 0;
    }
    if (candidateName === queryName) {
      return 100;
    }
    if (candidateName.indexOf(queryName) === 0) {
      return 80;
    }
    var words = candidateName.split(" ");
    var wanted = queryName.split(" ");
    var everyWordStarts = wanted.every(function (q) {
      return words.some(function (w) {
        return w.indexOf(q) === 0;
      });
    });
    if (everyWordStarts) {
      return 60;
    }
    if (candidateName.indexOf(queryName) !== -1) {
      return 40;
    }
    return 0;
  }

  function searchIndex(query, entries, limit) {
    var max = limit == null ? 20 : limit;
    var parsed = parseQuery(query);
    var kind = parsed.type;
    if (kind === "empty" || kind === "coordinate" || kind === "invalid_coordinate") {
      return { query: parsed, results: [] };
    }
    var results = [];
    if (kind === "oaci" || kind === "zone") {
      var wanted = parsed.code;
      entries.forEach(function (entry) {
        var code = String(entry.code || "");
        if (kind === "zone") {
          code = normalizeZoneCode(code) || code.toUpperCase();
        } else {
          code = code.toUpperCase();
        }
        if (code === wanted) {
          results.push({ entry: entry, score: 100 });
        }
      });
      if (results.length) {
        return { query: parsed, results: results.slice(0, max) };
      }
    }
    entries.forEach(function (entry) {
      var score = Math.max(
        nameScore(parsed.name, normalizeText(entry.name)),
        nameScore(parsed.name, normalizeText(entry.code))
      );
      if (score) {
        results.push({ entry: entry, score: score });
      }
    });
    results.sort(function (a, b) {
      if (b.score !== a.score) {
        return b.score - a.score;
      }
      var an = normalizeText(a.entry.name);
      var bn = normalizeText(b.entry.name);
      return an < bn ? -1 : an > bn ? 1 : 0;
    });
    return { query: parsed, results: results.slice(0, max) };
  }

  /* Lo propio de la pantalla (no está en Python): una consulta de nombre también mira la región y la
     comuna que la fuente le dio a los puntos, con un puntaje menor que el nombre. Cada entrada trae
     `places` ya normalizado. */
  var PLACE_SCORE = 50;

  function searchFeatures(query, entries, limit) {
    var max = limit == null ? 20 : limit;
    var found = searchIndex(query, entries, entries.length);
    if (found.query.type === "name" && found.query.name) {
      var seen = {};
      found.results.forEach(function (r) {
        seen[r.entry.id] = true;
      });
      entries.forEach(function (entry) {
        if (!seen[entry.id] && entry.places && nameScore(found.query.name, entry.places) >= 40) {
          found.results.push({ entry: entry, score: PLACE_SCORE });
        }
      });
      found.results.sort(function (a, b) {
        if (b.score !== a.score) {
          return b.score - a.score;
        }
        var an = normalizeText(a.entry.name);
        var bn = normalizeText(b.entry.name);
        return an < bn ? -1 : an > bn ? 1 : 0;
      });
    }
    found.total = found.results.length;
    found.results = found.results.slice(0, max);
    return found;
  }

  /* LV-367 (fase 7): las comunas y regiones como entradas de búsqueda; espejo de
     `airspace_search.admin_entries` (mismos campos). Sin código: el código BCN no se escribe. */
  var ADMIN_ID_PREFIX = "admin:";

  function adminEntries(index) {
    return index.map(function (item) {
      return {
        id: ADMIN_ID_PREFIX + String(item.code),
        code: "",
        name: item.name,
        kind: item.kind,
        region: item.region || "",
        bbox: item.bbox,
      };
    });
  }

  var api = {
    ADMIN_ID_PREFIX: ADMIN_ID_PREFIX,
    adminEntries: adminEntries,
    normalizeText: normalizeText,
    normalizeZoneCode: normalizeZoneCode,
    parseQuery: parseQuery,
    nameScore: nameScore,
    searchIndex: searchIndex,
    searchFeatures: searchFeatures,
  };
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.AirspaceSearch = api;
  }
})(typeof window !== "undefined" ? window : this);
