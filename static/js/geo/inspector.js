// Feature popup content. KML name/description may contain HTML/CDATA, so read
// values are ALWAYS rendered with textContent / input.value, never innerHTML
// (threat model, GEO §4). In editable mode the popup exposes name/description
// inputs that write back to the placemark node.

import { measureGeometry, formatLength, formatArea } from "./measure.js";

function measurementLine(geometry, labels) {
  const measurement = measureGeometry(geometry);
  if (!measurement) {
    return null;
  }
  const line = document.createElement("p");
  line.className = "geo-popup-measure";
  line.textContent =
    measurement.kind === "length"
      ? `${labels.length}: ${formatLength(measurement.meters)}`
      : `${labels.area}: ${formatArea(measurement.squareMeters)}`;
  return line;
}

// Read-only popup (viewer, GEO-7).
export function buildPopup(item, labels) {
  const root = document.createElement("div");
  root.className = "geo-popup";

  const title = document.createElement("strong");
  title.textContent = item.name || labels.untitled;
  root.appendChild(title);

  if (item.description) {
    const desc = document.createElement("p");
    desc.className = "geo-popup-desc";
    desc.textContent = item.description; // never innerHTML
    root.appendChild(desc);
  }

  const line = measurementLine(item.geometry, labels);
  if (line) {
    root.appendChild(line);
  }
  return root;
}

// `UX-28` (WCAG 2.2 §2.5.7): la lista de vértices de una geometría, y cómo
// volver a escribirlos.
//
// El criterio de éxito pide que **toda** operación que se hace arrastrando tenga
// una alternativa de un solo puntero. Acá la operación es mover un vértice con
// Geoman, y hasta ahora no había otra forma: quien no puede arrastrar —un
// temblor, una pantalla táctil chica, un ratón de cabeza— no podía corregir una
// coordenada.
//
// *Beneficio doble*, y por eso la fila lo dice: es también lo que se transcribe
// a SIGO. Leer los números de la geometría exigía abrir el KMZ aparte.
//
// Se devuelve `null` para lo que no tiene lista de vértices que valga la pena
// mostrar: sin geometría, o con un tipo que este documento no maneja.
function coordinateRows(geometry) {
  if (!geometry || !geometry.coordinates) {
    return null;
  }
  if (geometry.type === "Point") {
    return { path: [], points: [geometry.coordinates], closed: false };
  }
  if (geometry.type === "LineString") {
    return { path: [], points: geometry.coordinates, closed: false };
  }
  if (geometry.type === "Polygon" && geometry.coordinates.length) {
    const ring = geometry.coordinates[0];
    // ⚠️ El último punto de un anillo KML **repite** el primero. Se esconde a
    // propósito: mostrarlo obligaría a editar la misma esquina dos veces, y
    // olvidarse de la segunda deja el polígono abierto — o sea un archivo que
    // el validador rechaza por un descuido que la pantalla invitó a cometer.
    const closed =
      ring.length > 2 &&
      ring[0][0] === ring[ring.length - 1][0] &&
      ring[0][1] === ring[ring.length - 1][1];
    return {
      path: [0],
      points: closed ? ring.slice(0, -1) : ring,
      closed,
    };
  }
  return null;
}

function buildCoordinateTable(node, labels) {
  const rows = coordinateRows(node.geometry);
  if (!rows) {
    return null;
  }

  const box = document.createElement("div");
  box.className = "geo-popup-coords";

  const heading = document.createElement("div");
  heading.className = "geo-popup-coords-title";
  heading.textContent = labels.coordinates || "Coordinates";
  box.appendChild(heading);

  const hint = document.createElement("p");
  hint.className = "geo-popup-coords-hint";
  hint.textContent = labels.coordinatesHint || "";
  box.appendChild(hint);

  const table = document.createElement("table");
  table.className = "geo-coord-table";
  const head = table.createTHead().insertRow();
  [labels.vertex || "#", labels.latitude || "Lat", labels.longitude || "Lon"].forEach(
    (text) => {
      const cell = document.createElement("th");
      cell.scope = "col";
      cell.textContent = text;
      head.appendChild(cell);
    },
  );

  const body = table.createTBody();
  const inputs = [];
  rows.points.forEach((point, index) => {
    const row = body.insertRow();
    const number = document.createElement("th");
    number.scope = "row";
    number.textContent = String(index + 1);
    row.appendChild(number);
    // El orden en pantalla es lat/lon, que es como se dicta una coordenada y
    // como se transcribe a SIGO. En el documento van al revés (lon/lat, que es
    // el orden de GeoJSON y KML) y esa vuelta se hace al aplicar, una sola vez:
    // invertir el documento para que coincida con la vista habría cambiado el
    // formato del archivo por una comodidad de pantalla.
    const pair = [1, 0].map((axis) => {
      const cell = row.insertCell();
      const field = document.createElement("input");
      field.type = "number";
      field.step = "any";
      field.className = "form-control form-control-sm geo-coord-input";
      field.value = String(point[axis]);
      field.setAttribute(
        "aria-label",
        `${axis === 1 ? labels.latitude : labels.longitude} ${index + 1}`,
      );
      cell.appendChild(field);
      return field;
    });
    inputs.push({ lat: pair[0], lon: pair[1] });
  });

  box.appendChild(table);

  // Lee lo tipeado y devuelve la geometría nueva, o `null` si algo no es un
  // número. Se rechaza el conjunto entero y no la celda suelta: aplicar la mitad
  // dejaría una figura que nadie pidió, y la persona no vería cuál mitad.
  // ⚠️ **La celda vacía cuenta como inválida, y ése es el punto.** Un
  // `<input type="number">` con basura dentro devuelve `""` —el navegador
  // rechaza lo tipeado y no lo refleja en `value`— y `Number("")` es **0**, que
  // pasa `Number.isFinite` sin chistar. Sin esta comprobación, escribir una
  // letra en una latitud mandaba el vértice al ecuador **en silencio**: la
  // figura cambiaba, nadie lo decía, y quedaba guardada. Encontrado en el
  // navegador con la tabla recién escrita; el guardián que sólo miraba
  // `isFinite` lo dejaba pasar.
  const number = (field) => {
    const raw = field.value.trim();
    return raw === "" ? NaN : Number(raw);
  };
  box.readGeometry = () => {
    const points = inputs.map((pair) => [number(pair.lon), number(pair.lat)]);
    if (points.some((point) => !Number.isFinite(point[0]) || !Number.isFinite(point[1]))) {
      return null;
    }
    if (node.geometry.type === "Point") {
      return { type: "Point", coordinates: points[0] };
    }
    if (node.geometry.type === "LineString") {
      return { type: "LineString", coordinates: points };
    }
    const ring = rows.closed ? points.concat([points[0]]) : points;
    const coordinates = node.geometry.coordinates.slice();
    coordinates[0] = ring;
    return { type: "Polygon", coordinates };
  };
  return box;
}

// Editable popup (editor, GEO-8): name + description inputs, an Apply button.
// `node` is the live canonical placemark; onApply(name, description, geometry)
// persists -- `geometry` llega sólo cuando `UX-28` pudo leer la tabla y quedó
// distinta, así que quien no la tocó guarda exactamente como antes.
export function buildEditablePopup(node, labels, onApply) {
  const root = document.createElement("div");
  root.className = "geo-popup geo-popup-edit";

  const nameInput = document.createElement("input");
  nameInput.type = "text";
  nameInput.className = "form-control form-control-sm";
  nameInput.value = node.name || "";
  nameInput.setAttribute("aria-label", labels.name || "name");

  const descInput = document.createElement("textarea");
  descInput.className = "form-control form-control-sm";
  descInput.rows = 2;
  descInput.value = node.description || "";
  descInput.setAttribute("aria-label", labels.description || "description");

  const coords = buildCoordinateTable(node, labels);

  const apply = document.createElement("button");
  apply.type = "button";
  apply.className = "btn btn-sm btn-primary mt-1";
  apply.textContent = labels.apply || "Apply";
  apply.addEventListener("click", () =>
    onApply(
      nameInput.value,
      descInput.value,
      coords ? coords.readGeometry() : null,
    ),
  );

  root.append(nameInput, descInput);
  if (coords) {
    root.appendChild(coords);
  }
  root.appendChild(apply);

  const line = measurementLine(node.geometry, labels);
  if (line) {
    root.appendChild(line);
  }
  return root;
}
