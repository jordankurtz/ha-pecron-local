# tests/test_select.py
import pytest
from custom_components.pecron_local.select import SELECT_DESCRIPTIONS


def test_select_descriptions_include_ac_charging_power():
    keys = [s.key for s in SELECT_DESCRIPTIONS]
    assert "ac_charging_power_ios" in keys


def test_select_descriptions_include_brightness():
    keys = [s.key for s in SELECT_DESCRIPTIONS]
    assert "machine_screen_light_as" in keys
