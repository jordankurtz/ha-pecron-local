# custom_components/pecron_local/entity.py
from __future__ import annotations
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN
from .coordinator import PecronCoordinator


class PecronEntity(CoordinatorEntity[PecronCoordinator]):
    """Base entity. Unavailable when coordinator has no data."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: PecronCoordinator, entry: ConfigEntry, key: str) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Pecron",
        )

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data is not None
