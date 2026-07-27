// Feature popup content. KML name/description may contain HTML/CDATA, so it is
// ALWAYS rendered with textContent, never innerHTML (threat model, GEO §4).

import { measureGeometry, formatLength, formatArea } from "./measure.js";

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

  const measurement = measureGeometry(item.geometry);
  if (measurement) {
    const line = document.createElement("p");
    line.className = "geo-popup-measure";
    if (measurement.kind === "length") {
      line.textContent = `${labels.length}: ${formatLength(measurement.meters)}`;
    } else {
      line.textContent = `${labels.area}: ${formatArea(measurement.squareMeters)}`;
    }
    root.appendChild(line);
  }

  return root;
}
