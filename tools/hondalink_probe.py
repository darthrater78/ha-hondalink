#!/usr/bin/env python3
"""Standalone HondaLink connectivity probe.

Runs the same four-step flow the integration uses, stopping at the first
failure and reporting which layer broke. Requires no Home Assistant install
and no third-party packages -- stdlib only, so it runs as-is under Termux.

Credentials are read interactively or from HONDALINK_EMAIL / HONDALINK_PASSWORD
environment variables. They are never passed on the command line (argv is
visible to other processes via ps) and never written to disk.

    python3 tools/hondalink_probe.py
    python3 tools/hondalink_probe.py --vin 1HGCV3F55PA000000
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Any

# Mirrors const.py so the probe tests exactly what the integration would send.
CLIENT_ID = "HondaLinkAndroidApp0074"
CLIENT_SECRET = "rETFrZcLyUycsSblksCP"
APP_USER_AGENT = "HondaLink/5.0.51 (Android)"
DEVICE_DESCRIPTION = "Android"
IDENTITY_BASE = "https://identity.services.honda.com"
API_BASE = "https://wsc.hondaweb.com"
HONDALINK_BUSINESS_ID = "HONDALINK CONNECT"
HONDALINK_SYSTEM_ID = "com.honda.hondalink.cv_android"
HONDA_HEADER_VERSION = "1.0"

TIMEOUT = 30
SENSITIVE_KEYS = {"access_token", "refresh_token", "password", "pin", "client_reg_key"}


class ProbeError(Exception):
    """A step failed in a way that stops the probe."""


def redact(value: Any) -> Any:
    """Recursively mask credential-bearing fields so output is safe to paste."""
    if isinstance(value, dict):
        return {
            key: "**REDACTED**" if str(key).lower() in SENSITIVE_KEYS else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def request(
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    form: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any], str]:
    """Return (status, parsed_json, raw_text). Never raises on HTTP status."""
    data: bytes | None = None
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
    elif body is not None:
        data = json.dumps(body).encode()

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            status, text = response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as err:
        status, text = err.code, err.read().decode("utf-8", "replace")
    except urllib.error.URLError as err:
        raise ProbeError(f"network error reaching {url}: {err.reason}") from err

    try:
        payload = json.loads(text) if text.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    return status, payload, text


def leaf_paths(value: Any, path: str = "", out: list[str] | None = None) -> list[str]:
    """Flatten a payload into dotted paths so the real schema is visible."""
    if out is None:
        out = []
    if len(out) >= 400:
        return out
    if isinstance(value, dict):
        if not value and path:
            out.append(path)
        for key, item in value.items():
            leaf_paths(item, f"{path}.{key}" if path else str(key), out)
    elif isinstance(value, list):
        if not value and path:
            out.append(path)
        for index, item in enumerate(value[:20]):
            leaf_paths(item, f"{path}.{index}" if path else str(index), out)
    elif path:
        out.append(f"{path} = {value!r}"[:160])
    return out


def api_headers(token: str, reg_key: str, ctx: dict[str, str]) -> dict[str, str]:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": APP_USER_AGENT,
        "hondaHeaderType.version": HONDA_HEADER_VERSION,
        "hondaHeaderType.messageId": str(uuid.uuid4()),
        "hondaHeaderType.siteId": reg_key,
        "hondaHeaderType.businessId": HONDALINK_BUSINESS_ID,
        "hondaHeaderType.systemId": HONDALINK_SYSTEM_ID,
        "hondaHeaderType.collectedTimestamp": stamp,
        "hondaHeaderType.collectedTimeStamp": stamp,
        "hondaHeaderType.clientType": "Mobile",
        "hondaHeaderType.deviceID": ctx["device_id"],
        "hondaHeaderType.sessionID": ctx["session_id"],
        "hondaHeaderType.country_code": ctx["country"],
        "hondaHeaderType.language_code": ctx["language"],
    }
    if ctx.get("hidas_ident"):
        headers["hondaHeaderType.userId"] = ctx["hidas_ident"]
        headers["hondaHeaderType.hidasId"] = ctx["hidas_ident"]
    return headers


def step(number: int, title: str) -> None:
    print(f"\n{'=' * 62}\nSTEP {number}: {title}\n{'=' * 62}")


def verdict(text: str) -> None:
    print(f"\n>>> VERDICT: {text}")


def step_register() -> str:
    step(1, "Register app client with HIDAS")
    status, payload, text = request(
        "POST",
        f"{IDENTITY_BASE}/hidas/rs/client/register",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": APP_USER_AGENT,
        },
        form={"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET},
    )
    print(f"HTTP {status}")
    print(json.dumps(redact(payload), indent=2)[:1200] if payload else text[:600])

    reg_key = (payload.get("clientregistrationkey") or {}).get("client_reg_key")
    if not reg_key:
        verdict(
            "The app-level client credentials in const.py are no longer accepted.\n"
            "    Honda rotated CLIENT_ID/CLIENT_SECRET, or this endpoint is retired.\n"
            "    Nothing downstream can work until they are re-extracted from a\n"
            "    current HondaLink app build. This is NOT specific to your car."
        )
        raise ProbeError("client registration failed")
    print("\nOK - client registration key obtained.")
    return reg_key


def step_login(email: str, password: str, reg_key: str) -> tuple[str, dict[str, str]]:
    step(2, "Generate HIDAS bearer token (your account credentials)")
    status, payload, text = request(
        "POST",
        f"{IDENTITY_BASE}/hidas/rs/token/generate",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": APP_USER_AGENT,
        },
        form={
            "username": email,
            "password": password,
            "description": DEVICE_DESCRIPTION,
            "client_reg_key": reg_key,
        },
    )
    print(f"HTTP {status}")
    print(json.dumps(redact(payload), indent=2)[:1500] if payload else text[:600])

    token = (payload.get("token") or {}).get("access_token")
    if not token:
        verdict(
            "Your HondaLink account did not authenticate against the legacy HIDAS\n"
            "    identity service. Either the credentials are wrong, the account needs\n"
            "    terms accepted in the app, or 2023+ accounts have moved to a different\n"
            "    identity provider. If the same login works in the HondaLink app, the\n"
            "    latter is likely -- the entire auth layer would need replacing."
        )
        raise ProbeError("login failed")

    user = payload.get("user") or {}
    print("\nOK - authenticated. The legacy identity service still accepts your account.")
    return token, {
        "country": user.get("country_code") or "US",
        "language": user.get("language_code") or "en",
        "hidas_ident": user.get("hidas_ident") or "",
        "device_id": str(uuid.uuid4()),
        "session_id": str(uuid.uuid4()),
    }


def step_vehicles(token: str, reg_key: str, ctx: dict[str, str]) -> list[dict[str, Any]]:
    step(3, "Discover vehicles (THE decisive test for your model year)")
    status, payload, text = request(
        "GET",
        f"{API_BASE}/REST/NGT/MyVehicle/1.0",
        headers=api_headers(token, reg_key, ctx),
    )
    print(f"HTTP {status}")
    print(json.dumps(redact(payload), indent=2)[:2500] if payload else text[:800])

    vehicles = payload.get("vehicleInfo")
    vehicles = vehicles if isinstance(vehicles, list) else []
    if not vehicles:
        verdict(
            "Auth works, but this vehicle service returns no cars for your account.\n"
            "    This is the signature of a model year on a newer telematics backend:\n"
            "    the HondaLink SSO is shared, the vehicle/data services are not.\n"
            "    The auth layer of this integration is reusable; api.py's data layer\n"
            "    would need to be rewritten against whatever the 2023+ app calls.\n"
            "    (Rule out the mundane cause first: confirm the car is actually linked\n"
            "    to this account and has an ACTIVE HondaLink Remote subscription.)"
        )
        raise ProbeError("no vehicles returned")

    print(f"\nOK - {len(vehicles)} vehicle(s) found. This is the strong result.")
    for vehicle in vehicles:
        vin = str(vehicle.get("VIN", ""))
        masked = f"{vin[:3]}...{vin[-6:]}" if len(vin) > 9 else vin
        print(
            f"  - {vehicle.get('ModelYear', '?')} "
            f"{vehicle.get('ModelGroupNameFriendly') or vehicle.get('ModelCode', '?')} "
            f"[{masked}]"
        )
    return vehicles


def step_dashboard(vin: str, token: str, reg_key: str, ctx: dict[str, str]) -> None:
    step(4, "Fetch latest dashboard payload (the sensor data)")
    status, payload, text = request(
        "POST",
        f"{API_BASE}/REST/NGT/CIG/dbd/latest/{vin}",
        headers=api_headers(token, reg_key, ctx),
        body={"fromDate": "", "toDate": ""},
    )
    print(f"HTTP {status}  status={payload.get('status')!r}")

    body = payload.get("responseBody")
    if not isinstance(body, dict) or not body:
        print((json.dumps(redact(payload), indent=2) if payload else text)[:1500])
        verdict(
            "Vehicle is visible but returns no dashboard data. Often means the\n"
            "    Remote subscription is inactive, or the car reports through a\n"
            "    different endpoint. Only the data mapping would need work."
        )
        return

    paths = leaf_paths(body)
    print(f"\nOK - dashboard returned {len(paths)} data points.")
    print("\n--- FULL SCHEMA (this is your entity map) ---")
    for line in paths:
        print(f"  {line}")

    expected = {
        "fuel level": "fuelLevel.currentLevel.value",
        "range": "fuelLevel.driveRange.value",
        "odometer": "odometer.value",
        "oil life": "oilLife.value",
        "tire pressure": "tireStatus.frontLeft.pressureData.value",
        "doors": "doorStatus.firstRowDriver.lockState",
        "GPS": "gpsData.coordinate.latitude",
    }
    print("\n--- WHAT THIS INTEGRATION'S SENSORS EXPECT ---")
    joined = "\n".join(paths)
    hits = 0
    for label, path in expected.items():
        found = path in joined
        hits += found
        print(f"  [{'OK' if found else '  '}] {label:<16} {path}")

    verdict(
        f"{hits}/{len(expected)} of the integration's mapped paths are present.\n"
        "    High score -> it should largely work as-is.\n"
        "    Low score with data above -> the API works, only sensor.py's paths\n"
        "    need remapping to the schema printed above. That is a small change."
    )
    print("\nNOTE: the schema above may include your VIN and GPS coordinates.")
    print("      Scrub it before pasting anywhere public.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe HondaLink API reachability.")
    parser.add_argument("--vin", help="VIN to query; defaults to the first discovered")
    args = parser.parse_args()

    print("HondaLink connectivity probe")
    print("Credentials are used for these requests only. Nothing is saved to disk.")

    email = os.environ.get("HONDALINK_EMAIL") or input("\nHondaLink email: ").strip()
    password = os.environ.get("HONDALINK_PASSWORD") or getpass.getpass("HondaLink password: ")
    if not email or not password:
        print("Email and password are required.", file=sys.stderr)
        return 2

    try:
        reg_key = step_register()
        token, ctx = step_login(email, password, reg_key)
        del password
        vehicles = step_vehicles(token, reg_key, ctx)

        vin = (args.vin or str(vehicles[0].get("VIN", ""))).strip().upper()
        if not vin:
            print("\nNo VIN available to query.", file=sys.stderr)
            return 1
        step_dashboard(vin, token, reg_key, ctx)
    except ProbeError as err:
        print(f"\nProbe stopped: {err}", file=sys.stderr)
        return 1

    print("\nProbe complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
