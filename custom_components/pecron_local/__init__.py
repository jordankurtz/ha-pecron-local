from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_AUTH_KEY,
    CONF_MAC,
    CONF_POLL_INTERVAL,
    CONF_PREFERRED_TRANSPORT,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    PLATFORMS,
    TRANSPORT_BLE,
    TRANSPORT_TCP,
)
from .coordinator import PecronCoordinator
from .transport.tcp import TcpTransport
from .transport.ble import BleTransport


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    auth_key_b64 = entry.data[CONF_AUTH_KEY]
    host = entry.data.get("host")
    mac = entry.data.get(CONF_MAC)
    poll_interval = entry.data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
    preferred = entry.data.get(CONF_PREFERRED_TRANSPORT, TRANSPORT_TCP)

    tcp = TcpTransport(host=host, auth_key_b64=auth_key_b64) if host else None
    ble = BleTransport(mac=mac, auth_key_b64=auth_key_b64) if mac else None

    if preferred == TRANSPORT_TCP:
        first, second = tcp, ble
    else:
        first, second = ble, tcp

    coordinator = PecronCoordinator(
        hass,
        tcp=first,
        ble=second,
        poll_interval=poll_interval,
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
