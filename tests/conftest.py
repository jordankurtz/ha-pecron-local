import pytest
from unittest.mock import patch
from pytest_homeassistant_custom_component.common import MockConfigEntry

pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Automatically enable custom integrations for all tests."""
    return


@pytest.fixture(autouse=True)
def mock_scan_for_devices():
    """Prevent real LAN scans during tests."""
    with patch(
        "custom_components.pecron_local.config_flow.scan_for_devices",
        return_value=[],
    ):
        yield
