# tests/test_tcp_transport.py
import asyncio
import base64
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from custom_components.pecron_local.transport.tcp import TcpTransport
from custom_components.pecron_local.transport.base import TransportError


@pytest.fixture
def auth_key_b64():
    return base64.b64encode(b"0123456789abcdef").decode()


@pytest.fixture
def transport(auth_key_b64):
    return TcpTransport(host="192.168.1.100", auth_key_b64=auth_key_b64)


def test_transport_not_connected_initially(transport):
    assert not transport.connected


async def test_read_raises_transport_error_when_not_connected(transport):
    with pytest.raises(TransportError):
        await transport.read()


async def test_write_raises_transport_error_when_not_connected(transport):
    with pytest.raises(TransportError):
        await transport.write(data_point_id=40, value=True, ctrl_type="BOOL")


async def test_connect_failure_raises_transport_error(transport):
    with patch("asyncio.open_connection", side_effect=OSError("refused")):
        with pytest.raises(TransportError):
            await transport.connect()


async def test_disconnect_when_not_connected_is_safe(transport):
    await transport.disconnect()  # Should not raise
