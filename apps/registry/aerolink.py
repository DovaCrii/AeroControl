"""X.4b: reading AeroLink's battery inventory (ADR-0002, phase 2).

ADR-0002 makes AeroLink the **master of battery inventory** -- DJI reports
cycles and health natively, and a hand-kept count drifts from reality
immediately. `registry.Battery` is the mirror that keeps the ISO 7.1.3 evidence
where the auditor already looks. This module is how the mirror is filled.

**The contract this expects, proposed by AeroControl** (the consumer), for
AeroLink to implement. It is written down here and in ADR-0002 so both sides
agree on a shape before either builds against a guess:

    GET {AEROLINK_API_URL}/devices/?kind=battery
    Authorization: Token <token>

`AEROLINK_API_URL` **includes the version prefix** -- only "/devices/?kind=..."
is appended here. So it is set to e.g. `http://127.0.0.1:8081/api/v1`.

    {"results": [
      {"serial_number": "...",       # required, the join key (ADR-0002 §2)
       "model": "...",               # optional
       "status": "active|retired",   # optional, defaults to active
       "cycle_count": 120,           # optional
       "health_percent": 93,         # optional, 0-100
       "firmware_version": "...",    # optional
       "aircraft_serial": "..."}     # optional, "last seen on"
    ]}

A bare list instead of `{"results": [...]}` is also accepted: AeroLink's API is
not written yet, and refusing the simpler shape would be inventing a
requirement on their side for no benefit here.

The transport follows `apps.core.weather` -- the project's only other outgoing
call -- for the same reasons: the call is made server-side (the CSP stays a
bare `default-src 'self'`), the URL scheme is checked rather than assumed, the
read is bounded, the timeout is short, and every failure path returns nothing
instead of raising. A telemetry gateway being down must never break the
operational app that shares its VM.
"""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

logger = logging.getLogger("aerocontrol.aerolink")

# Bounded read: a gateway returning an unexpectedly huge body must not become a
# memory problem. 4 MB is far above a realistic battery inventory (~16 aircraft
# worth) and far below anything that would hurt.
MAX_RESPONSE_BYTES = 4 * 1024 * 1024


class AeroLinkUnavailable(Exception):
    """The gateway could not be reached or did not answer usefully.

    Raised rather than returned so a scheduled sync fails loudly in its job
    record instead of silently reporting "0 batteries" -- which would read
    exactly like a gateway that answered with an empty inventory.
    """


def fetch_batteries():
    """The battery inventory as a list of dicts, straight from the gateway."""
    base = getattr(settings, "AEROLINK_API_URL", "") or ""
    if not base:
        raise AeroLinkUnavailable("AEROLINK_API_URL is not configured.")
    if urllib.parse.urlparse(base).scheme not in ("http", "https"):
        # urlopen would happily accept file:// or a custom scheme, turning a
        # misconfigured setting into a local-file read. Enforced, not assumed.
        raise AeroLinkUnavailable("AEROLINK_API_URL must be http or https.")

    url = f"{base.rstrip('/')}/devices/?kind=battery"
    request = urllib.request.Request(url, headers=_headers())
    timeout = getattr(settings, "AEROLINK_TIMEOUT_SECONDS", 10)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310
            if response.status != 200:
                raise AeroLinkUnavailable(f"HTTP {response.status}")
            body = response.read(MAX_RESPONSE_BYTES)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.warning("aerolink_unreachable", extra={"reason": type(exc).__name__})
        raise AeroLinkUnavailable(str(exc)) from exc

    return parse_batteries(body)


def _headers():
    headers = {"Accept": "application/json"}
    token = getattr(settings, "AEROLINK_API_TOKEN", "") or ""
    if token:
        headers["Authorization"] = f"Token {token}"
    return headers


def parse_batteries(body):
    """Pull the battery list out of a response body.

    Separate from the fetch so the same parsing is exercised by
    `sync_batteries --from-file`, which is how this can be tested end to end
    before AeroLink exposes anything at all.
    """
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeDecodeError) as exc:
        raise AeroLinkUnavailable("Malformed JSON.") from exc

    if isinstance(payload, dict):
        payload = payload.get("results")
    if not isinstance(payload, list):
        raise AeroLinkUnavailable("Expected a list of devices.")
    return [item for item in payload if isinstance(item, dict)]
