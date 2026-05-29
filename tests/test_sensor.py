# tests/test_sensor.py
import pytest
from unittest.mock import MagicMock
from custom_components.pecron_local.sensor import _get_field, SENSOR_DESCRIPTIONS
from custom_components.pecron_local.const import SENSOR_FIELDS


def test_get_field_top_level():
    kv = {"battery_percentage": 75}
    val = _get_field(kv, SENSOR_FIELDS["battery_percent"])
    assert val == 75


def test_get_field_nested():
    kv = {"host_packet_data_jdb": {"host_packet_electric_percentage": 80}}
    val = _get_field(kv, SENSOR_FIELDS["battery_percent"])
    assert val == 80


def test_get_field_missing_returns_none():
    val = _get_field({}, SENSOR_FIELDS["battery_percent"])
    assert val is None


def test_get_field_ac_output_power():
    kv = {"ac_data_output_hm": {"ac_output_power": 500}}
    val = _get_field(kv, SENSOR_FIELDS["ac_output_power"])
    assert val == 500


def test_sensor_descriptions_include_battery():
    codes = [d.key for d in SENSOR_DESCRIPTIONS]
    assert "battery_percent" in codes


def test_sensor_descriptions_include_solar_ports():
    codes = [d.key for d in SENSOR_DESCRIPTIONS]
    assert "dc5521_input_power" in codes
    assert "gx16mf1_input_power" in codes
    assert "gx16mf2_input_power" in codes
