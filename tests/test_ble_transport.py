# tests/test_ble_transport.py
import asyncio
import base64
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from custom_components.pecron_local.transport.ble import BleTransport
from custom_components.pecron_local.transport.base import TransportError


@pytest.fixture
def auth_key_b64():
    return base64.b64encode(b"0123456789abcdef").decode()


@pytest.fixture
def transport(auth_key_b64):
    return BleTransport(mac="AA:BB:CC:DD:EE:FF", auth_key_b64=auth_key_b64)


def test_not_connected_initially(transport):
    assert not transport.connected


async def test_read_raises_when_not_connected(transport):
    with pytest.raises(TransportError):
        await transport.read()


async def test_write_raises_when_not_connected(transport):
    with pytest.raises(TransportError):
        await transport.write(40, True, "BOOL")


async def test_disconnect_when_not_connected_is_safe(transport):
    await transport.disconnect()  # must not raise


async def test_connect_failure_raises_transport_error(transport):
    with patch("custom_components.pecron_local.transport.ble.BleakClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.connect = AsyncMock(side_effect=Exception("BLE error"))
        mock_client.disconnect = AsyncMock()
        mock_client_cls.return_value = mock_client
        with pytest.raises(TransportError):
            await transport.connect()
