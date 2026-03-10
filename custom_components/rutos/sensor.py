"""Sensor platform for the RutOS integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import RutOSDataUpdateCoordinator
from .entity import RutOSEntity


@dataclass(frozen=True, kw_only=True)
class RutOSSensorEntityDescription(SensorEntityDescription):
    """Describe a RutOS sensor entity."""

    value_fn: Callable[[dict[str, Any]], str | int | float | None]


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


GPS_SENSORS: tuple[RutOSSensorEntityDescription, ...] = (
    RutOSSensorEntityDescription(
        key="gps_speed",
        translation_key="gps_speed",
        native_unit_of_measurement="km/h",
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda gps: gps.get("speed"),
    ),
    RutOSSensorEntityDescription(
        key="gps_altitude",
        translation_key="gps_altitude",
        native_unit_of_measurement="m",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda gps: gps.get("altitude"),
    ),
    RutOSSensorEntityDescription(
        key="gps_satellites",
        translation_key="gps_satellites",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda gps: gps.get("satellites"),
    ),
    RutOSSensorEntityDescription(
        key="gps_heading",
        translation_key="gps_heading",
        native_unit_of_measurement="°",
        value_fn=lambda gps: gps.get("angle"),
    ),
    RutOSSensorEntityDescription(
        key="gps_fix_status",
        translation_key="gps_fix_status",
        value_fn=lambda gps: gps.get("fix_status"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up RutOS sensors based on a config entry."""
    coordinator: RutOSDataUpdateCoordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        RutOSSensorEntity(coordinator, description, iface["name"])
        for iface in coordinator.data.wan_interfaces
        for description in INTERFACE_SENSORS
    ]
    entities.append(RutOSActiveWANSensor(coordinator))
    entities.extend(
        RutOSGPSSensorEntity(coordinator, desc) for desc in GPS_SENSORS
    )
    async_add_entities(entities)


class RutOSSensorEntity(RutOSEntity, SensorEntity):
    """Representation of a RutOS WAN interface sensor."""

    entity_description: RutOSSensorEntityDescription

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
    def native_value(self) -> str | int | float | None:
        """Return the sensor value."""
        iface = self._find_interface(self._interface_name)
        if iface is None:
            return None
        return self.entity_description.value_fn(iface)


class RutOSGPSSensorEntity(RutOSEntity, SensorEntity):
    """Representation of a RutOS GPS sensor."""

    entity_description: RutOSSensorEntityDescription

    def __init__(
        self,
        coordinator: RutOSDataUpdateCoordinator,
        description: RutOSSensorEntityDescription,
    ) -> None:
        """Initialize the GPS sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = (
            f"{coordinator.data.device_info.get('serial', '')}_{description.key}"
        )

    @property
    def native_value(self) -> str | int | float | None:
        """Return the sensor value."""
        gps = self.coordinator.data.gps_position
        if gps is None:
            return None
        return self.entity_description.value_fn(gps)


class RutOSActiveWANSensor(RutOSEntity, SensorEntity):
    """Sensor showing the currently active WAN interface."""

    _attr_translation_key = "active_wan"

    def __init__(self, coordinator: RutOSDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"{coordinator.data.device_info.get('serial', '')}_active_wan"
        )

    @property
    def native_value(self) -> str | None:
        """Return the name of the active (first up) WAN interface."""
        for iface in self.coordinator.data.wan_interfaces:
            if iface.get("status") == "up":
                return iface["name"]
        return None
