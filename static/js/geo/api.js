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

// Commit a new version (GEO-6 API). Returns {status, body}: the caller decides
// what each status means (201 created, 200 no_change, 409 conflict/plan_locked,
// 400 validation, 429 throttled). Never throws on a handled HTTP status.
export async function commit(url, csrfToken, payload) {
  const res = await fetch(url, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": csrfToken || "",
      Accept: "application/json",
    },
    body: JSON.stringify(payload),
  });
  let body = null;
  try {
    body = await res.json();
  } catch (err) {
    body = null;
  }
  return { status: res.status, body };
}
