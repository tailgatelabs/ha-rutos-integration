"""Tests for the RutOS home location update feature."""

from __future__ import annotations

from unittest.mock import AsyncMock, call, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME

from custom_components.rutos.const import (
    CONF_UPDATE_HOME_LOCATION,
    DOMAIN,
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

MOCK_GPS_POSITION = {
    "latitude": 37.7749,
    "longitude": -122.4194,
    "accuracy": 5,
    "altitude": 15.2,
    "speed": 65.3,
    "angle": 180,
    "satellites": 12,
    "fix_status": "3D",
}


def _create_entry(hass: HomeAssistant, options: dict | None = None) -> MockConfigEntry:
    """Create and add a mock config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="RUTX50",
        data={
            CONF_HOST: "192.168.1.1",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "admin01",
        },
        options=options or {},
        unique_id="1234567890",
    )
    entry.add_to_hass(hass)
    return entry


def _mock_api(gps_position=None):
    """Return a mock API instance."""
    api = AsyncMock()
    api.login.return_value = None
    api.get_device_info.return_value = MOCK_DEVICE_INFO
    api.get_wan_interfaces.return_value = MOCK_WAN_INTERFACES
    api.get_internet_status.return_value = True
    api.get_gps_position.return_value = gps_position
    api.get_data_limit.return_value = []
    api.get_modem_signal.return_value = []
    api.get_modems.return_value = []
    api.set_failover_order.return_value = None
    return api


def _set_location_calls(mock_call: AsyncMock) -> list:
    """Extract set_location calls from mock."""
    return [
        c
        for c in mock_call.call_args_list
        if c == call("homeassistant", "set_location")
        or (len(c[0]) >= 2 and c[0][0] == "homeassistant" and c[0][1] == "set_location")
    ]


async def test_gps_updates_home_location(hass: HomeAssistant):
    """Test GPS data updates home location when option is ON (default)."""
    entry = _create_entry(hass)
    api = _mock_api(gps_position=MOCK_GPS_POSITION)

    with (
        patch("custom_components.rutos.RutOSAPI", return_value=api),
        patch(
            "homeassistant.core.ServiceRegistry.async_call",
            new_callable=AsyncMock,
        ) as mock_call,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        assert entry.state is ConfigEntryState.LOADED

        # Trigger a coordinator update to fire the listener
        coordinator: RutOSDataUpdateCoordinator = entry.runtime_data
        await coordinator.async_refresh()
        await hass.async_block_till_done()

        mock_call.assert_any_call(
            "homeassistant",
            "set_location",
            {
                "latitude": 37.7749,
                "longitude": -122.4194,
                "elevation": 15.2,
            },
        )


async def test_option_off_no_location_update(hass: HomeAssistant):
    """Test no location update when option is OFF."""
    entry = _create_entry(hass, options={CONF_UPDATE_HOME_LOCATION: False})
    api = _mock_api(gps_position=MOCK_GPS_POSITION)

    with (
        patch("custom_components.rutos.RutOSAPI", return_value=api),
        patch(
            "homeassistant.core.ServiceRegistry.async_call",
            new_callable=AsyncMock,
        ) as mock_call,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        coordinator: RutOSDataUpdateCoordinator = entry.runtime_data
        await coordinator.async_refresh()
        await hass.async_block_till_done()

        # Should not have called set_location
        location_calls = _set_location_calls(mock_call)
        assert len(location_calls) == 0


async def test_no_gps_data_no_location_update(hass: HomeAssistant):
    """Test no location update when GPS data is None."""
    entry = _create_entry(hass)
    api = _mock_api(gps_position=None)

    with (
        patch("custom_components.rutos.RutOSAPI", return_value=api),
        patch(
            "homeassistant.core.ServiceRegistry.async_call",
            new_callable=AsyncMock,
        ) as mock_call,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        coordinator: RutOSDataUpdateCoordinator = entry.runtime_data
        await coordinator.async_refresh()
        await hass.async_block_till_done()

        location_calls = _set_location_calls(mock_call)
        assert len(location_calls) == 0


async def test_gps_missing_lat_lon_no_update(hass: HomeAssistant):
    """Test no location update when GPS data lacks lat/lon."""
    gps_no_coords = {"accuracy": 5, "altitude": 15.2}
    entry = _create_entry(hass)
    api = _mock_api(gps_position=gps_no_coords)

    with (
        patch("custom_components.rutos.RutOSAPI", return_value=api),
        patch(
            "homeassistant.core.ServiceRegistry.async_call",
            new_callable=AsyncMock,
        ) as mock_call,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        coordinator: RutOSDataUpdateCoordinator = entry.runtime_data
        await coordinator.async_refresh()
        await hass.async_block_till_done()

        location_calls = _set_location_calls(mock_call)
        assert len(location_calls) == 0


async def test_altitude_none_omits_elevation(hass: HomeAssistant):
    """Test elevation is omitted from service call when altitude is None."""
    gps_no_alt = {
        "latitude": 37.7749,
        "longitude": -122.4194,
        "accuracy": 5,
        "altitude": None,
    }
    entry = _create_entry(hass)
    api = _mock_api(gps_position=gps_no_alt)

    with (
        patch("custom_components.rutos.RutOSAPI", return_value=api),
        patch(
            "homeassistant.core.ServiceRegistry.async_call",
            new_callable=AsyncMock,
        ) as mock_call,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        coordinator: RutOSDataUpdateCoordinator = entry.runtime_data
        await coordinator.async_refresh()
        await hass.async_block_till_done()

        mock_call.assert_any_call(
            "homeassistant",
            "set_location",
            {
                "latitude": 37.7749,
                "longitude": -122.4194,
            },
        )
