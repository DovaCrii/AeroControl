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

// ── Editing helpers (GEO-8): mutate the canonical tree by uid ──────────────

// Find a placemark node anywhere in the tree by its uid, or null.
export function findPlacemark(doc, uid) {
  let found = null;
  function walk(nodes) {
    for (const node of nodes || []) {
      if (found) {
        return;
      }
      if (node.kind === "placemark" && node.uid === uid) {
        found = node;
        return;
      }
      if (node.kind === "folder") {
        walk(node.children);
      }
    }
  }
  walk(doc.children);
  return found;
}

// Remove a placemark by uid from wherever it lives. Returns true if removed.
export function removePlacemark(doc, uid) {
  function walk(nodes) {
    for (let i = 0; i < (nodes || []).length; i += 1) {
      const node = nodes[i];
      if (node.kind === "placemark" && node.uid === uid) {
        nodes.splice(i, 1);
        return true;
      }
      if (node.kind === "folder" && walk(node.children)) {
        return true;
      }
    }
    return false;
  }
  return walk(doc.children);
}

// Append a new placemark to the document root.
export function addPlacemark(doc, uid, geometry) {
  if (!Array.isArray(doc.children)) {
    doc.children = [];
  }
  const node = {
    kind: "placemark",
    uid,
    name: "",
    description: "",
    geometry,
  };
  doc.children.push(node);
  return node;
}

// Leaflet layer -> canonical geometry ([lon, lat] order, same as GeoJSON).
export function geometryFromLayer(layer) {
  const gj = layer.toGeoJSON();
  return gj && gj.geometry ? gj.geometry : null;
}

let uidCounter = 0;
export function newUid() {
  uidCounter += 1;
  return `e-${Date.now().toString(36)}-${uidCounter}`;
}
