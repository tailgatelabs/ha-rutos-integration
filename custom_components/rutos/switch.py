"""Switch platform for the RutOS integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
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
    """Set up RutOS switches based on a config entry."""
    coordinator: RutOSDataUpdateCoordinator = entry.runtime_data
    async_add_entities(
        [
            RutOSInterfaceSwitch(coordinator, iface["name"])
            for iface in coordinator.data.wan_interfaces
        ]
    )


class RutOSInterfaceSwitch(RutOSEntity, SwitchEntity):
    """Switch to enable/disable a WAN interface."""

    _attr_translation_key = "wan_enabled"

    def __init__(
        self,
        coordinator: RutOSDataUpdateCoordinator,
        interface_name: str,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._interface_name = interface_name
        self._attr_unique_id = (
            f"{coordinator.data.device_info.get('serial', '')}_{interface_name}_enabled"
        )
        self._attr_translation_placeholders = {"interface": interface_name}

    @property
    def is_on(self) -> bool:
        """Return true if the interface is enabled."""
        iface = self._find_interface(self._interface_name)
        if iface is None:
            return False
        return iface.get("enabled", False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the WAN interface."""
        await self.coordinator.api.set_interface_enabled(self._interface_name, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the WAN interface."""
        await self.coordinator.api.set_interface_enabled(self._interface_name, False)
        await self.coordinator.async_request_refresh()
