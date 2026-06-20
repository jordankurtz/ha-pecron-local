from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CLOUD_TSL_ALIASES,
    CONF_AUTH_KEY,
    CONF_MAC,
    CONF_POLL_INTERVAL,
    CONF_PREFERRED_TRANSPORT,
    CONF_TSL,
    CONTROLS,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    PLATFORMS,
    TRANSPORT_BLE,
    TRANSPORT_TCP,
)
from .coordinator import PecronCoordinator
from .transport.tcp import TcpTransport
from .transport.ble import BleTransport


def _build_effective_controls(tsl: dict) -> dict:
    """Merge cloud TSL IDs into our canonical CONTROLS dict.

    Different Pecron models assign different data point IDs to the same controls.
    The cloud TSL provides the authoritative ID mapping for each device model.
    CLOUD_TSL_ALIASES handles cases where the cloud uses a different code name
    (e.g. 'false_touch_us') for the same control that HA calls something else
    (e.g. 'device_touch_locking_as').
    """
    effective = {k: dict(v) for k, v in CONTROLS.items()}

    # Build cloud_code → HA_key lookup: direct matches + aliases
    cloud_to_ha: dict[str, str] = {k: k for k in CONTROLS}
    cloud_to_ha.update(CLOUD_TSL_ALIASES)

    for cloud_code, info in tsl.items():
        ha_key = cloud_to_ha.get(cloud_code)
        if ha_key and ha_key in effective:
            effective[ha_key]["id"] = info["id"]
            if "specs" in info:
                effective[ha_key]["specs"] = info["specs"]

    return effective


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    auth_key_b64 = entry.data[CONF_AUTH_KEY]
    host = entry.data.get("host")
    mac = entry.data.get(CONF_MAC)
    poll_interval = entry.data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
    preferred = entry.data.get(CONF_PREFERRED_TRANSPORT, TRANSPORT_TCP)

    tsl = entry.data.get(CONF_TSL, {})
    effective_controls = _build_effective_controls(tsl) if tsl else CONTROLS

    tcp = TcpTransport(host=host, auth_key_b64=auth_key_b64, controls=effective_controls) if host else None
    ble = BleTransport(mac=mac, auth_key_b64=auth_key_b64, controls=effective_controls) if mac else None

    if preferred == TRANSPORT_TCP:
        first, second = tcp, ble
    else:
        first, second = ble, tcp

    coordinator = PecronCoordinator(
        hass,
        tcp=first,
        ble=second,
        poll_interval=poll_interval,
        effective_controls=effective_controls,
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        coordinator: PecronCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        if coordinator.active_transport:
            await coordinator.active_transport.disconnect()
    return unloaded
