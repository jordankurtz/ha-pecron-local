from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_AUTH_KEY, DOMAIN
from .coordinator import PecronCoordinator


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    coordinator: PecronCoordinator = hass.data[DOMAIN][entry.entry_id]
    redacted_data = {**entry.data, CONF_AUTH_KEY: "**REDACTED**"}
    return {
        "config_entry": redacted_data,
        "coordinator_data": coordinator.data,
        "active_transport": (
            type(coordinator.active_transport).__name__
            if coordinator.active_transport
            else None
        ),
        "last_update_success": coordinator.last_update_success,
    }
