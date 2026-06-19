# custom_components/pecron_local/switch.py
from __future__ import annotations
from dataclasses import dataclass

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SENSOR_FIELDS
from .coordinator import PecronCoordinator
from .entity import PecronEntity
from .sensor import _get_field
from .transport.base import TransportError


@dataclass(frozen=True, kw_only=True)
class PecronSwitchDescription(SwitchEntityDescription):
    key: str
    data_point_id: int


SWITCH_DESCRIPTIONS: list[PecronSwitchDescription] = [
    PecronSwitchDescription(key="ac_switch_hm", name="AC Output", data_point_id=40),
    PecronSwitchDescription(key="dc_switch_hm", name="DC Output", data_point_id=38),
    PecronSwitchDescription(key="ups_status_hm", name="UPS Mode", data_point_id=27),
    PecronSwitchDescription(key="device_touch_locking_as", name="Touch Lock", data_point_id=42),
    PecronSwitchDescription(key="auto_light_flag_as", name="Auto Screen Light", data_point_id=43),
    PecronSwitchDescription(key="eco_quite_mode_as", name="Eco/Quiet Mode", data_point_id=44),
]

_SWITCH_FIELD_MAP = {
    "ac_switch_hm": SENSOR_FIELDS.get("ac_switch", [("ac_switch_hm",)]),
    "dc_switch_hm": SENSOR_FIELDS.get("dc_switch", [("dc_switch_hm",)]),
    "ups_status_hm": SENSOR_FIELDS.get("ups_mode", [("ups_status_hm",)]),
    "device_touch_locking_as": [("device_touch_locking_as",)],
    "auto_light_flag_as": [("auto_light_flag_as",)],
    "eco_quite_mode_as": [("eco_quite_mode_as",)],
}


class PecronSwitch(PecronEntity, SwitchEntity):
    entity_description: PecronSwitchDescription

    def __init__(self, coordinator: PecronCoordinator, entry: ConfigEntry, description: PecronSwitchDescription) -> None:
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        if not self.coordinator.data:
            return None
        val = _get_field(self.coordinator.data, _SWITCH_FIELD_MAP.get(self.entity_description.key, [(self.entity_description.key,)]))
        return bool(val) if val is not None else None

    async def async_turn_on(self, **kwargs) -> None:
        await self._send_write(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._send_write(False)

    async def _send_write(self, value: bool) -> None:
        transport = self.coordinator.active_transport
        if transport is None:
            return
        try:
            await transport.write(self.entity_description.data_point_id, value, "BOOL")
        except TransportError:
            pass
        await self.coordinator.async_request_refresh()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: PecronCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        PecronSwitch(coordinator, entry, desc)
        for desc in SWITCH_DESCRIPTIONS
    ])
