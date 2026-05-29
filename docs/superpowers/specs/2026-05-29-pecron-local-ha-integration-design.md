# Pecron Local — Home Assistant Integration Design

**Date:** 2026-05-29
**Status:** Approved

## Overview

A HACS-installable Home Assistant custom integration for Pecron portable power stations that communicates exclusively over the local network (WiFi TCP) or Bluetooth Low Energy. No cloud dependency after initial setup.

Protocol implementation and reverse-engineering credit: [attractify-logan/pecron-monitor](https://github.com/attractify-logan/pecron-monitor). The TTLV packet format, AES-CBC handshake, TSL field mappings, and transport logic are ported from that project.

---

## Repository

New standalone repo: `ha-pecron-local`
Structure: HACS-compatible custom component under `custom_components/pecron_local/`

---

## Architecture

```
custom_components/pecron_local/
├── __init__.py          # Integration setup, config entry load/unload
├── manifest.json        # Integration metadata, bleak dependency, bluetooth entry
├── config_flow.py       # UI: discovery + auth (credentials or manual key)
├── coordinator.py       # DataUpdateCoordinator — poll loop, transport failover
├── transport/
│   ├── __init__.py
│   ├── base.py          # Abstract transport interface
│   ├── tcp.py           # WiFi TCP transport (port 6607, AES-CBC)
│   └── ble.py           # BLE transport (bleak, AES-CBC)
├── protocol.py          # TTLV packet encode/decode
├── const.py             # Domain, sensor field mappings, TSL IDs, enum tables
├── entity.py            # Base PecronEntity(CoordinatorEntity)
├── sensor.py            # All read-only sensors
├── switch.py            # AC output, DC output, UPS mode
├── select.py            # AC charging power, brightness, standby timeout, etc.
└── diagnostics.py       # HA diagnostics support (redacts auth key)
```

### Key dependency

`bleak` — already bundled with Home Assistant; no extra install required.

---

## Config Flow & Discovery

Two parallel discovery paths surface devices before the user configures anything:

1. **LAN scan** — probes the local subnet on port 6607 at integration add time. Found devices are listed by IP and device name for the user to select.
2. **BLE scan** — the integration registers a `bluetooth` entry in `manifest.json` matching Pecron's BLE advertisement name prefix. Devices appear automatically in the HA discovery inbox when in range.

The user may also click **Add manually** and enter an IP address directly.

### Authentication (after device is selected)

Two options presented as a choice in the config flow:

| Option | Flow |
|---|---|
| **Sign in with Pecron account** | User enters email, password, region (NA / EU / CN). Integration makes a single cloud call to fetch the per-device auth key, stores it in the config entry, never contacts the cloud again. |
| **Enter auth key manually** | User pastes the auth key directly (obtainable via `pecron-monitor --setup` or the ha-pecron cloud integration). Zero cloud calls. |

### Config entry fields

| Field | Type | Description |
|---|---|---|
| `host` | `str \| None` | Device LAN IP (None if BLE-only) |
| `mac` | `str \| None` | BLE MAC address (None if TCP-only) |
| `auth_key` | `str` | AES key (hex, fetched or entered) |
| `device_name` | `str` | Human-readable name |
| `preferred_transport` | `str` | `"tcp"` or `"ble"` |
| `poll_interval` | `int` | Seconds between polls (default 30) |

---

## Coordinator & Transport Failover

`PecronCoordinator` extends `DataUpdateCoordinator[dict]`.

### Poll cycle

```
try:
    data = await tcp_transport.read()
except TransportError:
    try:
        data = await ble_transport.read()
    except TransportError:
        raise UpdateFailed
return data  # nested dict matching SENSOR_FIELDS structure
```

### TCP transport

- Socket kept open between polls; re-established on any error.
- Handshake on connect: random nonce exchange → SHA-256 login → AES-CBC session key derived.
- Read: send TTLV cmd `0x0011`, receive and decrypt response, parse TTLV fields into nested dict.

### BLE transport

- Connects fresh each poll (persistent BLE connections are fragile on embedded firmware).
- Same handshake and TTLV framing as TCP, over GATT write/notify characteristics.
- Uses `bleak` (already in HA's dependency set).

### Write path

Switch toggles and select changes send a TTLV write packet (cmd `0x0013`) directly over whichever transport is currently active, then trigger an immediate coordinator refresh. No optimistic state — entities reflect only confirmed device state.

---

## Entities

All entities extend `PecronEntity(CoordinatorEntity)`. Entities whose field is absent from coordinator data are silently skipped — no model-specific config required.

### Sensors (read-only)

| Entity | Unit | Source field |
|---|---|---|
| Battery | % | `battery_percent` |
| Voltage | V | `voltage` |
| Temperature | °C | `temperature` (main); E3800: `battery_temp`, `charging_plate_temp`, `inverter_temp` |
| Charge status | — | `charge_status` (enum) |
| Device status | — | `device_status_hm` (enum: Shut Down / Charging / AC Discharge / DC Discharge / Standby / Conservation) |
| Total input power | W | `total_input_power` |
| Total output power | W | `total_output_power` |
| AC input power | W | `ac_input_power` |
| AC output power | W | `ac_output_power` |
| DC input power | W | `dc_input_power` |
| DC output power | W | `dc_output_power` |
| Solar port 1 voltage | V | `dc5521_input_voltage` |
| Solar port 1 current | A | `dc5521_input_current` |
| Solar port 1 power | W | `dc5521_input_power` |
| Solar port 2 voltage | V | `gx16mf1_input_voltage` |
| Solar port 2 current | A | `gx16mf1_input_current` |
| Solar port 2 power | W | `gx16mf1_input_power` |
| Solar port 3 voltage | V | `gx16mf2_input_voltage` |
| Solar port 3 current | A | `gx16mf2_input_current` |
| Solar port 3 power | W | `gx16mf2_input_power` |
| AC output voltage | V | `ac_output_voltage` |
| AC output frequency | Hz | `ac_output_hz` |
| AC output power factor | — | `ac_output_pf` |
| Time to full | min | `remain_charging_time` |
| Time to empty | min | `remain_time` |
| AC charging power | % | `ac_charging_power` (read side) |

### Switches

| Entity | TSL code |
|---|---|
| AC output | `ac_switch_hm` (id 40) |
| DC output | `dc_switch_hm` (id 38) |
| UPS mode | `ups_status_hm` (id 27) |

### Selects

| Entity | TSL code | Options |
|---|---|---|
| AC charging power | `ac_charging_power_ios` (id 50) | 0%, 10%, …, 100% |
| Screen brightness | `machine_screen_light_as` (id 45) | 5%, 20%, 50%, 80%, 100% |
| Standby timeout | `device_standy_times_as` (id 51) | 24h / 48h / 7d / 14d / Always On |
| AC output voltage | `ac_output_voltage_io` (id 32) | 100V / 110V / 120V / 220V / 230V / 240V |
| AC output frequency | `ac_output_frequency_io` (id 33) | 50Hz / 60Hz |
| Auto-off time | `noastime_io` (id 34) | Off / 1h / 2h / 3h / 4h |

Boolean settings exposed as switches (not selects): touch lock (`device_touch_locking_as`, id 42), eco/quiet mode (`eco_quite_mode_as`, id 44), auto screen light (`auto_light_flag_as`, id 43).

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| TCP + BLE both fail | `UpdateFailed` raised → all entities marked `unavailable`, retry next poll |
| Bad auth key | `ConfigEntryAuthFailed` → HA triggers re-auth flow |
| Write command fails | Warning logged, immediate poll to resync state |
| Device offline mid-session | TCP socket error → BLE attempt → `unavailable` if both fail |

---

## Diagnostics

Implements HA's `async_get_config_entry_diagnostics`. Returns coordinator data snapshot with `auth_key` replaced by `**REDACTED**`. Allows users to share diagnostic dumps safely for bug reports.

---

## Testing

- **Unit** — TTLV encode/decode (ported from `pecron-monitor/tests/unit/test_protocol.py`), sensor field mapping, enum decode tables
- **Integration** — coordinator tests with mock transport (both TCP success and TCP-fail-BLE-success paths), config flow tests with HA test helpers
- **No hardware tests** in this repo (hardware tests remain in pecron-monitor)

---

## Out of Scope

- Cloud transport (no MQTT, no Quectel API)
- Automation rules engine (use HA automations instead)
- Alert/notification system (use HA notification integrations)
- WB12200 battery management write controls (read sensors only for that model; write support can be added later)
