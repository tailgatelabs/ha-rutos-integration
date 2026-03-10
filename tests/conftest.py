"""Shared fixtures for RutOS integration tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.core import HomeAssistant

from custom_components.rutos.api import RutOSAPI
from custom_components.rutos.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, DOMAIN
from custom_components.rutos.coordinator import RutOSData, RutOSDataUpdateCoordinator

from pytest_homeassistant_custom_component.common import MockConfigEntry


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations for all tests."""
    yield


@pytest.fixture
def mock_device_info() -> dict:
    """Return mock device info."""
    return {
        "name": "RUTX50",
        "serial": "1234567890",
        "mac": "00:1E:42:AA:BB:CC",
        "model": "RUTX50",
        "firmware": "RUTX_R_00.07.06.1",
    }


@pytest.fixture
def mock_wan_interfaces() -> list[dict]:
    """Return mock WAN interface data."""
    return [
        {
            "name": "wan",
            "enabled": True,
            "status": "up",
            "ip_address": "192.168.1.100",
            "proto": "dhcp",
            "uptime": 3600,
            "metric": 10,
            "device": "eth0",
            "l3_device": "eth0",
        },
        {
            "name": "mob1s1a1",
            "enabled": False,
            "status": "down",
            "ip_address": None,
            "proto": "qmi",
            "uptime": 0,
            "metric": 20,
            "device": "wwan0",
            "l3_device": "wwan0",
        },
    ]


@pytest.fixture
def mock_data_limit() -> list[dict]:
    """Return mock data limit status."""
    return [
        {
            "id": "limit1",
            "interface": "mob1s1a1",
            "enabled": True,
            "data_limit": 5_000_000_000,
            "data_used": 2_500_000_000,
            "data_warning_enabled": True,
            "data_warning_limit": 4_000_000_000,
            "due_reset_time": 1735689600,
        },
    ]


@pytest.fixture
def mock_modems() -> list[dict]:
    """Return mock modem list."""
    return [{"id": "modem1"}]


@pytest.fixture
def mock_rutos_data(mock_device_info, mock_wan_interfaces, mock_data_limit, mock_modems) -> RutOSData:
    """Return a populated RutOSData instance."""
    return RutOSData(
        device_info=mock_device_info,
        wan_interfaces=mock_wan_interfaces,
        internet_available=True,
        data_limit=mock_data_limit,
        modems=mock_modems,
    )


@pytest.fixture
def mock_api(mock_device_info, mock_wan_interfaces) -> AsyncMock:
    """Return a fully mocked RutOSAPI."""
    api = AsyncMock(spec=RutOSAPI)
    api.login.return_value = None
    api.get_device_info.return_value = mock_device_info
    api.get_wan_interfaces.return_value = mock_wan_interfaces
    api.get_internet_status.return_value = True
    api.get_data_limit.return_value = [
        {
            "id": "limit1",
            "interface": "mob1s1a1",
            "enabled": True,
            "data_limit": 5_000_000_000,
            "data_used": 2_500_000_000,
            "data_warning_enabled": True,
            "data_warning_limit": 4_000_000_000,
            "due_reset_time": 1735689600,
        },
    ]
    api.clear_data_usage.return_value = None
    api.get_modems.return_value = [{"id": "modem1"}]
    api.reboot_modem.return_value = None
    api.set_interface_enabled.return_value = None
    api.set_failover_order.return_value = None
    return api


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a mock config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="RUTX50",
        data={
            CONF_HOST: "192.168.1.1",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "admin01",
        },
        unique_id="1234567890",
    )


@pytest.fixture
def mock_coordinator(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_rutos_data: RutOSData,
) -> RutOSDataUpdateCoordinator:
    """Return a coordinator with mocked API and pre-populated data."""
    coordinator = RutOSDataUpdateCoordinator(hass, mock_api)
    coordinator.data = mock_rutos_data
    return coordinator
