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

// Editable popup (editor, GEO-8): name + description inputs, an Apply button.
// `node` is the live canonical placemark; onApply(name, description) persists.
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

  const apply = document.createElement("button");
  apply.type = "button";
  apply.className = "btn btn-sm btn-primary mt-1";
  apply.textContent = labels.apply || "Apply";
  apply.addEventListener("click", () => onApply(nameInput.value, descInput.value));

  root.append(nameInput, descInput, apply);

  const line = measurementLine(node.geometry, labels);
  if (line) {
    root.appendChild(line);
  }
  return root;
}
