// Read-only API access for the geo map island (GEO-7).
// Business rules live on the server; this only fetches the canonical document.

export async function fetchCanonical(url) {
  const res = await fetch(url, {
    headers: { Accept: "application/json" },
    credentials: "same-origin",
  });
  if (!res.ok) {
    throw new Error(`content request failed: ${res.status}`);
  }
  return res.json();
}
