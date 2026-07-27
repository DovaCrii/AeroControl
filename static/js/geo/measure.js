// Self-contained geodesic measurements (no Leaflet plugin): haversine length
// for lines, spherical shoelace for polygon area. Inputs are [lon, lat] pairs.

const EARTH_RADIUS_M = 6371008.8; // IUGG mean radius
const rad = (deg) => (deg * Math.PI) / 180;

export function haversine(a, b) {
  const dLat = rad(b[1] - a[1]);
  const dLon = rad(b[0] - a[0]);
  const lat1 = rad(a[1]);
  const lat2 = rad(b[1]);
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(h)));
}

export function lineLength(coords) {
  let total = 0;
  for (let i = 1; i < coords.length; i += 1) {
    total += haversine(coords[i - 1], coords[i]);
  }
  return total;
}

// Spherical polygon area (the standard geodesic approximation, same one
// Leaflet.GeometryUtil and Google Maps use). coords is one closed ring.
export function ringArea(coords) {
  if (!coords || coords.length < 4) {
    return 0;
  }
  let sum = 0;
  for (let i = 0; i < coords.length - 1; i += 1) {
    const [lon1, lat1] = coords[i];
    const [lon2, lat2] = coords[i + 1];
    sum += rad(lon2 - lon1) * (2 + Math.sin(rad(lat1)) + Math.sin(rad(lat2)));
  }
  return Math.abs((sum * EARTH_RADIUS_M * EARTH_RADIUS_M) / 2);
}

// Returns {kind: "length"|"area", meters|squareMeters} or null when the
// geometry is not measurable (points, empty collections).
export function measureGeometry(geometry) {
  if (!geometry) {
    return null;
  }
  if (geometry.type === "LineString") {
    return { kind: "length", meters: lineLength(geometry.coordinates || []) };
  }
  if (geometry.type === "Polygon") {
    const outer = (geometry.coordinates || [])[0] || [];
    return { kind: "area", squareMeters: ringArea(outer) };
  }
  return null;
}

export function formatLength(meters) {
  return meters >= 1000
    ? `${(meters / 1000).toFixed(2)} km`
    : `${meters.toFixed(0)} m`;
}

export function formatArea(squareMeters) {
  return squareMeters >= 1e6
    ? `${(squareMeters / 1e6).toFixed(2)} km²`
    : `${squareMeters.toFixed(0)} m²`;
}
