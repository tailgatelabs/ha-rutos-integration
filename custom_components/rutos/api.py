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
                    method, url, json=json_data, headers=headers, ssl=False,
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
                url, json=payload, ssl=False,
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
            raise RutOSAPIError(f"Login request failed: {err}") from err

        if not isinstance(data, dict) or not data.get("success", False):
            errors = data.get("errors", []) if isinstance(data, dict) else []
            msg = (
                errors[0].get("error", "Login failed")
                if errors
                else "Login failed"
            )
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
            info["model"] = (
                static.get("device_name", "") or static.get("model", "")
            )
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

            interfaces.append({
                "name": iface.get("id", ""),
                "enabled": iface.get("is_up", False),
                "status": "up" if iface.get("is_up") else "down",
                "ip_address": ip_addr,
                "proto": iface.get("proto", ""),
                "uptime": iface.get("uptime", 0),
                "metric": iface.get("metric", 0),
                "device": iface.get("device", ""),
                "l3_device": iface.get("l3_device", ""),
            })

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

    async def set_interface_enabled(
        self, interface: str, enabled: bool
    ) -> None:
        """Enable or disable a network interface."""
        await self.put(
            f"/interfaces/config/{interface}",
            {"data": {"enabled": "1" if enabled else "0"}},
        )

    async def set_failover_order(self, interfaces: list[str]) -> None:
        """Set the failover order by updating interface metrics."""
        for idx, iface_id in enumerate(interfaces):
            metric = (idx + 1) * 10
            await self.put(
                f"/interfaces/config/{iface_id}",
                {"data": {"metric": str(metric)}},
            )

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
