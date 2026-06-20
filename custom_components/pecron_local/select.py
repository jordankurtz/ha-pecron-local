# custom_components/pecron_local/select.py
from __future__ import annotations
from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    AC_CHARGING_POWER_OPTIONS,
    AC_FREQUENCY_OPTIONS,
    AC_VOLTAGE_OPTIONS,
    AUTO_OFF_OPTIONS,
    DOMAIN,
    SCREEN_BRIGHTNESS_OPTIONS,
    STANDBY_TIMEOUT_OPTIONS,
)
from .coordinator import PecronCoordinator
from .entity import PecronEntity
from .sensor import _get_field
from .transport.base import TransportError


@dataclass(frozen=True, kw_only=True)
class PecronSelectDescription(SelectEntityDescription):
    key: str
    data_point_id: int
    options: list[str]


SELECT_DESCRIPTIONS: list[PecronSelectDescription] = [
    PecronSelectDescription(key="ac_charging_power_ios", name="AC Charging Power", data_point_id=50, options=AC_CHARGING_POWER_OPTIONS),
    PecronSelectDescription(key="machine_screen_light_as", name="Screen Brightness", data_point_id=45, options=SCREEN_BRIGHTNESS_OPTIONS),
    PecronSelectDescription(key="device_standy_times_as", name="Standby Timeout", data_point_id=51, options=STANDBY_TIMEOUT_OPTIONS),
    PecronSelectDescription(key="ac_output_voltage_io", name="AC Output Voltage", data_point_id=32, options=AC_VOLTAGE_OPTIONS),
    PecronSelectDescription(key="ac_output_frequency_io", name="AC Output Frequency", data_point_id=33, options=AC_FREQUENCY_OPTIONS),
    PecronSelectDescription(key="noastime_io", name="Auto-Off Time", data_point_id=34, options=AUTO_OFF_OPTIONS),
]


def _options_from_specs(specs: list[dict]) -> tuple[list[str], dict[int, str], dict[str, int]]:
    """Build (options_list, value→name, name→value) from TSL enum specs."""
    ordered = sorted(specs, key=lambda s: s["value"])
    options = [s["name"] for s in ordered]
    value_to_name = {s["value"]: s["name"] for s in ordered}
    name_to_value = {s["name"]: s["value"] for s in ordered}
    return options, value_to_name, name_to_value


class PecronSelect(PecronEntity, SelectEntity):
    entity_description: PecronSelectDescription

    def __init__(self, coordinator: PecronCoordinator, entry: ConfigEntry, description: PecronSelectDescription) -> None:
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description

        specs = coordinator.effective_controls.get(description.key, {}).get("specs")
        if specs and isinstance(specs, list):
            options, self._value_to_name, self._name_to_value = _options_from_specs(specs)
        else:
            options = description.options
            self._value_to_name = {i: opt for i, opt in enumerate(options)}
            self._name_to_value = {opt: i for i, opt in enumerate(options)}

        self._attr_options = options

    @property
    def current_option(self) -> str | None:
        if not self.coordinator.data:
            return None
        val = _get_field(self.coordinator.data, [(self.entity_description.key,)])
        if val is None:
            return None
        try:
            return self._value_to_name.get(int(val))
        except (TypeError, ValueError):
            return None

    async def async_select_option(self, option: str) -> None:
        device_value = self._name_to_value.get(option)
        if device_value is None:
            return
        transport = self.coordinator.active_transport
        if transport is None:
            return
        dpid = self.coordinator.data_point_id_for(
            self.entity_description.key, self.entity_description.data_point_id
        )
        try:
            await transport.write(dpid, device_value, "ENUM")
        except TransportError:
            pass
        await self.coordinator.async_request_refresh()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: PecronCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        PecronSelect(coordinator, entry, desc)
        for desc in SELECT_DESCRIPTIONS
    ])
