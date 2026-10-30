"""DataUpdateCoordinator for the RutOS integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import RutOSAPI, RutOSAPIError, RutOSAuthError, RutOSConnectionError
from .const import CONNECTION_BACKOFF_INTERVALS, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass
class RutOSData:
    """Data class holding coordinator state."""

    device_info: dict[str, Any] = field(default_factory=dict)
    wan_interfaces: list[dict[str, Any]] = field(default_factory=list)
    internet_available: bool = False
    gps_position: dict[str, Any] | None = None
    data_limit: list[dict[str, Any]] = field(default_factory=list)
    modem_signal: list[dict[str, Any]] = field(default_factory=list)
    modem_status: list[dict[str, Any]] = field(default_factory=list)
    modems: list[dict[str, Any]] = field(default_factory=list)
    failover_chain: dict[str, Any] = field(
        default_factory=lambda: {"policy_id": None, "mode": "failover", "members": []}
    )
    failover_status: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def failover_members(self) -> list[dict[str, Any]]:
        """Return the active policy's failover members in policy order."""
        return self.failover_chain.get("members", [])

    @property
    def failover_mode(self) -> str:
        """Return ``"failover"`` or ``"balance"`` for the active policy."""
        return self.failover_chain.get("mode", "failover")


class RutOSDataUpdateCoordinator(DataUpdateCoordinator[RutOSData]):
    """Coordinator to manage fetching RutOS data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: RutOSAPI) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.api = api
        self._connection_failures = 0

    async def _async_setup(self) -> None:
        """Fetch static device info on first refresh."""
        try:
            device_info = await self.api.get_device_info()
        except RutOSAuthError as err:
            raise UpdateFailed(f"Authentication failed: {err}") from err
        except RutOSAPIError as err:
            raise UpdateFailed(f"Failed to get device info: {err}") from err

        if self.data is None:
            self.data = RutOSData()
        self.data.device_info = device_info

    async def _async_update_data(self) -> RutOSData:
        """Fetch router state one endpoint at a time.

        A connection failure ends the poll, so a struggling router isn't sent
        the remaining requests.
        """
        if self.data is None:
            self.data = RutOSData()

        try:
            wan_interfaces = await self.api.get_wan_interfaces()
            internet_available = await self.api.get_internet_status()
            gps_position = await self.api.get_gps_position()
            data_limit = await self.api.get_data_limit()
            modem_data = await self.api.get_modem_data()
            failover_chain = await self.api.get_active_failover_chain()
            failover_status = await self.api.get_failover_status()
        except RutOSConnectionError as err:
            self._back_off()
            raise UpdateFailed(f"Error communicating with API: {err}") from err
        except RutOSAuthError as err:
            raise UpdateFailed(f"Authentication failed: {err}") from err
        except RutOSAPIError as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err

        self._connection_failures = 0
        self.update_interval = timedelta(seconds=DEFAULT_SCAN_INTERVAL)

        self.data.wan_interfaces = wan_interfaces
        self.data.internet_available = internet_available
        self.data.gps_position = gps_position
        self.data.data_limit = data_limit
        self.data.modem_signal = modem_data.signal
        self.data.modem_status = modem_data.status
        self.data.modems = modem_data.modems
        self.data.failover_chain = failover_chain
        self.data.failover_status = failover_status
        return self.data

    def _back_off(self) -> None:
        """Poll less often while the router is failing to respond."""
        step = min(self._connection_failures, len(CONNECTION_BACKOFF_INTERVALS) - 1)
        self.update_interval = timedelta(seconds=CONNECTION_BACKOFF_INTERVALS[step])
        self._connection_failures += 1
