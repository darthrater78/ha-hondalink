<p align="center">
  <img src="assets/logo.png" alt="HondaLink Home Assistant integration logo" width="180">
</p>

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/)
[![Version](https://img.shields.io/github/v/release/darthrater78/ha-hondalink)](https://github.com/darthrater78/ha-hondalink/releases)
[![License](https://img.shields.io/github/license/darthrater78/ha-hondalink)](LICENSE)
[![Maintenance](https://img.shields.io/maintenance/yes/2026.svg)](https://github.com/darthrater78/ha-hondalink)

# HondaLink for Home Assistant

Unofficial Home Assistant custom integration for HondaLink telematics vehicles.

This integration uses the HondaLink Android app API flow, observed while debugging the app, to discover vehicles, poll vehicle state, and expose supported remote commands in Home Assistant.

> This project is not affiliated with, endorsed by, or supported by Honda. HondaLink is a trademark of its respective owner.

> This is a fork of [daviddelahoz/ha-hondalink](https://github.com/daviddelahoz/ha-hondalink),
> which did the original HondaLink API research this integration is built on.

## Features

- Fuel level, range, odometer, oil life, 12V battery status, tire pressure, vehicle speed, and last update sensors
- Door, hood, trunk, window, lights, warning lamp, and remote engine binary sensors
- Lock and unlock entity for supported vehicles
- Buttons for engine start, engine stop, horn, lights, stop horn/lights, and refresh
- Device tracker from vehicle GPS data when returned by the HondaLink API
- Configurable lock and unlock command codes for vehicles or markets that use alternate CIG command names
- Units follow what the vehicle reports, so distance, pressure, and speed are not assumed

## Status

This is early custom-component work built from a validated HondaLink Android app
flow observed during app debugging. Honda can change these private endpoints at
any time.

Known platform coverage, by the `TelematicsPlatform` field the vehicle API returns:

| Platform | Example | Status |
|---|---|---|
| MY21 | 10th gen Accord | Confirmed working, including live data |
| MY23 | 2024 Accord Hybrid | Endpoints confirmed: authentication, vehicle discovery, and the dashboard schema all respond, with every sensor path this integration maps present. Live values not yet verified end to end. |
| BEV3 | Prologue | Not supported. These vehicles use HondaLink Connected by OnStar, a different backend entirely. |

Run `tools/hondalink_probe.py` to find out which platform your vehicle reports.

## Installation

### HACS

This repository is ready for HACS custom repository installation.

1. In Home Assistant, open HACS.
2. Go to Integrations.
3. Open Custom repositories.
4. Add this repository URL.
5. Choose category `Integration`.
6. Install `HondaLink`.
7. Restart Home Assistant.

### Manual

Copy the integration folder to Home Assistant:

```text
/config/custom_components/hondalink
```

Then restart Home Assistant.

## Setup

In Home Assistant, go to:

```text
Settings > Devices & services > Add integration > HondaLink
```

The config flow asks for:

- HondaLink email
- HondaLink password
- Remote PIN from the HondaLink app
- VIN, optional if the vehicle can be discovered automatically
- Name, optional display name

If auto-discovery returns no vehicles, enter the VIN manually.

## API Flow

The integration currently follows this sequence:

1. Register app client with HIDAS.
2. Generate a HIDAS bearer token.
3. Discover vehicles from `GET /REST/NGT/MyVehicle/1.0`.
4. Poll latest vehicle state from `POST /REST/NGT/CIG/dbd/latest/{VIN}`.
5. Send remote CIG commands through `POST /REST/NGT/CIG/{engine}/async/{command}`.
6. Poll command results from `GET /REST/NGT/CIG/{engine}/results/{request_id}`.

### Token Generation

The live HIDAS token endpoint expects these form fields:

```text
username=<email>
password=<password>
description=Android
client_reg_key=<client_reg_key>
```

Earlier app-debugging notes may mention `email` and `device_description`, but those fields are not the confirmed working request shape for the live endpoint.

## Options

After setup, open the integration options to change:

- Remote PIN
- Polling interval
- Lock command code
- Unlock command code
- Diagnostic attributes

The default lock command is `alk`; the default unlock command is `dulk`.

Diagnostic attributes are off by default. Turning them on adds the full dashboard
payload structure to the 12V battery sensor's attributes, which is useful when
mapping a new vehicle but writes hundreds of values to the recorder database on
every poll. Turn it back off once mapping is done.

## Troubleshooting

### Could not connect to HondaLink

Restart Home Assistant after updating the custom component, then try setup again. The config flow logs the HondaLink response in a redacted form, so check Home Assistant logs for:

```text
HondaLink connection failed during config flow
```

### Invalid credentials or remote PIN

Confirm that the same email, password, and remote PIN work in the HondaLink mobile app. Some HondaLink accounts may require accepting updated terms or completing account verification in the app before API login succeeds.

### No vehicle discovered

Enter the VIN manually in the setup form. The integration will still try to fetch
vehicle details by VIN after login.

### Sensors exist but every value is unknown

The dashboard endpoint returns its full schema with empty values when the vehicle
has nothing cached to report. Common causes, in order of likelihood:

1. Data or connected services are switched off in the vehicle itself.
2. The vehicle is not enrolled in connected services. Check for `"Enrollment": "N"`
   in the probe's step 3 output.
3. Nothing has asked the vehicle to report yet. Press the refresh button, or run
   the probe with `--refresh`.

### Diagnosing connection problems

`tools/hondalink_probe.py` runs the same four-step flow the integration uses and
stops at the first failure, so the step that breaks identifies the layer at fault.
It needs no Home Assistant install and no third-party packages.

```bash
python3 tools/hondalink_probe.py
python3 tools/hondalink_probe.py --refresh   # also ask the vehicle to report now
```

Credentials are read interactively or from `HONDALINK_EMAIL` and
`HONDALINK_PASSWORD`, never from the command line, and are not written to disk.
Tokens are redacted in its output, but the schema dump can contain your VIN and
GPS coordinates, so scrub it before sharing.

## Security

- This integration stores your HondaLink email, password, and remote PIN in the Home Assistant config entry so it can re-authenticate after token expiry.
- The Honda app `CLIENT_ID` and `CLIENT_SECRET` values are app-level credentials observed from the HondaLink mobile app flow, not user-specific credentials. Honda ships and uses them as part of the mobile app authentication flow, which this integration mirrors.
- Honda may rotate or revoke those app-level credentials at any time. If that happens, authentication can stop working for all users until the integration is updated.
- Do not share logs or diagnostics that include tokens, remote PIN, VIN, or GPS coordinates.
- Remote commands can physically affect your vehicle. Use this only with your own HondaLink account and vehicle.

## Support

If this integration is useful to you, consider supporting
[daviddelahoz](https://github.com/daviddelahoz), who reverse-engineered the original API flow:

<a href="https://www.buymeacoffee.com/daviddelahoz" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me a Coffee" style="height: 60px !important;width: 217px !important;" ></a>

## Version History

### 0.1.5 - 2026-09-07

- Added a reauthentication flow. Credential failures previously surfaced as
  ordinary update errors and retried on every poll, which risks account lockout;
  Home Assistant now prompts for the password instead.
- Diagnostic attributes on the 12V battery sensor are now off by default and
  controlled by an option. They wrote several hundred values to the recorder
  database on every poll.
- Sensor units now follow the unit the vehicle reports, falling back to the
  previous defaults. Odometer, range, speed, and tire pressures were hardcoded
  and would have been silently wrong on a vehicle reporting metric units.
- Fuel level is no longer reported as a battery device class.
- Fixed several sensors reporting confident wrong states for a vehicle that has
  not reported yet. Honda fills unreported fields with the string `unknown`,
  which was being read as a real value: doors and windows showed as open, lights
  as on, the door lock as unlocked, and the warning lamp as all-clear. These now
  report unknown until the vehicle actually reports.
- Concurrent requests arriving on an expired token now produce a single login.
- Response bodies that are not valid JSON are truncated in error messages, since
  redaction cannot inspect them.
- Minimum Home Assistant version is now 2024.12.0.

### 0.1.4 - 2026-09-07

- Fixed options flow failing to open on Home Assistant 2024.11 and newer.
  `OptionsFlow.config_entry` became a read-only property provided by the base
  class, so the handler no longer accepts or assigns it.
- Raised the minimum supported Home Assistant version to 2024.11.0, which is
  where that property was introduced.
- Repointed repository metadata (codeowners, documentation, issue tracker,
  README badges) at this fork.
- Added `tools/hondalink_probe.py`, a dependency-free diagnostic that walks the
  HIDAS authentication and CIG dashboard flow and reports which layer fails for
  a given vehicle. Confirmed the API serves MY23-platform vehicles
  (2024 Accord Hybrid) with all mapped sensor paths present.

### 0.1.3

- Documented the HondaLink app-level credentials and their rotation risk.

## Known Limitations

- See the Status section for per-platform coverage. MY23 vehicles reach the API
  and match the expected schema, but end-to-end live data is unverified.
- EV fields are exposed only when the Honda dashboard payload returns actual values.
- Lock and unlock command behavior may vary by vehicle, subscription, market, or Honda API changes.
- HondaLink is a private cloud API; reliability depends on Honda's service and endpoint compatibility.

## Local Development

Useful validation commands:

```bash
python3 -m py_compile *.py tools/*.py
```

HACS and hassfest workflow files are included under `.github/workflows/`.
