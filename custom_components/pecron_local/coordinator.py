from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .transport.base import PecronTransport, TransportError

_LOGGER = logging.getLogger(__name__)


class PecronCoordinator(DataUpdateCoordinator[dict]):
    """Poll device via TCP then BLE fallback. Tracks active transport for writes."""

    def __init__(
        self,
        hass: HomeAssistant,
        tcp: PecronTransport | None,
        ble: PecronTransport | None,
        poll_interval: int = 30,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="Pecron Local",
            update_interval=timedelta(seconds=poll_interval),
        )
        self._transports = [t for t in [tcp, ble] if t is not None]
        self.active_transport: PecronTransport | None = None

    async def _async_update_data(self) -> dict:
        for transport in self._transports:
            try:
                if not transport.connected:
                    await transport.connect()
                data = await transport.read()
                self.active_transport = transport
                return data
            except TransportError as exc:
                _LOGGER.debug("Transport %s failed: %s", type(transport).__name__, exc)
                try:
                    await transport.disconnect()
                except Exception:
                    pass
                continue

        self.active_transport = None
        raise UpdateFailed("All transports failed")
