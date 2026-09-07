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

- Fuel level, range, odometer, oil life, 12V battery status, tire pressure, cabin temperature, vehicle speed, and last update sensors
- Door, hood, trunk, window, lights, warning lamp, and remote engine binary sensors
- Lock and unlock entity for supported vehicles
- Buttons for engine start, engine stop, horn, lights, stop horn/lights, and refresh
- Device tracker from vehicle GPS data when returned by the HondaLink API
- Active recall binary sensor, sourced from NHTSA's public recalls database and carrying full recall details (campaign number, component, summary, consequence, remedy, report date) as attributes
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
| MY23 | 2024 Accord Hybrid | Confirmed working with live data. Odometer, fuel level, range, oil life, cabin temperature, GPS, speed, doors, locks and lights all report. Tire pressures are not reported by this vehicle. |
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

Steps 5 and 6 are separate: a command call returns as soon as the vehicle
acknowledges the request, and the result is polled in the background.

### Token Generation

The live HIDAS token endpoint expects these form fields:

```text
username=<email>
password=<password>
description=Android
client_reg_key=<client_reg_key>
```

Earlier app-debugging notes may mention `email` and `device_description`, but those fields are not the confirmed working request shape for the live endpoint.

## Recall Alerts

The `binary_sensor.*_active_recall` entity turns on when NHTSA lists an open
recall for the vehicle. This is sourced entirely from NHTSA's free, public
[recalls API](https://api.nhtsa.gov/recalls/recallsByVehicle) -- it does not
use the HondaLink API or require a HondaLink login, so it keeps working even
if HondaLink authentication is down.

The integration decodes the VIN once through NHTSA's VIN decode API to get
the make, model, and model year, then polls the recalls API for that
vehicle every 12 hours. Each recall's campaign number, component, summary,
consequence, remedy, and report date are available as attributes on the
entity.

NHTSA's recalls API is keyed by make/model/year rather than VIN, so a listed
recall can apply to a range of build dates or equipment configurations, not
necessarily this exact vehicle. Check the campaign number against your VIN
at [nhtsa.gov/recalls](https://www.nhtsa.gov/recalls) or in the HondaLink app
before acting on it.

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

## Example Dashboard

A ready-to-use [Mushroom](https://github.com/piitaya/lovelace-mushroom) view is
included at [`dashboards/hondalink-mushroom.yaml`](dashboards/hondalink-mushroom.yaml).
It shows fuel, range, odometer, oil life, 12V battery status, and cabin
temperature at a glance; door/window/light/warning status; tire pressures;
lock/unlock control; the remote action buttons; and a map from the GPS device
tracker.

It needs the Mushroom custom card (install via HACS > Frontend > Mushroom) and
otherwise only uses Home Assistant's built-in grid and map cards. See the
comments at the top of the file for how to point it at your vehicle's
entities and add it to a dashboard.

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

### 0.1.8 - 2026-09-07

- Added an active recall binary sensor, sourced from NHTSA's public recalls
  database by VIN (decoded to make/model/year, since NHTSA's recalls API is
  not VIN-keyed). Polls independently of the HondaLink API every 12 hours, so
  it keeps reporting even during a HondaLink outage or auth failure. Recall
  campaign number, component, summary, consequence, remedy, and report date
  are exposed as entity attributes.

### 0.1.7 - 2026-09-07

- Remote commands no longer hold a service call open while the vehicle carries
  them out. Pressing lock or engine start could block for over a minute; the
  command now returns once the vehicle acknowledges it, and completion is awaited
  in the background before the coordinator refreshes. Rejections such as a bad
  PIN still surface to the user immediately.
- Added an explicit 30 second HTTP timeout. Requests previously inherited
  aiohttp's five minute default, so one stalled request could hold up a poll.
- Network and timeout errors are now wrapped as HondaLink errors rather than
  escaping as raw aiohttp exceptions.
- The update coordinator is now constructed with its config entry, which Home
  Assistant expects from 2024.12 onward.

### 0.1.6 - 2026-09-07

- Recognise `mile/h` as a speed unit. Honda reports vehicle speed this way, which
  was not in the unit table and fell back to the default.
- The remote engine binary sensor now understands the states vehicles actually
  report. It compared against `ON`, but a MY23 vehicle reports `IG RUN`, so a
  running engine read as not running. Unrecognised states now report unknown
  rather than being asserted as off.
- Corrected the connectivity probe's refresh verdict. It treated an unchanged
  populated-value count as a failure and advised enrolling the vehicle, when an
  unchanged count on a vehicle that already reports simply means the data was
  current.
- Added a cabin temperature sensor, which vehicles report alongside its unit.
- Confirmed all sensor mappings against live data from a 2024 Accord Hybrid.

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

- See the Status section for per-platform coverage.
- Some vehicles never report tire pressure. A 2024 Accord Hybrid returns the tire
  nodes with a unit but no value, so those sensors stay unknown.
- Hybrid vehicles that are not plug-in return an `evStatus` block, but every field
  in it stays unknown. It is a shared template, not a sign of missing support.
- The `Enrollment` field in the vehicle record can read `N` on a vehicle that
  nonetheless reports fine. It is not a reliable indicator of connected services.
- EV fields are exposed only when the Honda dashboard payload returns actual values.
- Lock and unlock command behavior may vary by vehicle, subscription, market, or Honda API changes.
- HondaLink is a private cloud API; reliability depends on Honda's service and endpoint compatibility.

## Local Development

Useful validation commands:

```bash
python3 -m py_compile *.py tools/*.py
```

HACS and hassfest workflow files are included under `.github/workflows/`.
