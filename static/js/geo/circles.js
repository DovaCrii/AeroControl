// LV-277: una circunferencia y su centro, geometría pura.
//
// Una circunferencia dibujada deja **dos** elementos en el documento: el anillo y un
// punto «Centro» (`edit.js`, LV-202). No hay vínculo entre ellos: el documento es el
// árbol del KML y KML no tiene círculos. Al arrastrar el anillo el centro se quedaba
// donde estaba, y la hoja de SIGO —que copia el centro— quedaba con una coordenada
// que ya no era la del círculo. Este módulo contesta una sola pregunta: **qué punto
// es el centro de qué anillo**, con el mismo criterio con que lo decide el servidor
// (`apps/geo/sections.py`, `split_sections`), para que el centro que se mueve en el
// mapa sea el que la hoja de SIGO va a copiar.
//
// Sin Leaflet y sin DOM a propósito: así se ejercita en Node (`test_lv277_...py`) y no
// sólo se describe. Las constantes se copian del servidor y hay un test que las cruza.

// El mismo radio terrestre y el mismo umbral que `sections.py`.
const EARTH_RADIUS_M = 6371008.8;
const DEG = Math.PI / 180;
export const MAX_RADIUS_DEVIATION = 0.10;

// `[lon, lat]` -> metros, esférico (haversine), igual que `haversine_km`.
export function haversineM(lat1, lon1, lat2, lon2) {
  const phi1 = lat1 * DEG;
  const phi2 = lat2 * DEG;
  const dPhi = (lat2 - lat1) * DEG;
  const dLambda = (lon2 - lon1) * DEG;
  const a =
    Math.sin(dPhi / 2) ** 2 +
    Math.cos(phi1) * Math.cos(phi2) * Math.sin(dLambda / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.sqrt(a));
}

// El KML repite el primer vértice al final.
function ringVertices(ring) {
  if (
    ring.length > 1 &&
    ring[0][0] === ring[ring.length - 1][0] &&
    ring[0][1] === ring[ring.length - 1][1]
  ) {
    return ring.slice(0, -1);
  }
  return ring;
}

// Media simple de los vértices: para una circunferencia ES el centro.
export function ringCentroid(ring) {
  const vertices = ringVertices(ring);
  let lat = 0;
  let lng = 0;
  for (const v of vertices) {
    lng += v[0];
    lat += v[1];
  }
  return { lat: lat / vertices.length, lng: lng / vertices.length };
}

// (radio medio en metros, desviación relativa) del anillo contra un centro. Mide los
// vértices **y el punto medio de cada arista**, como `estimate_radius_m`: las cuatro
// esquinas de un rectángulo equidistan de su centro, y sólo el punto medio de la
// arista lo delata como «no es un círculo».
export function radiusStats(center, ring) {
  const vertices = ringVertices(ring);
  const distances = [];
  vertices.forEach((vertex, index) => {
    const next = vertices[(index + 1) % vertices.length];
    distances.push(haversineM(center.lat, center.lng, vertex[1], vertex[0]));
    distances.push(
      haversineM(
        center.lat,
        center.lng,
        (vertex[1] + next[1]) / 2,
        (vertex[0] + next[0]) / 2,
      ),
    );
  });
  const mean = distances.reduce((sum, d) => sum + d, 0) / distances.length;
  if (mean === 0) {
    return { meanM: 0, deviation: 0 };
  }
  return {
    meanM: mean,
    deviation: (Math.max(...distances) - Math.min(...distances)) / mean,
  };
}

// El anillo exterior de un placemark que encierra un área, o null. Igual que
// `closed_ring_of`: un Polygon lo trae en su primer anillo, y un LineString **cerrado**
// (como lo exporta Trimble) también; uno abierto es un trazado y se ignora.
export function closedRingOf(geometry) {
  const coordinates = geometry && geometry.coordinates;
  if (!coordinates || !coordinates.length) {
    return null;
  }
  if (geometry.type === "Polygon") {
    return coordinates[0];
  }
  if (
    geometry.type === "LineString" &&
    coordinates.length >= 4 &&
    coordinates[0][0] === coordinates[coordinates.length - 1][0] &&
    coordinates[0][1] === coordinates[coordinates.length - 1][1]
  ) {
    return coordinates;
  }
  return null;
}

function placemarksOf(doc) {
  const found = [];
  (function walk(nodes) {
    for (const node of nodes || []) {
      if (node.kind === "placemark") {
        found.push(node);
      } else if (node.kind === "folder") {
        walk(node.children);
      }
    }
  })(doc.children);
  return found;
}

// Qué punto es el centro de qué anillo: `Map(uid del anillo -> uid del punto)`.
//
// El **reparto** es el del servidor: todos los pares (anillo, punto) dentro de
// `max(3 × radio, 100 m)`, y un reclamo voraz por distancia, de modo que cada punto
// lo toma un solo anillo y cada anillo un solo punto. Con «el punto más cercano de
// cada anillo» dos círculos con puntos coincidentes se disputaban el mismo y uno
// quedaba huérfano; el servidor ya pagó esa lección con el KMZ real de MLP.
//
// **Y se agrega una condición que el servidor no tiene**, porque acá el emparejamiento
// no sólo se muestra: se **arrastra**. Sólo cuenta como centro lo que está **dentro**
// del círculo (a menos de un radio del centro). Un punto a dos radios de distancia
// puede ser el de otra faena que casualmente quedó cerca, y moverlo porque alguien
// arrastró un círculo vecino sería cambiar un dato que nadie tocó.
//
// Sólo anillos que son círculos (`deviation <= MAX_RADIUS_DEVIATION`): un rectángulo o
// un polígono a mano no tiene centro que seguir.
export function pairCircleCenters(doc) {
  const points = [];
  const rings = [];
  for (const node of placemarksOf(doc)) {
    const geometry = node.geometry || {};
    if (geometry.type === "Point" && geometry.coordinates && geometry.coordinates.length) {
      points.push({ uid: node.uid, coords: geometry.coordinates });
      continue;
    }
    const ring = closedRingOf(geometry);
    if (ring) {
      const center = ringCentroid(ring);
      const { meanM, deviation } = radiusStats(center, ring);
      rings.push({ uid: node.uid, center, radiusM: meanM, deviation });
    }
  }

  const candidates = [];
  rings.forEach((ring, ringIndex) => {
    const threshold = Math.max(3 * ring.radiusM, 100);
    points.forEach((point, pointIndex) => {
      const distance = haversineM(
        ring.center.lat,
        ring.center.lng,
        point.coords[1],
        point.coords[0],
      );
      if (distance <= threshold) {
        candidates.push({ distance, ringIndex, pointIndex });
      }
    });
  });
  candidates.sort((a, b) => a.distance - b.distance);

  const claimedPoints = new Set();
  const claimedRings = new Set();
  const pairs = new Map();
  for (const { distance, ringIndex, pointIndex } of candidates) {
    if (claimedPoints.has(pointIndex) || claimedRings.has(ringIndex)) {
      continue;
    }
    claimedPoints.add(pointIndex);
    claimedRings.add(ringIndex);
    const ring = rings[ringIndex];
    if (ring.deviation <= MAX_RADIUS_DEVIATION && distance <= ring.radiusM) {
      pairs.set(ring.uid, points[pointIndex].uid);
    }
  }
  return pairs;
}

// La misma geometría desplazada, en grados. No muta la original.
export function translateGeometry(geometry, dLng, dLat) {
  const shift = (c) => [c[0] + dLng, c[1] + dLat, ...c.slice(2)];
  switch (geometry.type) {
    case "Point":
      return { ...geometry, coordinates: shift(geometry.coordinates) };
    case "LineString":
      return { ...geometry, coordinates: geometry.coordinates.map(shift) };
    case "Polygon":
      return {
        ...geometry,
        coordinates: geometry.coordinates.map((ring) => ring.map(shift)),
      };
    default:
      return geometry;
  }
}
