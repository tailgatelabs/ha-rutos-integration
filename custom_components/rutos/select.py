"""Select platform for RutOS failover priority."""

from __future__ import annotations

import itertools

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import RutOSConfigEntry
from .const import CONF_FAILOVER_GROUPS
from .coordinator import RutOSDataUpdateCoordinator
from .entity import RutOSEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RutOSConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the failover priority select."""
    groups: dict[str, list[str]] = entry.options.get(CONF_FAILOVER_GROUPS, {})
    if len(groups) < 2:  # noqa: PLR2004
        return
    if entry.runtime_data.data.failover_mode == "balance":
        return
    async_add_entities([RutOSFailoverSelect(entry.runtime_data, groups)])


class RutOSFailoverSelect(RutOSEntity, SelectEntity):
    """Select entity for WAN failover priority preset."""

    _attr_translation_key = "failover_priority"
    _attr_icon = "mdi:swap-vertical"

    def __init__(
        self,
        coordinator: RutOSDataUpdateCoordinator,
        groups: dict[str, list[str]],
    ) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator)
        self._groups = groups
        self._configured_ifaces: set[str] = set()
        for ifaces in groups.values():
            self._configured_ifaces.update(ifaces)
        self._attr_unique_id = (
            f"{coordinator.data.device_info.get('serial', '')}_failover_priority"
        )

    def _active_groups(self) -> list[str]:
        """Return group labels that have at least one active interface."""
        active_ifaces = {
            iface["name"]
            for iface in self.coordinator.data.wan_interfaces
            if iface.get("status") == "up"
        }
        return [
            label
            for label, ifaces in self._groups.items()
            if any(i in active_ifaces for i in ifaces)
        ]

    @property
    def options(self) -> list[str]:
        """Return all permutations of currently active group labels."""
        active = self._active_groups()
        if len(active) < 2:  # noqa: PLR2004
            return []
        return [", ".join(perm) for perm in itertools.permutations(active)]

    @property
    def available(self) -> bool:
        """Return False if fewer than 2 groups are active."""
        return len(self._active_groups()) >= 2  # noqa: PLR2004

    @property
    def current_option(self) -> str | None:
        """Determine the current option from mwan3 member metrics."""
        members = self.coordinator.data.failover_members
        iface_metrics = {
            m.get("interface", ""): int(m.get("metric", 0)) for m in members
        }

        active = self._active_groups()
        group_min_metrics: dict[str, int] = {}
        for label in active:
            ifaces = self._groups[label]
            metrics = [iface_metrics[i] for i in ifaces if i in iface_metrics]
            if metrics:
                group_min_metrics[label] = min(metrics)

        if len(group_min_metrics) != len(active):
            return None

        sorted_groups = sorted(group_min_metrics, key=lambda g: group_min_metrics[g])
        current = ", ".join(sorted_groups)
        return current if current in self.options else None

    async def async_select_option(self, option: str) -> None:
        """Set the failover order for the selected permutation."""
        group_order = [g.strip() for g in option.split(", ")]
        iface_to_member: dict[str, str] = {
            m["interface"]: m["id"]
            for m in self.coordinator.data.failover_members
            if m.get("interface") and m.get("id")
        }
        member_ids: list[str] = []
        for label in group_order:
            for iface in self._groups[label]:
                member_id = iface_to_member.get(iface)
                if member_id:
                    member_ids.append(member_id)
        await self.coordinator.api.set_failover_order(member_ids)
        await self.coordinator.async_request_refresh()
