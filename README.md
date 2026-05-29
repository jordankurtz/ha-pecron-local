# Pecron Local — Home Assistant Integration

Local-only Home Assistant integration for Pecron portable power stations (F3000LFP and all models using the Pecron app).

Communicates over **WiFi TCP** (port 6607) with **BLE fallback** — no ongoing cloud dependency.

**Credit:** Protocol reverse-engineering by [attractify-logan/pecron-monitor](https://github.com/attractify-logan/pecron-monitor) (MIT).

## Installation

1. Install via HACS → Custom Repositories → add this repo → category: Integration
2. Restart Home Assistant
3. Settings → Devices & Services → Add Integration → search "Pecron Local"

## Setup

One-time cloud call to fetch the device auth key, then fully local. Two options:
- **Sign in with Pecron account** — integration fetches the key automatically
- **Enter auth key manually** — paste from `pecron-monitor --setup` or the ha-pecron integration

## Supported Models

All models supported by the Pecron app (E300LFP through F5000LFP).

## Entities

Battery %, voltage, current, temperature, device status, all power sensors (AC/DC in/out, per-port solar), AC output detail (V/Hz/PF), time to full/empty, AC/DC/UPS switches, and all device settings (charging power, brightness, standby timeout, etc.).
