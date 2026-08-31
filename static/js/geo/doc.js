// Canonical "AeroKML JSON" -> renderable items. Coordinates in the canonical
// are already [lon, lat, alt?] (GeoJSON order), so geometries pass straight to
// Leaflet's L.geoJSON. This module never mutates the document.

// Flatten the folder tree into a list of placemarks, keeping each one's folder
// path so the layer panel can group them. Sibling order is preserved.
export function collectFeatures(doc) {
  const items = [];
  const styles = doc.shared_styles || {};
  const resources = new Set(doc.kmz_resources || []);
  // GEO-13: an embedded icon is a style href that names a KMZ resource. An
  // external http(s) icon is ignored here (the map keeps a plain marker) so the
  // CSP stays 'self' for images.
  function iconFor(styleUrl) {
    if (!styleUrl) {
      return null;
    }
    const style = styles[styleUrl];
    const icon = style && style.resolved && style.resolved.icon;
    return icon && resources.has(icon) ? icon : null;
  }
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
          iconResource: iconFor(node.style_url),
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
    properties: {
      uid: item.uid,
      name: item.name,
      iconResource: item.iconResource || null,
    },
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

// Append a new placemark. Into the given folder when targetFolderUid names one,
// otherwise to the document root (GEO-11: folder-aware insertion).
export function addPlacemark(doc, uid, geometry, targetFolderUid) {
  const node = {
    kind: "placemark",
    uid,
    name: "",
    description: "",
    geometry,
  };
  const siblings = childListOf(doc, targetFolderUid);
  siblings.push(node);
  return node;
}

// ── GEO-11: tree mutators ──────────────────────────────────────────────────
// All operate on doc.children and mutate in place. The server re-validates the
// resulting tree on commit, so these never need to enforce caps or schema.

// The children array a uid's children live in: a folder's `.children`, or the
// document root when uid is null/undefined/not a folder.
function childListOf(doc, folderUid) {
  if (!Array.isArray(doc.children)) {
    doc.children = [];
  }
  if (!folderUid) {
    return doc.children;
  }
  const folder = findNode(doc, folderUid);
  if (folder && folder.kind === "folder") {
    if (!Array.isArray(folder.children)) {
      folder.children = [];
    }
    return folder.children;
  }
  return doc.children;
}

// Find any node (folder/placemark/raw) by uid, or null.
export function findNode(doc, uid) {
  let found = null;
  function walk(nodes) {
    for (const node of nodes || []) {
      if (found) {
        return;
      }
      if (node.uid === uid) {
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

// Locate a uid's containing array and index: {siblings, index}, or null.
export function findParent(doc, uid) {
  let result = null;
  function walk(nodes) {
    for (let i = 0; i < (nodes || []).length; i += 1) {
      if (result) {
        return;
      }
      const node = nodes[i];
      if (node.uid === uid) {
        result = { siblings: nodes, index: i };
        return;
      }
      if (node.kind === "folder") {
        walk(node.children);
      }
    }
  }
  walk(doc.children);
  return result;
}

// True when `uid` is `ancestorUid` itself or lives anywhere under it. Used to
// refuse dropping a folder into its own subtree.
export function isSelfOrDescendant(doc, ancestorUid, uid) {
  if (ancestorUid === uid) {
    return true;
  }
  const ancestor = findNode(doc, ancestorUid);
  if (!ancestor || ancestor.kind !== "folder") {
    return false;
  }
  let found = false;
  function walk(nodes) {
    for (const node of nodes || []) {
      if (found) {
        return;
      }
      if (node.uid === uid) {
        found = true;
        return;
      }
      if (node.kind === "folder") {
        walk(node.children);
      }
    }
  }
  walk(ancestor.children);
  return found;
}

// Move a node into targetFolderUid (null = root) at position `index` (end when
// index is null/undefined). Returns false on an illegal move (folder into
// itself) or a missing node.
export function moveNode(doc, uid, targetFolderUid, index) {
  if (targetFolderUid && isSelfOrDescendant(doc, uid, targetFolderUid)) {
    return false;
  }
  const parent = findParent(doc, uid);
  if (!parent) {
    return false;
  }
  const [node] = parent.siblings.splice(parent.index, 1);
  const dest = childListOf(doc, targetFolderUid);
  let at = index;
  if (at === null || at === undefined || at > dest.length) {
    at = dest.length;
  }
  // Removing the node may have shifted the target index when moving down within
  // the same array; the caller passes the intended final index, and splice on a
  // now-shorter array lands it correctly for the common cases.
  dest.splice(at, 0, node);
  return true;
}

// Reorder a node within its current parent to `index`.
export function reorderSibling(doc, uid, index) {
  const parent = findParent(doc, uid);
  if (!parent) {
    return false;
  }
  const [node] = parent.siblings.splice(parent.index, 1);
  let at = index;
  if (at === null || at === undefined || at > parent.siblings.length) {
    at = parent.siblings.length;
  }
  parent.siblings.splice(at, 0, node);
  return true;
}

// Deep-clone a subtree, assigning fresh uids to every node (so a duplicate is a
// genuinely new feature, not a second reference to the same uid).
function cloneWithNewUids(node) {
  const copy = JSON.parse(JSON.stringify(node));
  function rekey(n) {
    n.uid = newUid();
    if (n.kind === "folder") {
      for (const child of n.children || []) {
        rekey(child);
      }
    }
  }
  rekey(copy);
  return copy;
}

// Duplicate a node in place, right after the original. Returns the copy or null.
export function duplicateNode(doc, uid) {
  const parent = findParent(doc, uid);
  if (!parent) {
    return null;
  }
  const copy = cloneWithNewUids(parent.siblings[parent.index]);
  parent.siblings.splice(parent.index + 1, 0, copy);
  return copy;
}

// Explode a placemark whose geometry is a GeometryCollection into one placemark
// per sub-geometry, inserted where the original was. Returns the new count, or
// 0 when the node is not an explodable multi-geometry.
export function explodeMultiGeometry(doc, uid) {
  const parent = findParent(doc, uid);
  if (!parent) {
    return 0;
  }
  const node = parent.siblings[parent.index];
  const geom = node.geometry;
  if (
    node.kind !== "placemark" ||
    !geom ||
    geom.type !== "GeometryCollection" ||
    !Array.isArray(geom.geometries) ||
    geom.geometries.length < 2
  ) {
    return 0;
  }
  const parts = geom.geometries.map((sub, i) => ({
    kind: "placemark",
    uid: newUid(),
    name: `${node.name || ""} (${i + 1})`,
    description: node.description || "",
    visibility: node.visibility !== false,
    style_url: node.style_url || null,
    geometry: JSON.parse(JSON.stringify(sub)),
    extended_data: null,
    extras: [],
  }));
  parent.siblings.splice(parent.index, 1, ...parts);
  return parts.length;
}

// Leaflet layer -> canonical geometry ([lon, lat] order, same as GeoJSON).
export function geometryFromLayer(layer) {
  const gj = layer.toGeoJSON();
  return gj && gj.geometry ? gj.geometry : null;
}

// LV-202: los lados con que se poligonaliza una circunferencia dibujada.
//
// Importa el número, no es decorativo: el backend **mide** el radio desde el
// anillo (`estimate_radius_m`) y descarta como "no es un círculo" lo que se
// aparte del radio medio más de `MAX_RADIUS_DEVIATION` (0.10). El comentario de
// esa constante dice que "el círculo de 36 lados que dibujan las herramientas
// queda muy por debajo"; 64 deja el doble de margen y se dibuja igual de rápido.
export const CIRCLE_SIDES = 64;

// El mismo radio terrestre que `apps/geo/sections.py` (IUGG), y por la misma
// razón por la que esa constante está escrita ahí y no aproximada: el radio que
// el usuario dibuja tiene que ser el que el servidor mide y el que después se
// copia a la casilla "Radio (m)" del formulario de SIGO. Con dos constantes
// distintas, la cifra de la hoja de campo no sería la del mapa.
const EARTH_RADIUS_M = 6371008.8;
const DEG = Math.PI / 180;

// LV-202: una circunferencia como anillo cerrado de [lon, lat].
//
// **KML no tiene círculo**, y por eso el editor lo tenía apagado ("no faithful
// KML representation"). Sí lo tiene poligonalizado, que es exactamente cómo
// llegan los círculos reales: los KMZ de Trimble Business Center que el usuario
// usa para CC 738 exportan cada circunferencia como un anillo cerrado, y `R10.4`
// aprendió a leerlos. Dibujar produce ahora lo mismo que importar, así que el
// radio, el centro y la hoja de SIGO salen por el mismo camino ya probado.
//
// La proyección es plana con corrección por latitud, la misma aproximación que
// `estimate_radius_m` usa para los puntos medios de arista: a la escala de una
// solicitud SIGO (decenas o cientos de metros, hasta pocos km) el error queda muy
// por debajo de lo que la casilla del formulario puede expresar.
export function circleRing(center, radiusM, sides = CIRCLE_SIDES) {
  const metersPerDegree = EARTH_RADIUS_M * DEG;
  const dLat = radiusM / metersPerDegree;
  const cos = Math.cos(center.lat * DEG);
  // En un polo `cos` es 0 y la corrección se va al infinito. No hay operación
  // aérea ahí, pero una división por cero produciría `NaN` en las coordenadas y
  // un plan corrupto en vez de un error: se cae al radio en latitud.
  const dLon = Math.abs(cos) < 1e-9 ? dLat : radiusM / (metersPerDegree * cos);
  const ring = [];
  for (let index = 0; index < sides; index += 1) {
    const angle = (2 * Math.PI * index) / sides;
    ring.push([
      center.lng + dLon * Math.cos(angle),
      center.lat + dLat * Math.sin(angle),
    ]);
  }
  // Cerrado explícitamente repitiendo el primer vértice: es lo que
  // `closed_ring_of` comprueba para aceptar el anillo.
  ring.push(ring[0].slice());
  return ring;
}

let uidCounter = 0;
export function newUid() {
  uidCounter += 1;
  return `e-${Date.now().toString(36)}-${uidCounter}`;
}
