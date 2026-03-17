"""DataUpdateCoordinator for the RutOS integration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import RutOSAPI, RutOSAPIError, RutOSAuthError
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

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


class RutOSDataUpdateCoordinator(DataUpdateCoordinator[RutOSData]):
    """Coordinator to manage fetching RutOS data."""

    def __init__(self, hass: HomeAssistant, api: RutOSAPI) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.api = api

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
        """Fetch WAN interface data and internet status in parallel."""
        if self.data is None:
            self.data = RutOSData()

        try:
            (
                wan_interfaces,
                internet_available,
                gps_position,
                data_limit,
                modem_signal,
                modem_status,
                modems,
            ) = await asyncio.gather(
                self.api.get_wan_interfaces(),
                self.api.get_internet_status(),
                self.api.get_gps_position(),
                self.api.get_data_limit(),
                self.api.get_modem_signal(),
                self.api.get_modem_status(),
                self.api.get_modems(),
            )
        except RutOSAuthError as err:
            raise UpdateFailed(f"Authentication failed: {err}") from err
        except RutOSAPIError as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err

        self.data.wan_interfaces = wan_interfaces
        self.data.internet_available = internet_available
        self.data.gps_position = gps_position
        self.data.data_limit = data_limit
        self.data.modem_signal = modem_signal
        self.data.modem_status = modem_status
        self.data.modems = modems
        return self.data
