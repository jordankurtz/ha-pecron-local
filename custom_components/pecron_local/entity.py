# custom_components/pecron_local/entity.py
from __future__ import annotations
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .coordinator import PecronCoordinator


class PecronEntity(CoordinatorEntity[PecronCoordinator]):
    """Base entity. Unavailable when coordinator has no data."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: PecronCoordinator, entry_id: str, key: str) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"{entry_id}_{key}"

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data is not None
