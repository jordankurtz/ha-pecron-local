# tests/test_switch.py
import pytest
from custom_components.pecron_local.switch import SWITCH_DESCRIPTIONS


def test_switch_descriptions_include_ac():
    keys = [s.key for s in SWITCH_DESCRIPTIONS]
    assert "ac_switch_hm" in keys


def test_switch_descriptions_include_dc_and_ups():
    keys = [s.key for s in SWITCH_DESCRIPTIONS]
    assert "dc_switch_hm" in keys
    assert "ups_status_hm" in keys
