# custom_components/pecron_local/sensor.py
from __future__ import annotations
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SENSOR_FIELDS, DEVICE_STATUS_LABELS, CHARGE_STATUS_LABELS
from .coordinator import PecronCoordinator
from .entity import PecronEntity


@dataclass(frozen=True, kw_only=True)
class PecronSensorDescription(SensorEntityDescription):
    key: str


def _get_field(kv: dict, paths: list[tuple]) -> object | None:
    for path in paths:
        node = kv
        for part in path:
            if not isinstance(node, dict) or part not in node:
                node = None
                break
            node = node[part]
        if node is not None:
            return node
    return None


SENSOR_DESCRIPTIONS: list[PecronSensorDescription] = [
    PecronSensorDescription(key="battery_percent", name="Battery", native_unit_of_measurement=PERCENTAGE, device_class=SensorDeviceClass.BATTERY, state_class=SensorStateClass.MEASUREMENT),
    PecronSensorDescription(key="voltage", name="Voltage", native_unit_of_measurement=UnitOfElectricPotential.VOLT, device_class=SensorDeviceClass.VOLTAGE, state_class=SensorStateClass.MEASUREMENT),
    PecronSensorDescription(key="current", name="Current", native_unit_of_measurement=UnitOfElectricCurrent.AMPERE, device_class=SensorDeviceClass.CURRENT, state_class=SensorStateClass.MEASUREMENT),
    PecronSensorDescription(key="temperature", name="Temperature", native_unit_of_measurement=UnitOfTemperature.CELSIUS, device_class=SensorDeviceClass.TEMPERATURE, state_class=SensorStateClass.MEASUREMENT),
    PecronSensorDescription(key="battery_temp", name="Battery Temperature", native_unit_of_measurement=UnitOfTemperature.CELSIUS, device_class=SensorDeviceClass.TEMPERATURE, state_class=SensorStateClass.MEASUREMENT),
    PecronSensorDescription(key="charging_plate_temp", name="Charging Plate Temperature", native_unit_of_measurement=UnitOfTemperature.CELSIUS, device_class=SensorDeviceClass.TEMPERATURE, state_class=SensorStateClass.MEASUREMENT),
    PecronSensorDescription(key="inverter_temp", name="Inverter Temperature", native_unit_of_measurement=UnitOfTemperature.CELSIUS, device_class=SensorDeviceClass.TEMPERATURE, state_class=SensorStateClass.MEASUREMENT),
    PecronSensorDescription(key="total_input_power", name="Total Input Power", native_unit_of_measurement=UnitOfPower.WATT, device_class=SensorDeviceClass.POWER, state_class=SensorStateClass.MEASUREMENT),
    PecronSensorDescription(key="total_output_power", name="Total Output Power", native_unit_of_measurement=UnitOfPower.WATT, device_class=SensorDeviceClass.POWER, state_class=SensorStateClass.MEASUREMENT),
    PecronSensorDescription(key="ac_input_power", name="AC Input Power", native_unit_of_measurement=UnitOfPower.WATT, device_class=SensorDeviceClass.POWER, state_class=SensorStateClass.MEASUREMENT),
    PecronSensorDescription(key="ac_output_power", name="AC Output Power", native_unit_of_measurement=UnitOfPower.WATT, device_class=SensorDeviceClass.POWER, state_class=SensorStateClass.MEASUREMENT),
    PecronSensorDescription(key="dc_input_power", name="DC Input Power", native_unit_of_measurement=UnitOfPower.WATT, device_class=SensorDeviceClass.POWER, state_class=SensorStateClass.MEASUREMENT),
    PecronSensorDescription(key="dc_output_power", name="DC Output Power", native_unit_of_measurement=UnitOfPower.WATT, device_class=SensorDeviceClass.POWER, state_class=SensorStateClass.MEASUREMENT),
    PecronSensorDescription(key="dc5521_input_voltage", name="Solar Port 1 Voltage", native_unit_of_measurement=UnitOfElectricPotential.VOLT, device_class=SensorDeviceClass.VOLTAGE, state_class=SensorStateClass.MEASUREMENT),
    PecronSensorDescription(key="dc5521_input_current", name="Solar Port 1 Current", native_unit_of_measurement=UnitOfElectricCurrent.AMPERE, device_class=SensorDeviceClass.CURRENT, state_class=SensorStateClass.MEASUREMENT),
    PecronSensorDescription(key="dc5521_input_power", name="Solar Port 1 Power", native_unit_of_measurement=UnitOfPower.WATT, device_class=SensorDeviceClass.POWER, state_class=SensorStateClass.MEASUREMENT),
    PecronSensorDescription(key="gx16mf1_input_voltage", name="Solar Port 2 Voltage", native_unit_of_measurement=UnitOfElectricPotential.VOLT, device_class=SensorDeviceClass.VOLTAGE, state_class=SensorStateClass.MEASUREMENT),
    PecronSensorDescription(key="gx16mf1_input_current", name="Solar Port 2 Current", native_unit_of_measurement=UnitOfElectricCurrent.AMPERE, device_class=SensorDeviceClass.CURRENT, state_class=SensorStateClass.MEASUREMENT),
    PecronSensorDescription(key="gx16mf1_input_power", name="Solar Port 2 Power", native_unit_of_measurement=UnitOfPower.WATT, device_class=SensorDeviceClass.POWER, state_class=SensorStateClass.MEASUREMENT),
    PecronSensorDescription(key="gx16mf2_input_voltage", name="Solar Port 3 Voltage", native_unit_of_measurement=UnitOfElectricPotential.VOLT, device_class=SensorDeviceClass.VOLTAGE, state_class=SensorStateClass.MEASUREMENT),
    PecronSensorDescription(key="gx16mf2_input_current", name="Solar Port 3 Current", native_unit_of_measurement=UnitOfElectricCurrent.AMPERE, device_class=SensorDeviceClass.CURRENT, state_class=SensorStateClass.MEASUREMENT),
    PecronSensorDescription(key="gx16mf2_input_power", name="Solar Port 3 Power", native_unit_of_measurement=UnitOfPower.WATT, device_class=SensorDeviceClass.POWER, state_class=SensorStateClass.MEASUREMENT),
    PecronSensorDescription(key="ac_output_voltage", name="AC Output Voltage", native_unit_of_measurement=UnitOfElectricPotential.VOLT, device_class=SensorDeviceClass.VOLTAGE, state_class=SensorStateClass.MEASUREMENT),
    PecronSensorDescription(key="ac_output_hz", name="AC Output Frequency", native_unit_of_measurement="Hz", device_class=SensorDeviceClass.FREQUENCY, state_class=SensorStateClass.MEASUREMENT),
    PecronSensorDescription(key="ac_output_pf", name="AC Power Factor", native_unit_of_measurement=None, state_class=SensorStateClass.MEASUREMENT),
    PecronSensorDescription(key="remain_time", name="Time to Empty", native_unit_of_measurement=UnitOfTime.MINUTES, device_class=SensorDeviceClass.DURATION, state_class=SensorStateClass.MEASUREMENT),
    PecronSensorDescription(key="remain_charging_time", name="Time to Full", native_unit_of_measurement=UnitOfTime.MINUTES, device_class=SensorDeviceClass.DURATION, state_class=SensorStateClass.MEASUREMENT),
    PecronSensorDescription(key="device_status_hm", name="Device Status", native_unit_of_measurement=None),
    PecronSensorDescription(key="charge_status", name="Charge Status", native_unit_of_measurement=None),
    PecronSensorDescription(key="ac_charging_power", name="AC Charging Power", native_unit_of_measurement=PERCENTAGE, state_class=SensorStateClass.MEASUREMENT),
]


class PecronSensor(PecronEntity, SensorEntity):
    entity_description: PecronSensorDescription

    def __init__(self, coordinator: PecronCoordinator, entry: ConfigEntry, description: PecronSensorDescription) -> None:
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> object:
        if not self.coordinator.data:
            return None
        raw = _get_field(self.coordinator.data, SENSOR_FIELDS.get(self.entity_description.key, []))
        if self.entity_description.key == "device_status_hm" and raw is not None:
            return DEVICE_STATUS_LABELS.get(int(raw), str(raw))
        if self.entity_description.key == "charge_status" and raw is not None:
            return CHARGE_STATUS_LABELS.get(int(raw), str(raw))
        return raw


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: PecronCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        PecronSensor(coordinator, entry, desc)
        for desc in SENSOR_DESCRIPTIONS
    ])
