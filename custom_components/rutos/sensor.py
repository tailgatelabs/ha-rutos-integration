"""Sensor platform for the RutOS integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import RutOSData, RutOSDataUpdateCoordinator


@dataclass(frozen=True, kw_only=True)
class RutOSSensorEntityDescription(SensorEntityDescription):
    """Describe a RutOS sensor entity."""

    value_fn: Callable[[dict[str, Any]], str | int | None]


INTERFACE_SENSORS: tuple[RutOSSensorEntityDescription, ...] = (
    RutOSSensorEntityDescription(
        key="status",
        translation_key="wan_status",
        value_fn=lambda iface: iface.get("status"),
    ),
    RutOSSensorEntityDescription(
        key="ip_address",
        translation_key="wan_ip_address",
        value_fn=lambda iface: iface.get("ip_address"),
    ),
    RutOSSensorEntityDescription(
        key="proto",
        translation_key="wan_protocol",
        value_fn=lambda iface: iface.get("proto"),
    ),
    RutOSSensorEntityDescription(
        key="uptime",
        translation_key="wan_uptime",
        native_unit_of_measurement="s",
        value_fn=lambda iface: iface.get("uptime"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up RutOS sensors based on a config entry."""
    coordinator: RutOSDataUpdateCoordinator = entry.runtime_data

    entities: list[RutOSSensorEntity | RutOSActiveWANSensor] = []

    for iface in coordinator.data.wan_interfaces:
        iface_name = iface["name"]
        for description in INTERFACE_SENSORS:
            entities.append(
                RutOSSensorEntity(coordinator, description, iface_name)
            )

    entities.append(RutOSActiveWANSensor(coordinator))

    async_add_entities(entities)


class RutOSSensorEntity(CoordinatorEntity[RutOSDataUpdateCoordinator], SensorEntity):
    """Representation of a RutOS WAN interface sensor."""

    entity_description: RutOSSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: RutOSDataUpdateCoordinator,
        description: RutOSSensorEntityDescription,
        interface_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._interface_name = interface_name
        self._attr_unique_id = (
            f"{coordinator.data.device_info.get('serial', '')}_{interface_name}_{description.key}"
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
    def native_value(self) -> str | int | None:
        """Return the sensor value."""
        for iface in self.coordinator.data.wan_interfaces:
            if iface["name"] == self._interface_name:
                return self.entity_description.value_fn(iface)
        return None


class RutOSActiveWANSensor(CoordinatorEntity[RutOSDataUpdateCoordinator], SensorEntity):
    """Sensor showing the currently active WAN interface."""

    _attr_has_entity_name = True
    _attr_translation_key = "active_wan"

    def __init__(self, coordinator: RutOSDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"{coordinator.data.device_info.get('serial', '')}_active_wan"
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
    def native_value(self) -> str | None:
        """Return the name of the active (first up) WAN interface."""
        for iface in self.coordinator.data.wan_interfaces:
            if iface.get("status") == "up":
                return iface["name"]
        return None
