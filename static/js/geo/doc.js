// Canonical "AeroKML JSON" -> renderable items. Coordinates in the canonical
// are already [lon, lat, alt?] (GeoJSON order), so geometries pass straight to
// Leaflet's L.geoJSON. This module never mutates the document.

// Flatten the folder tree into a list of placemarks, keeping each one's folder
// path so the layer panel can group them. Sibling order is preserved.
export function collectFeatures(doc) {
  const items = [];
  function walk(nodes, path) {
    for (const node of nodes || []) {
      if (node.kind === "folder") {
        walk(node.children, [...path, node.name || ""]);
      } else if (node.kind === "placemark" && node.geometry) {
        items.push({
          uid: node.uid || `f-${items.length}`,
          name: node.name || "",
          description: node.description || "",
          folderPath: path,
          geometry: node.geometry,
        });
      }
    }
  }
  walk(doc.children, []);
  return items;
}

// Group items by their (joined) folder path, preserving first-seen order.
export function groupByFolder(items, rootLabel) {
  const groups = new Map();
  for (const item of items) {
    const key = item.folderPath.length ? item.folderPath.join(" / ") : rootLabel;
    if (!groups.has(key)) {
      groups.set(key, []);
    }
    groups.get(key).push(item);
  }
  return groups;
}

export function toGeoJSON(item) {
  return {
    type: "Feature",
    geometry: item.geometry,
    properties: { uid: item.uid, name: item.name },
  };
}
