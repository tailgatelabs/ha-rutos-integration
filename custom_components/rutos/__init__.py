"""The RutOS integration."""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # HA 2026.10+ types its schema APIs against probatio and aliases
    # ``voluptuous`` to it at runtime; older HA still ships real voluptuous.
    import probatio as vol
else:
    import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_USERNAME,
    Platform,
)
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import RutOSAPI
from .const import (
    ATTR_INTERFACES,
    CONF_UPDATE_HOME_LOCATION,
    DOMAIN,
    ISSUE_HOME_ZONE_OVERRIDDEN,
    SERVICE_SET_FAILOVER_ORDER,
)
from .coordinator import RutOSDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

HOME_ZONE_ENTITY_ID = "zone.home"

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.BUTTON,
    Platform.SELECT,
    Platform.NOTIFY,
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

    # Remove services and the home-zone repair when last config entry is
    # unloaded; a remaining entry re-raises the repair on its next update.
    if unload_ok and not hass.config_entries.async_loaded_entries(DOMAIN):
        hass.services.async_remove(DOMAIN, SERVICE_SET_FAILOVER_ORDER)
        ir.async_delete_issue(hass, DOMAIN, ISSUE_HOME_ZONE_OVERRIDDEN)

    return unload_ok


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

        # The router's ubus /gps/position/status endpoint returns numeric
        # fields as strings (e.g. "44.817068", "156.4"), so coerce to float
        # before handing them to homeassistant.set_location.
        try:
            lat = float(gps["latitude"])
            lon = float(gps["longitude"])
        except (KeyError, TypeError, ValueError):
            return

        altitude_raw = gps.get("altitude")
        altitude: float | None
        try:
            altitude = float(altitude_raw) if altitude_raw is not None else None
        except (TypeError, ValueError):
            altitude = None

        hass.async_create_task(_async_apply_home_location(hass, lat, lon, altitude))

    entry.async_on_unload(coordinator.async_add_listener(_update_home_location))


async def _async_apply_home_location(
    hass: HomeAssistant,
    lat: float,
    lon: float,
    altitude: float | None,
) -> None:
    """Push GPS coordinates to hass.config via homeassistant.set_location."""
    # Check before moving Home: by now the built-in zone.home has caught up
    # with the previous set_location, so a mismatch means it is an override.
    _async_check_home_zone_override(hass)

    service_data: dict[str, float | int] = {"latitude": lat, "longitude": lon}
    if altitude is not None:
        # homeassistant.set_location's schema requires elevation to be an int.
        service_data["elevation"] = round(altitude)

    await hass.services.async_call("homeassistant", "set_location", service_data)


@callback
def _async_check_home_zone_override(hass: HomeAssistant) -> None:
    """Raise a repair issue if zone.home does not follow the core location.

    The built-in zone.home tracks hass.config. A stored or YAML zone named
    "Home" replaces it and is not moved by set_location, so the user has to
    remove that override for Home to follow the router.
    """
    home_state = hass.states.get(HOME_ZONE_ENTITY_ID)
    if home_state is None:
        return

    zone_lat = home_state.attributes.get(ATTR_LATITUDE)
    zone_lon = home_state.attributes.get(ATTR_LONGITUDE)
    follows_core_config = (
        zone_lat is not None
        and zone_lon is not None
        and math.isclose(zone_lat, hass.config.latitude, abs_tol=1e-6)
        and math.isclose(zone_lon, hass.config.longitude, abs_tol=1e-6)
    )

    if follows_core_config:
        ir.async_delete_issue(hass, DOMAIN, ISSUE_HOME_ZONE_OVERRIDDEN)
        return

    ir.async_create_issue(
        hass,
        DOMAIN,
        ISSUE_HOME_ZONE_OVERRIDDEN,
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key=ISSUE_HOME_ZONE_OVERRIDDEN,
    )


def _register_services(hass: HomeAssistant) -> None:
    """Register integration services."""
    if hass.services.has_service(DOMAIN, SERVICE_SET_FAILOVER_ORDER):
        return

    async def handle_set_failover_order(call: ServiceCall) -> None:
        """Handle the set_failover_order service call."""
        interfaces: list[str] = call.data[ATTR_INTERFACES]

        for entry in hass.config_entries.async_entries(DOMAIN):
            coordinator: RutOSDataUpdateCoordinator = entry.runtime_data
            if coordinator.data.failover_mode == "balance":
                raise ServiceValidationError(
                    "Cannot set failover order: router's active mwan3 policy "
                    "is in load-balance mode. Switch to failover mode in the "
                    "router GUI to use this service."
                )

            iface_to_member: dict[str, str] = {
                m["network_id"]: m["id"]
                for m in coordinator.data.failover_members
                if m.get("network_id") and m.get("id")
            }
            unknown = [i for i in interfaces if i not in iface_to_member]
            if unknown:
                raise ServiceValidationError(
                    f"Cannot set failover order: interface(s) {unknown} are "
                    "not in the active failover policy."
                )

            member_ids = [iface_to_member[i] for i in interfaces]
            await coordinator.api.set_failover_order(member_ids)
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
