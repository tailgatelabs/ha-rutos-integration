"""Tests for the RutOS data coordinator."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.rutos.api import RutOSAPIError, RutOSAuthError
from custom_components.rutos.const import DEFAULT_SCAN_INTERVAL
from custom_components.rutos.coordinator import RutOSData, RutOSDataUpdateCoordinator


async def test_async_setup_fetches_device_info(
    hass: HomeAssistant, mock_api: AsyncMock, mock_device_info: dict
):
    """Test _async_setup populates device_info."""
    coordinator = RutOSDataUpdateCoordinator(hass, mock_api)
    coordinator.data = RutOSData()

    await coordinator._async_setup()

    assert coordinator.data.device_info == mock_device_info
    mock_api.get_device_info.assert_awaited_once()


async def test_async_setup_auth_error_raises_update_failed(
    hass: HomeAssistant, mock_api: AsyncMock
):
    """Test API auth error during setup raises UpdateFailed."""
    mock_api.get_device_info.side_effect = RutOSAuthError("bad creds")
    coordinator = RutOSDataUpdateCoordinator(hass, mock_api)

    with pytest.raises(UpdateFailed, match="Authentication failed"):
        await coordinator._async_setup()


async def test_async_setup_api_error_raises_update_failed(
    hass: HomeAssistant, mock_api: AsyncMock
):
    """Test generic API error during setup raises UpdateFailed."""
    mock_api.get_device_info.side_effect = RutOSAPIError("timeout")
    coordinator = RutOSDataUpdateCoordinator(hass, mock_api)

    with pytest.raises(UpdateFailed, match="Failed to get device info"):
        await coordinator._async_setup()


async def test_async_update_data_returns_rutos_data(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_wan_interfaces: list[dict],
):
    """Test _async_update_data returns populated RutOSData."""
    coordinator = RutOSDataUpdateCoordinator(hass, mock_api)
    coordinator.data = RutOSData()

    result = await coordinator._async_update_data()

    assert isinstance(result, RutOSData)
    assert result.wan_interfaces == mock_wan_interfaces
    assert result.internet_available is True
    assert len(result.modems) == 1
    assert result.modems[0]["id"] == "modem1"
    mock_api.get_wan_interfaces.assert_awaited_once()
    mock_api.get_internet_status.assert_awaited_once()
    mock_api.get_modems.assert_awaited_once()


async def test_async_update_data_auth_error_raises_update_failed(
    hass: HomeAssistant, mock_api: AsyncMock
):
    """Test auth error during update raises UpdateFailed."""
    mock_api.get_wan_interfaces.side_effect = RutOSAuthError("expired")
    coordinator = RutOSDataUpdateCoordinator(hass, mock_api)
    coordinator.data = RutOSData()

    with pytest.raises(UpdateFailed, match="Authentication failed"):
        await coordinator._async_update_data()


async def test_async_update_data_api_error_raises_update_failed(
    hass: HomeAssistant, mock_api: AsyncMock
):
    """Test API error during update raises UpdateFailed."""
    mock_api.get_wan_interfaces.side_effect = RutOSAPIError("network down")
    coordinator = RutOSDataUpdateCoordinator(hass, mock_api)
    coordinator.data = RutOSData()

    with pytest.raises(UpdateFailed, match="Error communicating"):
        await coordinator._async_update_data()


async def test_update_interval_is_30s(hass: HomeAssistant, mock_api: AsyncMock):
    """Test coordinator uses the configured scan interval."""
    coordinator = RutOSDataUpdateCoordinator(hass, mock_api)
    assert coordinator.update_interval == timedelta(seconds=DEFAULT_SCAN_INTERVAL)


async def test_async_setup_initializes_data_when_none(
    hass: HomeAssistant, mock_api: AsyncMock, mock_device_info: dict
):
    """Test _async_setup creates RutOSData when self.data is None."""
    coordinator = RutOSDataUpdateCoordinator(hass, mock_api)
    # Leave coordinator.data as None (the default before first refresh)
    assert coordinator.data is None

    await coordinator._async_setup()

    assert coordinator.data is not None
    assert coordinator.data.device_info == mock_device_info


async def test_async_update_data_initializes_data_when_none(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_wan_interfaces: list[dict],
):
    """Test _async_update_data creates RutOSData when self.data is None."""
    coordinator = RutOSDataUpdateCoordinator(hass, mock_api)
    assert coordinator.data is None

    result = await coordinator._async_update_data()

    assert isinstance(result, RutOSData)
    assert result.wan_interfaces == mock_wan_interfaces
    assert len(result.modems) == 1
