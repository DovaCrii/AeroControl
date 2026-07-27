// Leaflet map setup: base-layer switcher from the configured tile providers.
// Leaflet is loaded as a classic script before this module, so `L` is global.

export function createMap(el, tileProviders) {
  const map = L.map(el, { zoomControl: true });
  const bases = {};
  let first = null;
  for (const provider of tileProviders || []) {
    const layer = L.tileLayer(provider.url, {
      attribution: provider.attribution || "",
      maxZoom: provider.maxZoom || 19,
    });
    bases[provider.name] = layer;
    if (!first) {
      layer.addTo(map);
      first = layer;
    }
  }
  if (Object.keys(bases).length > 1) {
    L.control.layers(bases, {}, { position: "topright" }).addTo(map);
  }
  // A sane default view until features are loaded and fitted.
  map.setView([-33.45, -70.66], 4);
  return map;
}
