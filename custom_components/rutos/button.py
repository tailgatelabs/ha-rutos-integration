"""Button platform for the RutOS integration."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
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
    """Set up RutOS buttons based on a config entry."""
    coordinator: RutOSDataUpdateCoordinator = entry.runtime_data
    if coordinator.data.data_limit:
        async_add_entities([RutOSClearDataUsageButton(coordinator)])


class RutOSClearDataUsageButton(RutOSEntity, ButtonEntity):
    """Button to clear/reset data usage counters."""

    _attr_translation_key = "clear_data_usage"

    def __init__(self, coordinator: RutOSDataUpdateCoordinator) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"{coordinator.data.device_info.get('serial', '')}_clear_data_usage"
        )

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.coordinator.api.clear_data_usage()
        await self.coordinator.async_request_refresh()
