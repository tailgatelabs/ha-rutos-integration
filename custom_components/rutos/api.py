"""REST API client for Teltonika RutOS devices (Vuci API v1.13+)."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import aiohttp

from .const import API_PATH, SESSION_REFRESH_MARGIN

_LOGGER = logging.getLogger(__name__)


class RutOSAPIError(Exception):
    """Base exception for RutOS API errors."""


class RutOSAuthError(RutOSAPIError):
    """Authentication error."""


class RutOSConnectionError(RutOSAPIError):
    """Connection error."""


class RutOSAPI:
    """Async REST client for Teltonika RutOS Vuci API."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        session: aiohttp.ClientSession,
    ) -> None:
        """Initialize the API client."""
        self._host = host
        self._username = username
        self._password = password
        self._session = session
        self._base_url = f"https://{host}{API_PATH}"
        self._token: str | None = None
        self._token_expiry: float = 0
        self._lock = asyncio.Lock()

    def _url(self, path: str) -> str:
        """Build a full URL for the given API path."""
        return f"{self._base_url}{path}"

    def _auth_headers(self) -> dict[str, str]:
        """Return headers with Bearer token for authenticated requests."""
        if self._token:
            return {"Authorization": f"Bearer {self._token}"}
        return {}

    async def _request(
        self,
        method: str,
        path: str,
        json_data: dict | None = None,
    ) -> Any:
        """Send an authenticated HTTP request, retrying once on 401."""
        url = self._url(path)
        for attempt in range(2):
            await self._ensure_session()
            headers = self._auth_headers()
            try:
                async with self._session.request(
                    method,
                    url,
                    json=json_data,
                    headers=headers,
                    ssl=False,
                ) as resp:
                    status = resp.status
                    try:
                        data = await resp.json(content_type=None)
                    except (ValueError, aiohttp.ContentTypeError):
                        data = None
            except aiohttp.ClientConnectionError as err:
                raise RutOSConnectionError(
                    f"Cannot connect to {self._host}: {err}"
                ) from err
            except aiohttp.ClientError as err:
                raise RutOSAPIError(f"API request failed: {err}") from err

            # Retry once on 401 with a fresh token
            if status == 401 and attempt == 0:
                _LOGGER.debug("Got 401, re-authenticating")
                self._token = None
                continue

            if status == 401:
                raise RutOSAuthError("Authentication required or token expired")

            if status >= 400:
                raise RutOSAPIError(f"HTTP {status} from {path}")

            if not isinstance(data, dict):
                raise RutOSAPIError(f"Unexpected response format from {path}")

            if not data.get("success", False):
                errors = data.get("errors", [])
                msg = (
                    errors[0].get("error", "Unknown error")
                    if errors
                    else "Request failed"
                )
                if any(e.get("source") == "Authorization" for e in errors):
                    raise RutOSAuthError(msg)
                raise RutOSAPIError(msg)

            return data.get("data", {})

        # Should not be reachable, but satisfy type checker
        raise RutOSAPIError("Request failed after retry")  # pragma: no cover

    async def login(self) -> None:
        """Authenticate and obtain a Bearer token."""
        url = self._url("/login")
        payload = {"username": self._username, "password": self._password}
        try:
            async with self._session.post(
                url,
                json=payload,
                ssl=False,
            ) as resp:
                try:
                    data = await resp.json(content_type=None)
                except (ValueError, aiohttp.ContentTypeError):
                    data = None
        except aiohttp.ClientConnectionError as err:
            raise RutOSConnectionError(
                f"Cannot connect to {self._host}: {err}"
            ) from err
        except aiohttp.ClientError as err:
            raise RutOSAPIError(f"Login request failed: {err}") from err

        if not isinstance(data, dict) or not data.get("success", False):
            errors = data.get("errors", []) if isinstance(data, dict) else []
            msg = errors[0].get("error", "Login failed") if errors else "Login failed"
            raise RutOSAuthError(msg)

        token_data = data.get("data", {})
        token = token_data.get("token")
        if not token:
            raise RutOSAuthError("No token in login response")

        self._token = token
        expires = token_data.get("expires", 300)
        self._token_expiry = time.monotonic() + expires
        _LOGGER.debug("Authenticated to %s (expires in %ds)", self._host, expires)

    async def _ensure_session(self) -> None:
        """Ensure we have a valid token, refreshing if needed."""
        async with self._lock:
            if (
                self._token is None
                or time.monotonic() > self._token_expiry - SESSION_REFRESH_MARGIN
            ):
                await self.login()

    async def get(self, path: str) -> Any:
        """Make an authenticated GET request."""
        return await self._request("GET", path)

    async def put(self, path: str, data: dict[str, Any]) -> Any:
        """Make an authenticated PUT request."""
        return await self._request("PUT", path, json_data=data)

    async def post(self, path: str, data: dict[str, Any] | None = None) -> Any:
        """Make an authenticated POST request."""
        return await self._request("POST", path, json_data=data)

    async def get_device_info(self) -> dict[str, Any]:
        """Fetch device information (model, serial, MAC, firmware)."""
        data = await self.get("/system/device/status")

        info: dict[str, Any] = {}

        mnfinfo = data.get("mnfinfo", {})
        if mnfinfo:
            info["serial"] = mnfinfo.get("serial", "")
            info["mac"] = mnfinfo.get("mac", "")
            info["name"] = mnfinfo.get("name", "")

        static = data.get("static", {})
        if static:
            info["firmware"] = static.get("fw_version", "")
            info["model"] = static.get("device_name", "") or static.get("model", "")
            info["hostname"] = static.get("hostname", "")

        return info

    async def get_wan_interfaces(self) -> list[dict[str, Any]]:
        """Fetch all WAN interface statuses."""
        data = await self.get("/interfaces/status")
        interfaces: list[dict[str, Any]] = []

        if not isinstance(data, list):
            return interfaces

        for iface in data:
            if iface.get("area_type") != "wan":
                continue

            ipv4_addrs = iface.get("ipv4-address", [])
            ip_addr = ipv4_addrs[0].get("address") if ipv4_addrs else None

            interfaces.append(
                {
                    "name": iface.get("id", ""),
                    "enabled": iface.get("is_up", False),
                    "status": "up" if iface.get("is_up") else "down",
                    "ip_address": ip_addr,
                    "proto": iface.get("proto", ""),
                    "uptime": iface.get("uptime", 0),
                    "metric": iface.get("metric", 0),
                    "device": iface.get("device", ""),
                    "l3_device": iface.get("l3_device", ""),
                }
            )

        interfaces.sort(key=lambda x: x.get("metric", 0))
        return interfaces

    async def get_internet_status(self) -> bool:
        """Check if the router has internet connectivity."""
        try:
            data = await self.get("/internet_connection/status")
            ipv4 = str(data.get("ipv4_status", "")).lower()
            return ipv4 in ("connected", "online", "up")
        except RutOSAPIError:
            return False

    async def set_interface_enabled(self, interface: str, enabled: bool) -> None:
        """Enable or disable a network interface."""
        await self.put(
            f"/interfaces/config/{interface}",
            {"data": {"enabled": "1" if enabled else "0"}},
        )

    async def get_data_limit(self) -> list[dict[str, Any]]:
        """Fetch data limit/usage status for all configured limits."""
        try:
            data = await self.get("/data_limit/status")
        except RutOSAPIError:
            return []

        if not isinstance(data, list):
            return []

        limits: list[dict[str, Any]] = []
        for entry in data:
            if not isinstance(entry, dict):
                continue
            limits.append(
                {
                    "id": entry.get("id", ""),
                    "interface": entry.get("interface", ""),
                    "enabled": entry.get("enabled", False),
                    "data_limit": int(entry.get("data_limit", 0)),
                    "data_used": int(entry.get("data_used", 0)),
                    "data_warning_enabled": entry.get("data_warning_enabled", False),
                    "data_warning_limit": int(entry.get("data_warning_limit", 0)),
                    "due_reset_time": entry.get("due_reset_time"),
                }
            )
        return limits

    async def clear_data_usage(self) -> None:
        """Clear/reset data usage counters."""
        await self.post("/data_limit/actions/clear")

    async def reboot_modem(self, modem_id: str) -> None:
        """Reboot a specific modem."""
        await self.post(f"/modems/{modem_id}/actions/reboot")

    async def get_modems(self) -> list[dict[str, Any]]:
        """Fetch list of available modems."""
        try:
            data = await self.get("/modems/signal/status")
        except RutOSAPIError:
            return []

        if not isinstance(data, list):
            return []

        return [
            {"id": modem.get("id", "")}
            for modem in data
            if isinstance(modem, dict) and modem.get("id")
        ]

    async def get_modem_signal(self) -> list[dict[str, Any]]:
        """Fetch signal strength data for all modems."""
        try:
            data = await self.get("/modems/signal/status")
        except RutOSAPIError:
            return []

        if not isinstance(data, list):
            return []

        modems: list[dict[str, Any]] = []
        for modem in data:
            if not isinstance(modem, dict):
                continue
            modem_id = modem.get("id", "")
            modems.append(
                {
                    "id": modem_id,
                    "rssi": modem.get("rssi"),
                    "rsrp": modem.get("rsrp"),
                    "rsrq": modem.get("rsrq"),
                    "sinr": modem.get("sinr"),
                    "network_type": modem.get("network_type"),
                    "band": modem.get("band"),
                    "channel_number": modem.get("channel_number"),
                }
            )
        return modems

    async def get_modem_status(self) -> list[dict[str, Any]]:
        """Fetch operator and roaming status for all modems."""
        try:
            data = await self.get("/modems/status")
        except RutOSAPIError:
            return []

        if not isinstance(data, list):
            return []

        modems: list[dict[str, Any]] = []
        for modem in data:
            if not isinstance(modem, dict):
                continue
            modem_id = modem.get("id", "")
            operator_state = str(modem.get("operator_state", ""))
            modems.append(
                {
                    "id": modem_id,
                    "operator": modem.get("operator"),
                    "roaming": "roaming" in operator_state.lower(),
                }
            )
        return modems

    async def set_failover_order(self, interfaces: list[str]) -> None:
        """Set the failover order by updating mwan3 member metrics."""
        members = [
            {"id": f"{iface_id}_member_mwan", "metric": str(idx + 1)}
            for idx, iface_id in enumerate(interfaces)
        ]
        await self.put("/failover/members/config", {"data": members})

    async def get_failover_members(self) -> list[dict[str, Any]]:
        """Fetch mwan3 failover member configs (priority metrics)."""
        data = await self.get("/failover/members/config")
        if not isinstance(data, list):
            return []
        return [m for m in data if m.get("id", "").endswith("_member_mwan")]

    async def get_gps_position(self) -> dict[str, Any] | None:
        """Fetch GPS position data (lat, lon, speed, altitude, etc.)."""
        try:
            data = await self.get("/gps/position/status")
        except RutOSAPIError:
            return None

        if not isinstance(data, dict):
            return None

        # Only return data if we have a valid fix
        if not data.get("latitude") and not data.get("longitude"):
            return None

        return {
            "latitude": data.get("latitude"),
            "longitude": data.get("longitude"),
            "accuracy": data.get("accuracy"),
            "altitude": data.get("altitude"),
            "speed": data.get("speed"),
            "angle": data.get("angle"),
            "satellites": data.get("satellites"),
            "fix_status": data.get("fix_status"),
        }
