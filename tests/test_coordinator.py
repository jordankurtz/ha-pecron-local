import pytest
from unittest.mock import AsyncMock, MagicMock
from homeassistant.helpers.update_coordinator import UpdateFailed
from custom_components.pecron_local.coordinator import PecronCoordinator
from custom_components.pecron_local.transport.base import TransportError


@pytest.fixture
def mock_tcp():
    t = AsyncMock()
    t.connected = False
    return t


@pytest.fixture
def mock_ble():
    t = AsyncMock()
    t.connected = False
    return t


@pytest.fixture
def coordinator(hass, mock_tcp, mock_ble):
    return PecronCoordinator(hass, tcp=mock_tcp, ble=mock_ble, poll_interval=30)


async def test_tcp_success_returns_data(coordinator, mock_tcp):
    mock_tcp.connected = False
    mock_tcp.connect = AsyncMock()
    mock_tcp.read = AsyncMock(return_value={"battery_percentage": 80})

    data = await coordinator._async_update_data()
    assert data["battery_percentage"] == 80
    assert coordinator.active_transport is mock_tcp


async def test_tcp_fail_falls_back_to_ble(coordinator, mock_tcp, mock_ble):
    mock_tcp.connect = AsyncMock(side_effect=TransportError("refused"))
    mock_ble.connect = AsyncMock()
    mock_ble.read = AsyncMock(return_value={"battery_percentage": 60})

    data = await coordinator._async_update_data()
    assert data["battery_percentage"] == 60
    assert coordinator.active_transport is mock_ble


async def test_both_fail_raises_update_failed(coordinator, mock_tcp, mock_ble):
    mock_tcp.connect = AsyncMock(side_effect=TransportError("refused"))
    mock_ble.connect = AsyncMock(side_effect=TransportError("ble error"))

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_active_transport_none_before_first_poll(coordinator):
    assert coordinator.active_transport is None


async def test_reuses_open_tcp_connection(coordinator, mock_tcp):
    mock_tcp.connected = True
    mock_tcp.read = AsyncMock(return_value={"battery_percentage": 90})

    data = await coordinator._async_update_data()
    mock_tcp.connect.assert_not_called()
    assert data["battery_percentage"] == 90
