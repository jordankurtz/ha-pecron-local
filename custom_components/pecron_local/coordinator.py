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
        effective_controls: dict | None = None,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="Pecron Local",
            update_interval=timedelta(seconds=poll_interval),
        )
        self._transports = [t for t in [tcp, ble] if t is not None]
        self.active_transport: PecronTransport | None = None
        self.effective_controls: dict = effective_controls or {}

    def data_point_id_for(self, key: str, fallback: int) -> int:
        """Return the device-specific data point ID for a control key."""
        ctrl = self.effective_controls.get(key, {})
        return ctrl.get("id", fallback)

    async def _async_update_data(self) -> dict:
        errors: list[str] = []
        for transport in self._transports:
            # Attempt up to 2 tries per transport: once with an existing
            # connection and once after a fresh connect. Pecron firmware
            # closes the TCP socket after each response, so the second
            # attempt handles the reconnect transparently.
            for attempt in range(2):
                try:
                    if not transport.connected:
                        await transport.connect()
                    data = await transport.read()
                    self.active_transport = transport
                    return data
                except TransportError as exc:
                    _LOGGER.debug(
                        "Transport %s attempt %d failed: %s",
                        type(transport).__name__, attempt + 1, exc,
                    )
                    try:
                        await transport.disconnect()
                    except Exception:
                        pass
                    if attempt == 1:
                        errors.append(f"{type(transport).__name__}: {exc}")

        self.active_transport = None
        raise UpdateFailed(f"All transports failed — {'; '.join(errors)}")
