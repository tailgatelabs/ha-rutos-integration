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


DATA_LIMIT_SENSORS: tuple[RutOSSensorEntityDescription, ...] = (
    RutOSSensorEntityDescription(
        key="data_used",
        translation_key="data_used",
        native_unit_of_measurement="B",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda d: d.get("data_used"),
    ),
    RutOSSensorEntityDescription(
        key="data_limit",
        translation_key="data_limit",
        native_unit_of_measurement="B",
        device_class=SensorDeviceClass.DATA_SIZE,
        value_fn=lambda d: d.get("data_limit"),
    ),
    RutOSSensorEntityDescription(
        key="data_usage_percent",
        translation_key="data_usage_percent",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (
            round(d["data_used"] / d["data_limit"] * 100, 1)
            if d.get("data_limit")
            else None
        ),
    ),
)


MODEM_SIGNAL_SENSORS: tuple[RutOSSensorEntityDescription, ...] = (
    RutOSSensorEntityDescription(
        key="rssi",
        translation_key="modem_rssi",
        native_unit_of_measurement="dBm",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda m: m.get("rssi"),
    ),
    RutOSSensorEntityDescription(
        key="rsrp",
        translation_key="modem_rsrp",
        native_unit_of_measurement="dBm",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda m: m.get("rsrp"),
    ),
    RutOSSensorEntityDescription(
        key="rsrq",
        translation_key="modem_rsrq",
        native_unit_of_measurement="dB",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda m: m.get("rsrq"),
    ),
    RutOSSensorEntityDescription(
        key="sinr",
        translation_key="modem_sinr",
        native_unit_of_measurement="dB",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda m: m.get("sinr"),
    ),
    RutOSSensorEntityDescription(
        key="network_type",
        translation_key="modem_network_type",
        value_fn=lambda m: m.get("network_type"),
    ),
    RutOSSensorEntityDescription(
        key="band",
        translation_key="modem_band",
        value_fn=lambda m: m.get("band"),
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
    for limit in coordinator.data.data_limit:
        limit_id = limit.get("id", "")
        if not limit.get("enabled"):
            continue
        entities.extend(
            RutOSDataLimitSensor(coordinator, desc, limit_id)
            for desc in DATA_LIMIT_SENSORS
        )
    for modem in coordinator.data.modem_signal:
        modem_id = modem.get("id", "")
        entities.extend(
            RutOSModemSignalSensor(coordinator, desc, modem_id)
            for desc in MODEM_SIGNAL_SENSORS
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


class RutOSDataLimitSensor(RutOSEntity, SensorEntity):
    """Representation of a RutOS data limit/usage sensor."""

    entity_description: RutOSSensorEntityDescription

    def __init__(
        self,
        coordinator: RutOSDataUpdateCoordinator,
        description: RutOSSensorEntityDescription,
        limit_id: str,
    ) -> None:
        """Initialize the data limit sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._limit_id = limit_id
        self._attr_unique_id = (
            f"{coordinator.data.device_info.get('serial', '')}_{limit_id}_{description.key}"
        )
        self._attr_translation_placeholders = {"limit": limit_id}

    def _find_limit(self) -> dict[str, Any] | None:
        """Find data limit entry by id."""
        for limit in self.coordinator.data.data_limit:
            if limit.get("id") == self._limit_id:
                return limit
        return None

    @property
    def native_value(self) -> str | int | float | None:
        """Return the sensor value."""
        limit = self._find_limit()
        if limit is None:
            return None
        return self.entity_description.value_fn(limit)


class RutOSModemSignalSensor(RutOSEntity, SensorEntity):
    """Representation of a RutOS modem signal sensor."""

    entity_description: RutOSSensorEntityDescription

    def __init__(
        self,
        coordinator: RutOSDataUpdateCoordinator,
        description: RutOSSensorEntityDescription,
        modem_id: str,
    ) -> None:
        """Initialize the modem signal sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._modem_id = modem_id
        self._attr_unique_id = (
            f"{coordinator.data.device_info.get('serial', '')}_{modem_id}_{description.key}"
        )
        self._attr_translation_placeholders = {"modem": modem_id}

    def _find_modem(self) -> dict[str, Any] | None:
        """Find modem data by id."""
        for modem in self.coordinator.data.modem_signal:
            if modem.get("id") == self._modem_id:
                return modem
        return None

    @property
    def native_value(self) -> str | int | float | None:
        """Return the sensor value."""
        modem = self._find_modem()
        if modem is None:
            return None
        return self.entity_description.value_fn(modem)


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
