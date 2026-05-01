"""Tests for the RutOS integration setup and services."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from custom_components.rutos.api import RutOSAuthError
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME

from custom_components.rutos.const import (
    ATTR_INTERFACES,
    DOMAIN,
    SERVICE_SET_FAILOVER_ORDER,
)
from custom_components.rutos.coordinator import RutOSDataUpdateCoordinator

from pytest_homeassistant_custom_component.common import MockConfigEntry


MOCK_DEVICE_INFO = {
    "name": "RUTX50",
    "serial": "1234567890",
    "mac": "00:1E:42:AA:BB:CC",
    "model": "RUTX50",
    "firmware": "RUTX_R_00.07.06.1",
}

MOCK_WAN_INTERFACES = [
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
]


def _create_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Create and add a mock config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="RUTX50",
        data={
            CONF_HOST: "192.168.1.1",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "admin01",
        },
        unique_id="1234567890",
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def mock_api_instance():
    """Return a mock API that returns device info and WAN data."""
    api = AsyncMock()
    api.login.return_value = None
    api.get_device_info.return_value = MOCK_DEVICE_INFO
    api.get_wan_interfaces.return_value = MOCK_WAN_INTERFACES
    api.get_internet_status.return_value = True
    api.get_gps_position.return_value = None
    api.get_data_limit.return_value = []
    api.get_modem_signal.return_value = []
    api.get_modem_status.return_value = []
    api.get_modems.return_value = []
    api.get_active_failover_chain.return_value = {
        "policy_id": "mwan_default",
        "mode": "failover",
        "members": [
            {"id": "wan_member_mwan", "interface": "wan", "metric": "1"},
            {"id": "mob1s1a1_member_mwan", "interface": "mob1s1a1", "metric": "2"},
        ],
    }
    api.set_failover_order.return_value = None
    return api


async def test_async_setup_entry_success(
    hass: HomeAssistant, mock_api_instance: AsyncMock
):
    """Test successful setup stores coordinator and forwards platforms."""
    entry = _create_entry(hass)

    with patch("custom_components.rutos.RutOSAPI", return_value=mock_api_instance):
        result = await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert result is True
    assert entry.state is ConfigEntryState.LOADED
    assert isinstance(entry.runtime_data, RutOSDataUpdateCoordinator)
    assert entry.runtime_data.data.device_info == MOCK_DEVICE_INFO


async def test_async_setup_entry_auth_failure(
    hass: HomeAssistant, mock_api_instance: AsyncMock
):
    """Test auth error during first refresh is handled."""
    mock_api_instance.get_device_info.side_effect = RutOSAuthError("bad creds")
    entry = _create_entry(hass)

    with patch("custom_components.rutos.RutOSAPI", return_value=mock_api_instance):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_async_unload_entry(hass: HomeAssistant, mock_api_instance: AsyncMock):
    """Test unloading an entry returns True."""
    entry = _create_entry(hass)

    with patch("custom_components.rutos.RutOSAPI", return_value=mock_api_instance):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        result = await hass.config_entries.async_unload(entry.entry_id)

    assert result is True
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_set_failover_order_service_registered(
    hass: HomeAssistant, mock_api_instance: AsyncMock
):
    """Test the set_failover_order service exists after setup."""
    entry = _create_entry(hass)

    with patch("custom_components.rutos.RutOSAPI", return_value=mock_api_instance):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert hass.services.has_service(DOMAIN, SERVICE_SET_FAILOVER_ORDER)


async def test_set_failover_order_service_call(
    hass: HomeAssistant, mock_api_instance: AsyncMock
):
    """Test service call resolves interfaces to member IDs, invokes API, refreshes."""
    entry = _create_entry(hass)

    with patch("custom_components.rutos.RutOSAPI", return_value=mock_api_instance):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_FAILOVER_ORDER,
        {ATTR_INTERFACES: ["wan", "mob1s1a1"]},
        blocking=True,
    )

    # Service translates interface IDs to member IDs from the active policy.
    mock_api_instance.set_failover_order.assert_awaited_once_with(
        ["wan_member_mwan", "mob1s1a1_member_mwan"]
    )


async def test_set_failover_order_service_balance_mode_errors(
    hass: HomeAssistant, mock_api_instance: AsyncMock
):
    """Service raises ServiceValidationError when active policy is balance."""
    from homeassistant.exceptions import ServiceValidationError

    mock_api_instance.get_active_failover_chain.return_value = {
        "policy_id": "balance_default",
        "mode": "balance",
        "members": [
            {"id": "wan_member_balance", "interface": "wan", "metric": "1"},
            {"id": "mob1s1a1_member_balance", "interface": "mob1s1a1",
             "metric": "1"},
        ],
    }
    entry = _create_entry(hass)

    with patch("custom_components.rutos.RutOSAPI", return_value=mock_api_instance):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    with pytest.raises(ServiceValidationError, match="load-balance"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_FAILOVER_ORDER,
            {ATTR_INTERFACES: ["wan", "mob1s1a1"]},
            blocking=True,
        )

    mock_api_instance.set_failover_order.assert_not_awaited()


async def test_register_services_idempotent(
    hass: HomeAssistant, mock_api_instance: AsyncMock
):
    """Test that _register_services is safe to call twice."""
    from custom_components.rutos import _register_services

    entry = _create_entry(hass)

    with patch("custom_components.rutos.RutOSAPI", return_value=mock_api_instance):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert hass.services.has_service(DOMAIN, SERVICE_SET_FAILOVER_ORDER)

    # Calling _register_services again should not raise or duplicate the service
    _register_services(hass)

    assert hass.services.has_service(DOMAIN, SERVICE_SET_FAILOVER_ORDER)
