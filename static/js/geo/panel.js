// Layer panel: one checkbox per folder group, toggling the visibility of that
// group's Leaflet layer on the map. Built entirely with DOM APIs (no innerHTML)
// so it is CSP-safe and cannot inject markup from feature names.

export function buildPanel(container, groups, map, labels) {
  container.replaceChildren();

  const heading = document.createElement("div");
  heading.className = "geo-panel-head";
  heading.textContent = `${labels.layers} · ${labels.features}`;
  container.appendChild(heading);

  for (const [name, layer] of groups) {
    const row = document.createElement("label");
    row.className = "geo-panel-row";

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = true;
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) {
        layer.group.addTo(map);
      } else {
        map.removeLayer(layer.group);
      }
    });

    const text = document.createElement("span");
    text.className = "geo-panel-label";
    text.textContent = name;

    const count = document.createElement("span");
    count.className = "geo-panel-count";
    count.textContent = String(layer.count);

    row.append(checkbox, text, count);
    container.appendChild(row);
  }
}
