"""The RutOS integration."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import RutOSAPI
from .const import (
    ATTR_INTERFACES,
    CONF_UPDATE_HOME_LOCATION,
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
    Platform.SELECT,
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

    coordinator = RutOSDataUpdateCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _register_services(hass)
    _register_home_location_listener(hass, entry, coordinator)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    return True


async def _async_options_updated(hass: HomeAssistant, entry: RutOSConfigEntry) -> None:
    """Reload the integration when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: RutOSConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Remove services when last config entry is unloaded
    if unload_ok and not hass.config_entries.async_loaded_entries(DOMAIN):
        hass.services.async_remove(DOMAIN, SERVICE_SET_FAILOVER_ORDER)

    return unload_ok


def _register_home_location_listener(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: RutOSDataUpdateCoordinator,
) -> None:
    """Register a coordinator listener that updates HA home location from GPS."""

    warned_editable = False
    issue_id = f"editable_home_zone_{entry.entry_id}"

    def _update_home_location() -> None:
        """Update home location when coordinator data changes."""
        nonlocal warned_editable

        if not entry.options.get(CONF_UPDATE_HOME_LOCATION, True):
            return

        gps = coordinator.data.gps_position
        if gps is None:
            return

        lat = gps.get("latitude")
        lon = gps.get("longitude")
        if lat is None or lon is None:
            return

        # If zone.home has been customized in Settings > Areas & Zones, it is
        # stored in .storage/core.zones with editable=True. In that case HA's
        # zone component does not wire its core_config_updated listener, so
        # homeassistant.set_location updates hass.config but never propagates
        # to the zone.home entity. Warn the user (log + repair) and skip the
        # no-op service call until they remove the custom home zone.
        home_state = hass.states.get("zone.home")
        if home_state is not None and home_state.attributes.get("editable"):
            if not warned_editable:
                _LOGGER.warning(
                    "zone.home is user-customized (editable=True) and cannot be "
                    "updated from GPS. Remove the custom home zone in Settings > "
                    "Areas & Zones so Home Assistant auto-generates a default one, "
                    "then GPS updates will resume."
                )
                ir.async_create_issue(
                    hass,
                    DOMAIN,
                    issue_id,
                    is_fixable=False,
                    severity=ir.IssueSeverity.WARNING,
                    translation_key="editable_home_zone",
                )
                warned_editable = True
            return

        if warned_editable:
            ir.async_delete_issue(hass, DOMAIN, issue_id)
        warned_editable = False

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
    entry.async_on_unload(lambda: ir.async_delete_issue(hass, DOMAIN, issue_id))


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
