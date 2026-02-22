"""Switch platform for the RutOS integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import RutOSDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up RutOS switches based on a config entry."""
    coordinator: RutOSDataUpdateCoordinator = entry.runtime_data

    entities: list[RutOSInterfaceSwitch] = []
    for iface in coordinator.data.wan_interfaces:
        entities.append(RutOSInterfaceSwitch(coordinator, iface["name"]))

    async_add_entities(entities)


class RutOSInterfaceSwitch(
    CoordinatorEntity[RutOSDataUpdateCoordinator], SwitchEntity
):
    """Switch to enable/disable a WAN interface."""

    _attr_has_entity_name = True
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
        """Return true if the interface is enabled."""
        for iface in self.coordinator.data.wan_interfaces:
            if iface["name"] == self._interface_name:
                return iface.get("enabled", False)
        return False

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the WAN interface."""
        await self.coordinator.api.set_interface_enabled(self._interface_name, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the WAN interface."""
        await self.coordinator.api.set_interface_enabled(self._interface_name, False)
        await self.coordinator.async_request_refresh()
