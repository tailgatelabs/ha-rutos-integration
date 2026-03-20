"""Base entity for the RutOS integration."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import RutOSDataUpdateCoordinator


class RutOSEntity(CoordinatorEntity[RutOSDataUpdateCoordinator]):
    """Base class for RutOS entities with shared device info."""

    _attr_has_entity_name = True

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        info = self.coordinator.data.device_info
        serial = info.get("serial", "")
        return DeviceInfo(
            identifiers={(DOMAIN, serial)},
            name=info.get("model", "RutOS Device"),
            manufacturer="Teltonika",
            model=info.get("name", ""),
            sw_version=info.get("firmware", ""),
        )

    def _find_interface(self, interface_name: str) -> dict[str, Any] | None:
        """Find a WAN interface by name, or return None."""
        for iface in self.coordinator.data.wan_interfaces:
            if iface["name"] == interface_name:
                return iface
        return None
