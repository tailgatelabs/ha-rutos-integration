"""Button platform for the RutOS integration."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import RutOSConfigEntry
from .coordinator import RutOSDataUpdateCoordinator
from .entity import RutOSEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RutOSConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up RutOS buttons based on a config entry."""
    coordinator: RutOSDataUpdateCoordinator = entry.runtime_data
    entities: list[ButtonEntity] = []
    if coordinator.data.data_limit:
        entities.append(RutOSClearDataUsageButton(coordinator))
    entities.extend(
        RutOSModemRebootButton(coordinator, modem["id"])
        for modem in coordinator.data.modems
    )
    async_add_entities(entities)


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


class RutOSModemRebootButton(RutOSEntity, ButtonEntity):
    """Button to reboot a specific modem."""

    _attr_translation_key = "modem_reboot"

    def __init__(
        self,
        coordinator: RutOSDataUpdateCoordinator,
        modem_id: str,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._modem_id = modem_id
        self._attr_unique_id = (
            f"{coordinator.data.device_info.get('serial', '')}_{modem_id}_reboot"
        )
        self._attr_translation_placeholders = {"modem": modem_id}

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.coordinator.api.reboot_modem(self._modem_id)
        await self.coordinator.async_request_refresh()
