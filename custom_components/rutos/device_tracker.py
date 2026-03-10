"""Device tracker platform for the RutOS integration."""

from __future__ import annotations

from homeassistant.components.device_tracker.const import SourceType
from homeassistant.components.device_tracker.config_entry import TrackerEntity
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
    """Set up RutOS device tracker based on a config entry."""
    coordinator: RutOSDataUpdateCoordinator = entry.runtime_data
    async_add_entities([RutOSDeviceTracker(coordinator)])


class RutOSDeviceTracker(RutOSEntity, TrackerEntity):
    """Device tracker using GPS position from the RutOS router."""

    _attr_translation_key = "gps_location"

    def __init__(self, coordinator: RutOSDataUpdateCoordinator) -> None:
        """Initialize the device tracker."""
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"{coordinator.data.device_info.get('serial', '')}_gps_location"
        )

    @property
    def source_type(self) -> SourceType:
        """Return the source type."""
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        """Return latitude value of the device."""
        gps = self.coordinator.data.gps_position
        if gps is None:
            return None
        return gps.get("latitude")

    @property
    def longitude(self) -> float | None:
        """Return longitude value of the device."""
        gps = self.coordinator.data.gps_position
        if gps is None:
            return None
        return gps.get("longitude")

    @property
    def location_accuracy(self) -> int:
        """Return the location accuracy of the device."""
        gps = self.coordinator.data.gps_position
        if gps is None:
            return 0
        return gps.get("accuracy", 0)
