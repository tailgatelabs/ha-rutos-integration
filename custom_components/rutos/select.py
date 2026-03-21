"""Select platform for RutOS failover priority."""

from __future__ import annotations

from enum import StrEnum

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import RutOSConfigEntry
from .coordinator import RutOSDataUpdateCoordinator
from .entity import RutOSEntity


class FailoverPreset(StrEnum):
    """Failover priority presets."""

    CELLULAR_FIRST = "cellular_starlink_wifi"
    STARLINK_FIRST = "starlink_cellular_wifi"


# Interface IDs as they appear in mwan3 member config.
FAILOVER_PRESETS: dict[str, list[str]] = {
    FailoverPreset.CELLULAR_FIRST: ["mob1s1a1", "mob1s2a1", "wan1", "wan2"],
    FailoverPreset.STARLINK_FIRST: ["wan1", "mob1s1a1", "mob1s2a1", "wan2"],
}

_CELLULAR_IFACES = set(FAILOVER_PRESETS[FailoverPreset.CELLULAR_FIRST][:2])
_STARLINK_IFACE = FAILOVER_PRESETS[FailoverPreset.STARLINK_FIRST][0]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RutOSConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the failover priority select."""
    async_add_entities([RutOSFailoverSelect(entry.runtime_data)])


class RutOSFailoverSelect(RutOSEntity, SelectEntity):
    """Select entity for WAN failover priority preset."""

    _attr_translation_key = "failover_priority"
    _attr_options = list(FAILOVER_PRESETS.keys())
    _attr_icon = "mdi:swap-vertical"

    def __init__(self, coordinator: RutOSDataUpdateCoordinator) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"{coordinator.data.device_info.get('serial', '')}_failover_priority"
        )

    @property
    def current_option(self) -> str | None:
        """Determine the current failover preset from mwan3 member metrics."""
        members = self.coordinator.data.failover_members
        cellular_metric: int | None = None
        starlink_metric: int | None = None

        for member in members:
            iface = member.get("interface", "")
            metric = int(member.get("metric", 0))
            if iface in _CELLULAR_IFACES:
                if cellular_metric is None or metric < cellular_metric:
                    cellular_metric = metric
            elif iface == _STARLINK_IFACE:
                starlink_metric = metric

        if cellular_metric is not None and starlink_metric is not None:
            if cellular_metric < starlink_metric:
                return FailoverPreset.CELLULAR_FIRST
            return FailoverPreset.STARLINK_FIRST
        return None

    async def async_select_option(self, option: str) -> None:
        """Set the failover order for the selected preset."""
        interfaces = FAILOVER_PRESETS[option]
        await self.coordinator.api.set_failover_order(interfaces)
        await self.coordinator.async_request_refresh()
