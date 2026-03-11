"""The RutOS integration."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import RutOSAPI
from .const import (
    ATTR_INTERFACES,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_UPDATE_HOME_LOCATION,
    CONF_USERNAME,
    DOMAIN,
    SERVICE_SET_FAILOVER_ORDER,
)
from .coordinator import RutOSDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.BUTTON,
]

type RutOSConfigEntry = ConfigEntry[RutOSDataUpdateCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: RutOSConfigEntry) -> bool:
    """Set up RutOS from a config entry."""
    session = async_get_clientsession(hass, verify_ssl=False)
    api = RutOSAPI(
        host=entry.data[CONF_HOST],
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        session=session,
    )

    coordinator = RutOSDataUpdateCoordinator(hass, api)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _register_services(hass)
    _register_home_location_listener(hass, entry, coordinator)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: RutOSConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


def _register_home_location_listener(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: RutOSDataUpdateCoordinator,
) -> None:
    """Register a coordinator listener that updates HA home location from GPS."""

    def _update_home_location() -> None:
        """Update home location when coordinator data changes."""
        if not entry.options.get(CONF_UPDATE_HOME_LOCATION, True):
            return

        gps = coordinator.data.gps_position
        if gps is None:
            return

        lat = gps.get("latitude")
        lon = gps.get("longitude")
        if lat is None or lon is None:
            return

        service_data: dict[str, float] = {
            "latitude": lat,
            "longitude": lon,
        }
        altitude = gps.get("altitude")
        if altitude is not None:
            service_data["elevation"] = altitude

        hass.async_create_task(
            hass.services.async_call("homeassistant", "set_location", service_data)
        )

    entry.async_on_unload(coordinator.async_add_listener(_update_home_location))


def _register_services(hass: HomeAssistant) -> None:
    """Register integration services."""
    if hass.services.has_service(DOMAIN, SERVICE_SET_FAILOVER_ORDER):
        return

    async def handle_set_failover_order(call: ServiceCall) -> None:
        """Handle the set_failover_order service call."""
        interfaces: list[str] = call.data[ATTR_INTERFACES]

        for entry in hass.config_entries.async_entries(DOMAIN):
            coordinator: RutOSDataUpdateCoordinator = entry.runtime_data
            await coordinator.api.set_failover_order(interfaces)
            await coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_FAILOVER_ORDER,
        handle_set_failover_order,
        schema=vol.Schema(
            {
                vol.Required(ATTR_INTERFACES): vol.All([str], vol.Length(min=1)),
            }
        ),
    )
