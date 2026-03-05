"""Binary sensor platform for the RutOS integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import RutOSDataUpdateCoordinator
from .entity import RutOSEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up RutOS binary sensors based on a config entry."""
    coordinator: RutOSDataUpdateCoordinator = entry.runtime_data
    async_add_entities([RutOSInternetConnectivitySensor(coordinator)])


class RutOSInternetConnectivitySensor(RutOSEntity, BinarySensorEntity):
    """Binary sensor for internet connectivity status."""

    _attr_translation_key = "internet_connectivity"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: RutOSDataUpdateCoordinator) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"{coordinator.data.device_info.get('serial', '')}_internet_connectivity"
        )

    @property
    def is_on(self) -> bool:
        """Return true if internet is available."""
        return self.coordinator.data.internet_available
