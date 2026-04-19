"""The RutOS integration."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.components.zone import DATA_ZONE_STORAGE_COLLECTION
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_USERNAME,
    Platform,
)
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import slugify

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
    """Push GPS coordinates to hass.config and, if needed, the stored zone.home."""
    service_data: dict[str, float | int] = {"latitude": lat, "longitude": lon}
    if altitude is not None:
        # homeassistant.set_location's schema requires elevation to be an int.
        service_data["elevation"] = int(round(altitude))

    await hass.services.async_call("homeassistant", "set_location", service_data)

    home_state = hass.states.get("zone.home")
    if home_state is None or not home_state.attributes.get("editable"):
        return

    # A user-customized zone.home is stored in .storage/core.zones with
    # editable=True. For stored zones HA skips wiring its
    # core_config_updated listener, so the set_location call above updates
    # hass.config but never moves the zone.home entity. Update the stored
    # zone directly through the zone storage collection — this preserves the
    # user's radius, icon, and passive settings while refreshing the
    # coordinates.
    await _async_update_stored_home_zone(hass, lat, lon)


async def _async_update_stored_home_zone(
    hass: HomeAssistant, lat: float, lon: float
) -> None:
    """Update the stored zone.home entry via the zone storage collection."""
    try:
        storage_collection = hass.data.get(DATA_ZONE_STORAGE_COLLECTION)
        if storage_collection is None:
            return
        for item_id, item in storage_collection.data.items():
            if slugify(item.get(CONF_NAME, "")) == "home":
                await storage_collection.async_update_item(
                    item_id,
                    {CONF_LATITUDE: lat, CONF_LONGITUDE: lon},
                )
                return
    except Exception as err:  # noqa: BLE001 - defensive against HA internal API churn
        _LOGGER.warning("Could not update stored zone.home from GPS: %s", err)


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
