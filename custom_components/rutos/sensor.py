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
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import RutOSConfigEntry
from .const import CONF_FAILOVER_GROUPS
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
        key="gps_latitude",
        translation_key="gps_latitude",
        native_unit_of_measurement="°",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda gps: gps.get("latitude"),
    ),
    RutOSSensorEntityDescription(
        key="gps_longitude",
        translation_key="gps_longitude",
        native_unit_of_measurement="°",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda gps: gps.get("longitude"),
    ),
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
    RutOSSensorEntityDescription(
        key="gps_accuracy",
        translation_key="gps_accuracy",
        native_unit_of_measurement="m",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda gps: gps.get("accuracy"),
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

MODEM_STATUS_SENSORS: tuple[RutOSSensorEntityDescription, ...] = (
    RutOSSensorEntityDescription(
        key="operator",
        translation_key="modem_operator",
        value_fn=lambda m: m.get("operator"),
    ),
)

MODEM_DUAL_SIM_SENSORS: tuple[RutOSSensorEntityDescription, ...] = (
    RutOSSensorEntityDescription(
        key="active_sim",
        translation_key="modem_active_sim",
        value_fn=lambda m: m.get("active_sim"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RutOSConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up RutOS sensors based on a config entry."""
    coordinator: RutOSDataUpdateCoordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        RutOSSensorEntity(coordinator, description, iface["name"])
        for iface in coordinator.data.wan_interfaces
        for description in INTERFACE_SENSORS
    ]
    groups: dict[str, list[str]] = entry.options.get(CONF_FAILOVER_GROUPS, {})
    iface_labels: dict[str, str] = {}
    for label, ifaces in groups.items():
        for iface in ifaces:
            iface_labels[iface] = label
    entities.append(RutOSActiveWANSensor(coordinator, iface_labels))
    entities.extend(RutOSGPSSensorEntity(coordinator, desc) for desc in GPS_SENSORS)
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
    for modem in coordinator.data.modem_status:
        modem_id = modem.get("id", "")
        entities.extend(
            RutOSModemStatusSensor(coordinator, desc, modem_id)
            for desc in MODEM_STATUS_SENSORS
        )
        if modem.get("dual_sim") or (modem.get("sim_count") or 0) >= 2:
            entities.extend(
                RutOSModemStatusSensor(coordinator, desc, modem_id)
                for desc in MODEM_DUAL_SIM_SENSORS
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
        self._attr_unique_id = f"{coordinator.data.device_info.get('serial', '')}_{interface_name}_{description.key}"
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
        self._attr_unique_id = f"{coordinator.data.device_info.get('serial', '')}_{limit_id}_{description.key}"
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
        self._attr_unique_id = f"{coordinator.data.device_info.get('serial', '')}_{modem_id}_{description.key}"
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


class RutOSModemStatusSensor(RutOSEntity, SensorEntity):
    """Representation of a RutOS modem status sensor."""

    entity_description: RutOSSensorEntityDescription

    def __init__(
        self,
        coordinator: RutOSDataUpdateCoordinator,
        description: RutOSSensorEntityDescription,
        modem_id: str,
    ) -> None:
        """Initialize the modem status sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._modem_id = modem_id
        self._attr_unique_id = f"{coordinator.data.device_info.get('serial', '')}_{modem_id}_{description.key}"
        self._attr_translation_placeholders = {"modem": modem_id}

    def _find_modem(self) -> dict[str, Any] | None:
        """Find modem data by id."""
        for modem in self.coordinator.data.modem_status:
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

    def __init__(
        self,
        coordinator: RutOSDataUpdateCoordinator,
        iface_labels: dict[str, str],
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._iface_labels = iface_labels
        self._attr_unique_id = (
            f"{coordinator.data.device_info.get('serial', '')}_active_wan"
        )

    @property
    def native_value(self) -> str | None:
        """Return the label of the active (first up) WAN interface."""
        for iface in self.coordinator.data.wan_interfaces:
            if iface.get("status") == "up":
                name = iface["name"]
                return self._iface_labels.get(name, name)
        return None
