# tests/test_config_flow.py
import base64
import pytest
from unittest.mock import AsyncMock, patch
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from custom_components.pecron_local.const import DOMAIN


async def test_flow_shows_device_selector(hass):
    with patch(
        "custom_components.pecron_local.config_flow.scan_for_devices",
        return_value=[],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    # Schema should have a "device" selector
    assert "device" in result["data_schema"].schema


async def test_flow_with_discovered_device(hass):
    with patch(
        "custom_components.pecron_local.config_flow.scan_for_devices",
        return_value=[{"host": "192.168.1.50", "name": "Pecron @ 192.168.1.50"}],
    ), patch(
        "custom_components.pecron_local.coordinator.PecronCoordinator.async_config_entry_first_refresh",
        new_callable=AsyncMock,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["step_id"] == "user"

        # Pick the discovered device
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"device": "192.168.1.50"}
        )
        assert result2["step_id"] == "auth_method"

        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"], {"auth_method": "manual"}
        )
        assert result3["step_id"] == "manual_key"

        valid_key = base64.b64encode(b"0123456789abcdef").decode()
        result4 = await hass.config_entries.flow.async_configure(
            result3["flow_id"], {"auth_key": valid_key}
        )
    assert result4["type"] == FlowResultType.CREATE_ENTRY
    assert result4["data"]["host"] == "192.168.1.50"


async def test_manual_ip_flow_creates_entry(hass):
    with patch(
        "custom_components.pecron_local.config_flow.scan_for_devices",
        return_value=[],
    ), patch(
        "custom_components.pecron_local.coordinator.PecronCoordinator.async_config_entry_first_refresh",
        new_callable=AsyncMock,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        # Pick manual IP
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"device": "manual_ip"}
        )
        assert result2["step_id"] == "manual_host"

        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"], {"host": "192.168.1.100"}
        )
        assert result3["step_id"] == "auth_method"

        result4 = await hass.config_entries.flow.async_configure(
            result3["flow_id"], {"auth_method": "manual"}
        )
        assert result4["step_id"] == "manual_key"

        valid_key = base64.b64encode(b"0123456789abcdef").decode()
        result5 = await hass.config_entries.flow.async_configure(
            result4["flow_id"], {"auth_key": valid_key}
        )
    assert result5["type"] == FlowResultType.CREATE_ENTRY
    assert result5["data"]["host"] == "192.168.1.100"


async def test_manual_mac_flow_creates_entry(hass):
    with patch(
        "custom_components.pecron_local.config_flow.scan_for_devices",
        return_value=[],
    ), patch(
        "custom_components.pecron_local.coordinator.PecronCoordinator.async_config_entry_first_refresh",
        new_callable=AsyncMock,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"device": "manual_mac"}
        )
        assert result2["step_id"] == "manual_mac"

        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"], {"mac": "AA:BB:CC:DD:EE:FF"}
        )
        assert result3["step_id"] == "auth_method"

        result4 = await hass.config_entries.flow.async_configure(
            result3["flow_id"], {"auth_method": "manual"}
        )
        assert result4["step_id"] == "manual_key"

        valid_key = base64.b64encode(b"0123456789abcdef").decode()
        result5 = await hass.config_entries.flow.async_configure(
            result4["flow_id"], {"auth_key": valid_key}
        )
    assert result5["type"] == FlowResultType.CREATE_ENTRY
    assert result5["data"]["mac"] == "AA:BB:CC:DD:EE:FF"


async def test_invalid_mac_shows_error(hass):
    with patch(
        "custom_components.pecron_local.config_flow.scan_for_devices",
        return_value=[],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"device": "manual_mac"}
        )
        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"], {"mac": "not-a-mac"}
        )
    assert result3["type"] == FlowResultType.FORM
    assert result3["step_id"] == "manual_mac"
    assert "mac" in result3["errors"]


async def test_bluetooth_discovery_flow(hass):
    from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
    from unittest.mock import MagicMock

    service_info = MagicMock(spec=BluetoothServiceInfoBleak)
    service_info.name = "QUEC_BLE_EEFF"
    service_info.address = "AA:BB:CC:DD:EE:FF"

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_BLUETOOTH},
        data=service_info,
    )
    assert result["type"] in (FlowResultType.FORM, FlowResultType.ABORT)
