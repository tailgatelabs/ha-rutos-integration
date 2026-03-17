"""Binary sensor platform for the RutOS integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
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
    """Set up RutOS binary sensors based on a config entry."""
    coordinator: RutOSDataUpdateCoordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = [RutOSInternetConnectivitySensor(coordinator)]
    for modem in coordinator.data.modem_status:
        modem_id = modem.get("id", "")
        entities.append(RutOSModemRoamingSensor(coordinator, modem_id))
    async_add_entities(entities)


class RutOSInternetConnectivitySensor(RutOSEntity, BinarySensorEntity):
    """Binary sensor for internet connectivity status."""

    _attr_translation_key = "internet_connectivity"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: RutOSDataUpdateCoordinator) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"{coordinator.data.device_info.get('serial', '')}_internet_connectivity"
        )

    @property
    def is_on(self) -> bool:
        """Return true if internet is available."""
        return self.coordinator.data.internet_available


class RutOSModemRoamingSensor(RutOSEntity, BinarySensorEntity):
    """Binary sensor for modem roaming status."""

    _attr_translation_key = "modem_roaming"

    def __init__(self, coordinator: RutOSDataUpdateCoordinator, modem_id: str) -> None:
        """Initialize the roaming binary sensor."""
        super().__init__(coordinator)
        self._modem_id = modem_id
        self._attr_unique_id = (
            f"{coordinator.data.device_info.get('serial', '')}_{modem_id}_roaming"
        )
        self._attr_translation_placeholders = {"modem": modem_id}

    @property
    def is_on(self) -> bool | None:
        """Return true if modem is roaming."""
        for modem in self.coordinator.data.modem_status:
            if modem.get("id") == self._modem_id:
                return modem.get("roaming")
        return None
