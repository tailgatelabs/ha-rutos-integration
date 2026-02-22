"""Binary sensor platform for the RutOS integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import RutOSDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up RutOS binary sensors based on a config entry."""
    coordinator: RutOSDataUpdateCoordinator = entry.runtime_data
    async_add_entities([RutOSInternetConnectivitySensor(coordinator)])


class RutOSInternetConnectivitySensor(
    CoordinatorEntity[RutOSDataUpdateCoordinator], BinarySensorEntity
):
    """Binary sensor for internet connectivity status."""

    _attr_has_entity_name = True
    _attr_translation_key = "internet_connectivity"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: RutOSDataUpdateCoordinator) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"{coordinator.data.device_info.get('serial', '')}_internet_connectivity"
        )

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device info."""
        info = self.coordinator.data.device_info
        serial = info.get("serial", "")
        return {
            "identifiers": {(DOMAIN, serial)},
            "name": info.get("model", "RutOS Device"),
            "manufacturer": "Teltonika",
            "model": info.get("name", ""),
            "sw_version": info.get("firmware", ""),
        }

    @property
    def is_on(self) -> bool:
        """Return true if internet is available."""
        return self.coordinator.data.internet_available
