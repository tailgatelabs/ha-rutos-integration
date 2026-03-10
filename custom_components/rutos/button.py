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
    async_add_entities([
        RutOSModemRebootButton(coordinator, modem["id"])
        for modem in coordinator.data.modems
    ])


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
