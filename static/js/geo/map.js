// Leaflet map setup: base-layer switcher from the configured tile providers.
// Leaflet is loaded as a classic script before this module, so `L` is global.

export function createMap(el, tileProviders) {
  const map = L.map(el, { zoomControl: true });
  const bases = {};
  const providers = tileProviders || [];
  // LV-239: the layer drawn on open is the one flagged `default` in
  // GEO_TILE_PROVIDERS -- satellite, by the user's request: a plan's area is
  // terrain, and on the street map the circle floats over nothing. It used to be
  // whichever came first in the settings list, so reordering that literal for
  // tidiness silently changed what the operator sees. Falling back to the first
  // one keeps a map on screen if nobody flags any.
  const initial = providers.find((provider) => provider.default) || providers[0];
  for (const provider of providers) {
    const layer = L.tileLayer(provider.url, {
      attribution: provider.attribution || "",
      maxZoom: provider.maxZoom || 19,
    });
    bases[provider.name] = layer;
    if (provider === initial) {
      layer.addTo(map);
    }
  }
  if (Object.keys(bases).length > 1) {
    L.control.layers(bases, {}, { position: "topright" }).addTo(map);
  }
  // A sane default view until features are loaded and fitted.
  map.setView([-33.45, -70.66], 4);
  return map;
}
