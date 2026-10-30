"""Tests for the RutOS data coordinator."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.rutos.api import (
    RutOSAPIError,
    RutOSAuthError,
    RutOSConnectionError,
)
from custom_components.rutos.const import (
    CONNECTION_BACKOFF_INTERVALS,
    DEFAULT_SCAN_INTERVAL,
)
from custom_components.rutos.coordinator import RutOSData, RutOSDataUpdateCoordinator
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed


async def test_async_setup_fetches_device_info(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_device_info: dict,
    mock_config_entry: MockConfigEntry,
):
    """Test _async_setup populates device_info."""
    mock_config_entry.add_to_hass(hass)
    coordinator = RutOSDataUpdateCoordinator(hass, mock_config_entry, mock_api)
    coordinator.data = RutOSData()

    await coordinator._async_setup()

    assert coordinator.data.device_info == mock_device_info
    mock_api.get_device_info.assert_awaited_once()


async def test_async_setup_auth_error_raises_update_failed(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
):
    """Test API auth error during setup raises UpdateFailed."""
    mock_api.get_device_info.side_effect = RutOSAuthError("bad creds")
    mock_config_entry.add_to_hass(hass)
    coordinator = RutOSDataUpdateCoordinator(hass, mock_config_entry, mock_api)

    with pytest.raises(UpdateFailed, match="Authentication failed"):
        await coordinator._async_setup()


async def test_async_setup_api_error_raises_update_failed(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
):
    """Test generic API error during setup raises UpdateFailed."""
    mock_api.get_device_info.side_effect = RutOSAPIError("timeout")
    mock_config_entry.add_to_hass(hass)
    coordinator = RutOSDataUpdateCoordinator(hass, mock_config_entry, mock_api)

    with pytest.raises(UpdateFailed, match="Failed to get device info"):
        await coordinator._async_setup()


async def test_async_update_data_returns_rutos_data(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_wan_interfaces: list[dict],
    mock_config_entry: MockConfigEntry,
):
    """Test _async_update_data returns populated RutOSData."""
    mock_config_entry.add_to_hass(hass)
    coordinator = RutOSDataUpdateCoordinator(hass, mock_config_entry, mock_api)
    coordinator.data = RutOSData()

    result = await coordinator._async_update_data()

    assert isinstance(result, RutOSData)
    assert result.wan_interfaces == mock_wan_interfaces
    assert result.internet_available is True
    assert result.gps_position is not None
    assert result.gps_position["latitude"] == 37.7749
    assert len(result.data_limit) == 1
    assert result.data_limit[0]["id"] == "limit1"
    assert len(result.modem_signal) == 1
    assert result.modem_signal[0]["id"] == "modem1"
    assert len(result.modems) == 1
    assert result.modems[0]["id"] == "modem1"
    assert result.failover_status["mob1s1a1"]["status"] == "online"
    mock_api.get_wan_interfaces.assert_awaited_once()
    mock_api.get_internet_status.assert_awaited_once()
    mock_api.get_gps_position.assert_awaited_once()
    mock_api.get_data_limit.assert_awaited_once()
    mock_api.get_modem_data.assert_awaited_once()
    mock_api.get_failover_status.assert_awaited_once()


async def test_async_update_data_auth_error_raises_update_failed(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
):
    """Test auth error during update raises UpdateFailed."""
    mock_api.get_wan_interfaces.side_effect = RutOSAuthError("expired")
    mock_config_entry.add_to_hass(hass)
    coordinator = RutOSDataUpdateCoordinator(hass, mock_config_entry, mock_api)
    coordinator.data = RutOSData()

    with pytest.raises(UpdateFailed, match="Authentication failed"):
        await coordinator._async_update_data()


async def test_async_update_data_api_error_raises_update_failed(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
):
    """Test API error during update raises UpdateFailed."""
    mock_api.get_wan_interfaces.side_effect = RutOSAPIError("network down")
    mock_config_entry.add_to_hass(hass)
    coordinator = RutOSDataUpdateCoordinator(hass, mock_config_entry, mock_api)
    coordinator.data = RutOSData()

    with pytest.raises(UpdateFailed, match="Error communicating"):
        await coordinator._async_update_data()


async def test_connection_failure_stops_the_poll(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
):
    """Test a connection failure leaves the remaining endpoints unrequested."""
    mock_api.get_internet_status.side_effect = RutOSConnectionError("timed out")
    mock_config_entry.add_to_hass(hass)
    coordinator = RutOSDataUpdateCoordinator(hass, mock_config_entry, mock_api)
    coordinator.data = RutOSData()

    with pytest.raises(UpdateFailed, match="Error communicating"):
        await coordinator._async_update_data()

    mock_api.get_wan_interfaces.assert_awaited_once()
    mock_api.get_gps_position.assert_not_awaited()
    mock_api.get_failover_status.assert_not_awaited()
    assert coordinator.data.wan_interfaces == []


async def test_requests_do_not_overlap(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
):
    """Test each endpoint is awaited only after the previous one finished."""
    in_flight = 0
    peak = 0

    def _tracked(result):
        async def _call():
            nonlocal in_flight, peak
            in_flight += 1
            peak = max(peak, in_flight)
            await asyncio.sleep(0)
            in_flight -= 1
            return result

        return _call

    for name in (
        "get_wan_interfaces",
        "get_internet_status",
        "get_gps_position",
        "get_data_limit",
        "get_modem_data",
        "get_active_failover_chain",
        "get_failover_status",
    ):
        method = getattr(mock_api, name)
        method.side_effect = _tracked(method.return_value)
    mock_config_entry.add_to_hass(hass)
    coordinator = RutOSDataUpdateCoordinator(hass, mock_config_entry, mock_api)

    await coordinator._async_update_data()

    assert peak == 1


async def test_connection_failures_back_off(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
):
    """Test repeated connection failures widen the interval up to the cap."""
    mock_api.get_wan_interfaces.side_effect = RutOSConnectionError("timed out")
    mock_config_entry.add_to_hass(hass)
    coordinator = RutOSDataUpdateCoordinator(hass, mock_config_entry, mock_api)

    for seconds in (*CONNECTION_BACKOFF_INTERVALS, CONNECTION_BACKOFF_INTERVALS[-1]):
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()
        assert coordinator.update_interval == timedelta(seconds=seconds)


async def test_successful_poll_restores_interval(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_wan_interfaces: list[dict],
    mock_config_entry: MockConfigEntry,
):
    """Test the first success returns to the normal interval and resets backoff."""
    mock_api.get_wan_interfaces.side_effect = RutOSConnectionError("timed out")
    mock_config_entry.add_to_hass(hass)
    coordinator = RutOSDataUpdateCoordinator(hass, mock_config_entry, mock_api)

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()

    mock_api.get_wan_interfaces.side_effect = None
    await coordinator._async_update_data()
    assert coordinator.update_interval == timedelta(seconds=DEFAULT_SCAN_INTERVAL)

    mock_api.get_wan_interfaces.side_effect = RutOSConnectionError("timed out")
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
    assert coordinator.update_interval == timedelta(
        seconds=CONNECTION_BACKOFF_INTERVALS[0]
    )


async def test_api_error_does_not_back_off(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
):
    """Test an error response keeps the interval: the router is still answering."""
    mock_api.get_wan_interfaces.side_effect = RutOSAPIError("bad request")
    mock_config_entry.add_to_hass(hass)
    coordinator = RutOSDataUpdateCoordinator(hass, mock_config_entry, mock_api)

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()

    assert coordinator.update_interval == timedelta(seconds=DEFAULT_SCAN_INTERVAL)


async def test_update_interval_is_30s(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
):
    """Test coordinator uses the configured scan interval."""
    mock_config_entry.add_to_hass(hass)
    coordinator = RutOSDataUpdateCoordinator(hass, mock_config_entry, mock_api)
    assert coordinator.update_interval == timedelta(seconds=DEFAULT_SCAN_INTERVAL)


async def test_async_setup_initializes_data_when_none(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_device_info: dict,
    mock_config_entry: MockConfigEntry,
):
    """Test _async_setup creates RutOSData when self.data is None."""
    mock_config_entry.add_to_hass(hass)
    coordinator = RutOSDataUpdateCoordinator(hass, mock_config_entry, mock_api)
    # Leave coordinator.data as None (the default before first refresh)
    assert coordinator.data is None

    await coordinator._async_setup()

    assert coordinator.data is not None
    assert coordinator.data.device_info == mock_device_info


async def test_async_update_data_initializes_data_when_none(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_wan_interfaces: list[dict],
    mock_config_entry: MockConfigEntry,
):
    """Test _async_update_data creates RutOSData when self.data is None."""
    mock_config_entry.add_to_hass(hass)
    coordinator = RutOSDataUpdateCoordinator(hass, mock_config_entry, mock_api)
    assert coordinator.data is None

    result = await coordinator._async_update_data()

    assert isinstance(result, RutOSData)
    assert result.wan_interfaces == mock_wan_interfaces
    assert result.gps_position is not None
    assert len(result.data_limit) == 1
    assert len(result.modem_signal) == 1
    assert len(result.modems) == 1
