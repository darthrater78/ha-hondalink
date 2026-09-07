"""Minimal client for NHTSA's public VIN decode and recalls APIs.

HondaLink's private telematics API (api.py) has no recall endpoint -- it was
never observed in the app flow. Recall data instead comes from NHTSA, which
publishes it freely and does not require a HondaLink account: decode the VIN
to a make/model/year, then look up recalls for that vehicle.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from urllib.parse import quote

import aiohttp

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=15)

VIN_DECODE_URL = "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{vin}?format=json"
RECALLS_URL = "https://api.nhtsa.gov/recalls/recallsByVehicle"


class NHTSAError(Exception):
    pass


async def async_decode_vin(session: aiohttp.ClientSession, vin: str) -> dict[str, str]:
    """Resolve a VIN to the make/model/year NHTSA's recalls API expects."""
    url = VIN_DECODE_URL.format(vin=quote(vin, safe=""))
    data = await _get(session, url)
    results = data.get("Results") or []
    result = results[0] if results else {}
    make = result.get("Make")
    model = result.get("Model")
    year = result.get("ModelYear")
    if not make or not model or not year:
        raise NHTSAError(f"VIN decode did not return make/model/year for {vin}")
    return {"make": make, "model": model, "year": year}


async def async_get_recalls(
    session: aiohttp.ClientSession,
    *,
    make: str,
    model: str,
    year: str,
) -> list[dict[str, Any]]:
    """Return active NHTSA recalls for a make/model/year, most recent first."""
    data = await _get(session, RECALLS_URL, params={"make": make, "model": model, "modelYear": year})
    results = data.get("results")
    recalls = results if isinstance(results, list) else []
    return sorted(recalls, key=_recall_sort_key, reverse=True)


def _recall_sort_key(recall: dict[str, Any]) -> datetime:
    """NHTSA reports dates as MM/DD/YYYY, which does not sort correctly as text."""
    raw = recall.get("ReportReceivedDate")
    try:
        return datetime.strptime(str(raw), "%m/%d/%Y")
    except (TypeError, ValueError):
        return datetime.min


async def _get(
    session: aiohttp.ClientSession,
    url: str,
    *,
    params: dict[str, str] | None = None,
) -> dict[str, Any]:
    try:
        async with session.get(url, params=params, timeout=REQUEST_TIMEOUT) as response:
            text = await response.text()
            status = response.status
    except TimeoutError as err:
        raise NHTSAError(f"NHTSA request timed out: {url}") from err
    except aiohttp.ClientError as err:
        raise NHTSAError(f"NHTSA request failed: {err}") from err

    try:
        payload = json.loads(text) if text else {}
    except json.JSONDecodeError as err:
        excerpt = text[:200].replace("\n", " ")
        raise NHTSAError(f"Invalid JSON from NHTSA (HTTP {status}): {excerpt}") from err

    if status >= 400:
        raise NHTSAError(f"NHTSA request failed: HTTP {status} {payload}")
    return payload
