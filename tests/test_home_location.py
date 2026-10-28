"""Tests for the RutOS home location update feature."""

from __future__ import annotations

from unittest.mock import AsyncMock, call, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.rutos.const import (
    CONF_UPDATE_HOME_LOCATION,
    DOMAIN,
    ISSUE_HOME_ZONE_OVERRIDDEN,
)
from custom_components.rutos.coordinator import RutOSDataUpdateCoordinator
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

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
                "elevation": 15,
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


def _set_home_zone(hass: HomeAssistant, lat: float, lon: float) -> None:
    """Set a zone.home state at the given coordinates."""
    hass.states.async_set(
        "zone.home",
        "0",
        {"latitude": lat, "longitude": lon, "radius": 150, "friendly_name": "Home"},
    )


async def _setup_and_refresh(
    hass: HomeAssistant, entry: MockConfigEntry, home_zone: tuple[float, float]
) -> None:
    """Set up the entry, place zone.home, and run one coordinator update."""
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    _set_home_zone(hass, *home_zone)

    coordinator: RutOSDataUpdateCoordinator = entry.runtime_data
    await coordinator.async_refresh()
    await hass.async_block_till_done()


async def test_overridden_home_zone_raises_repair(
    hass: HomeAssistant, issue_registry: ir.IssueRegistry
):
    """A zone.home that does not follow hass.config raises a repair issue."""
    entry = _create_entry(hass)
    api = _mock_api(gps_position=MOCK_GPS_POSITION)

    with (
        patch("custom_components.rutos.RutOSAPI", return_value=api),
        patch(
            "homeassistant.core.ServiceRegistry.async_call",
            new_callable=AsyncMock,
        ) as mock_call,
    ):
        await _setup_and_refresh(hass, entry, (40.7128, -74.0060))

        # set_location is still the only thing used to move Home.
        mock_call.assert_any_call(
            "homeassistant",
            "set_location",
            {
                "latitude": 37.7749,
                "longitude": -122.4194,
                "elevation": 15,
            },
        )

        issue = issue_registry.async_get_issue(DOMAIN, ISSUE_HOME_ZONE_OVERRIDDEN)
        assert issue is not None
        assert issue.severity is ir.IssueSeverity.WARNING
        assert not issue.is_fixable


async def test_builtin_home_zone_no_repair(
    hass: HomeAssistant, issue_registry: ir.IssueRegistry
):
    """A zone.home that follows hass.config does not raise a repair issue."""
    entry = _create_entry(hass)
    api = _mock_api(gps_position=MOCK_GPS_POSITION)

    with (
        patch("custom_components.rutos.RutOSAPI", return_value=api),
        patch(
            "homeassistant.core.ServiceRegistry.async_call",
            new_callable=AsyncMock,
        ),
    ):
        await _setup_and_refresh(
            hass, entry, (hass.config.latitude, hass.config.longitude)
        )

        assert (
            issue_registry.async_get_issue(DOMAIN, ISSUE_HOME_ZONE_OVERRIDDEN) is None
        )


async def test_repair_cleared_when_override_removed(
    hass: HomeAssistant, issue_registry: ir.IssueRegistry
):
    """The repair issue clears once zone.home follows hass.config again."""
    entry = _create_entry(hass)
    api = _mock_api(gps_position=MOCK_GPS_POSITION)

    with (
        patch("custom_components.rutos.RutOSAPI", return_value=api),
        patch(
            "homeassistant.core.ServiceRegistry.async_call",
            new_callable=AsyncMock,
        ),
    ):
        await _setup_and_refresh(hass, entry, (40.7128, -74.0060))
        assert issue_registry.async_get_issue(DOMAIN, ISSUE_HOME_ZONE_OVERRIDDEN)

        _set_home_zone(hass, hass.config.latitude, hass.config.longitude)
        coordinator: RutOSDataUpdateCoordinator = entry.runtime_data
        await coordinator.async_refresh()
        await hass.async_block_till_done()

        assert (
            issue_registry.async_get_issue(DOMAIN, ISSUE_HOME_ZONE_OVERRIDDEN) is None
        )


async def test_repair_cleared_on_unload(
    hass: HomeAssistant, issue_registry: ir.IssueRegistry
):
    """Unloading the last entry removes the repair issue."""
    entry = _create_entry(hass)
    api = _mock_api(gps_position=MOCK_GPS_POSITION)

    with (
        patch("custom_components.rutos.RutOSAPI", return_value=api),
        patch(
            "homeassistant.core.ServiceRegistry.async_call",
            new_callable=AsyncMock,
        ),
    ):
        await _setup_and_refresh(hass, entry, (40.7128, -74.0060))
        assert issue_registry.async_get_issue(DOMAIN, ISSUE_HOME_ZONE_OVERRIDDEN)

        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

        assert (
            issue_registry.async_get_issue(DOMAIN, ISSUE_HOME_ZONE_OVERRIDDEN) is None
        )


async def test_option_off_no_repair(
    hass: HomeAssistant, issue_registry: ir.IssueRegistry
):
    """No repair issue is raised when home location updates are off."""
    entry = _create_entry(hass, options={CONF_UPDATE_HOME_LOCATION: False})
    api = _mock_api(gps_position=MOCK_GPS_POSITION)

    with (
        patch("custom_components.rutos.RutOSAPI", return_value=api),
        patch(
            "homeassistant.core.ServiceRegistry.async_call",
            new_callable=AsyncMock,
        ),
    ):
        await _setup_and_refresh(hass, entry, (40.7128, -74.0060))

        assert (
            issue_registry.async_get_issue(DOMAIN, ISSUE_HOME_ZONE_OVERRIDDEN) is None
        )


async def test_float_altitude_rounded_to_int_elevation(hass: HomeAssistant):
    """elevation must be int; set_location's schema rejects floats."""
    gps_float_alt = {
        "latitude": 37.7749,
        "longitude": -122.4194,
        "accuracy": 5,
        "altitude": 156.7,
    }
    entry = _create_entry(hass)
    api = _mock_api(gps_position=gps_float_alt)

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
        assert location_calls, "set_location was not called"
        service_data = location_calls[-1][0][2]
        assert service_data["elevation"] == 157
        assert isinstance(service_data["elevation"], int)


async def test_string_valued_router_gps_is_coerced(hass: HomeAssistant):
    """The RutOS ubus API returns GPS fields as strings; coerce before set_location."""
    gps_strings = {
        "latitude": "37.7749",
        "longitude": "-122.4194",
        "accuracy": "5",
        "altitude": "156.4",
    }
    entry = _create_entry(hass)
    api = _mock_api(gps_position=gps_strings)

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
        assert location_calls, "set_location was not called"
        service_data = location_calls[-1][0][2]
        assert service_data["latitude"] == 37.7749
        assert isinstance(service_data["latitude"], float)
        assert service_data["longitude"] == -122.4194
        assert isinstance(service_data["longitude"], float)
        assert service_data["elevation"] == 156
        assert isinstance(service_data["elevation"], int)


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
