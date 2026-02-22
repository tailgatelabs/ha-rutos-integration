"""JSON-RPC 2.0 API client for Teltonika RutOS devices."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import aiohttp

from .const import (
    API_JSONRPC_VERSION,
    API_PATH,
    SESSION_EXPIRY,
    SESSION_REFRESH_MARGIN,
)

_LOGGER = logging.getLogger(__name__)

JSONRPC_SESSION_EXPIRED = 6


class RutOSAPIError(Exception):
    """Base exception for RutOS API errors."""


class RutOSAuthError(RutOSAPIError):
    """Authentication error."""


class RutOSConnectionError(RutOSAPIError):
    """Connection error."""


class RutOSAPI:
    """Async JSON-RPC 2.0 client for RutOS ubus API."""

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
        self._url = f"https://{host}{API_PATH}"
        self._ubus_session: str | None = None
        self._session_expiry: float = 0
        self._rpc_id = 0
        self._lock = asyncio.Lock()

    def _next_id(self) -> int:
        """Return the next JSON-RPC request ID."""
        self._rpc_id += 1
        return self._rpc_id

    async def _request(self, method: str, params: list[Any]) -> Any:
        """Send a JSON-RPC 2.0 request."""
        payload = {
            "jsonrpc": API_JSONRPC_VERSION,
            "id": self._next_id(),
            "method": method,
            "params": params,
        }
        try:
            async with self._session.post(
                self._url, json=payload, ssl=False
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
        except aiohttp.ClientConnectionError as err:
            raise RutOSConnectionError(
                f"Cannot connect to {self._host}: {err}"
            ) from err
        except aiohttp.ClientError as err:
            raise RutOSAPIError(f"API request failed: {err}") from err

        if "error" in data:
            raise RutOSAPIError(f"JSON-RPC error: {data['error']}")

        return data.get("result")

    async def login(self) -> None:
        """Authenticate and obtain a ubus session."""
        result = await self._request(
            "call",
            [
                "00000000000000000000000000000000",
                "session",
                "login",
                {"username": self._username, "password": self._password},
            ],
        )
        # Result is [status_code, {ubus_rpc_session: "...", ...}]
        if not isinstance(result, list) or len(result) < 2:
            raise RutOSAuthError("Unexpected login response format")

        status_code = result[0]
        if status_code != 0:
            raise RutOSAuthError(f"Login failed with status code {status_code}")

        session_data = result[1]
        ubus_session = session_data.get("ubus_rpc_session")
        if not ubus_session:
            raise RutOSAuthError("No session ID in login response")

        self._ubus_session = ubus_session
        self._session_expiry = time.monotonic() + SESSION_EXPIRY
        _LOGGER.debug("Authenticated to %s", self._host)

    async def _ensure_session(self) -> str:
        """Ensure we have a valid session, refreshing if needed."""
        async with self._lock:
            if (
                self._ubus_session is None
                or time.monotonic() > self._session_expiry - SESSION_REFRESH_MARGIN
            ):
                await self.login()
            return self._ubus_session  # type: ignore[return-value]

    async def call(
        self, service: str, method: str, params: dict[str, Any] | None = None
    ) -> Any:
        """Make an authenticated ubus call."""
        session_id = await self._ensure_session()
        result = await self._request(
            "call",
            [session_id, service, method, params or {}],
        )

        # Handle expired session (code 6) — retry once
        if isinstance(result, list) and len(result) >= 1 and result[0] == JSONRPC_SESSION_EXPIRED:
            _LOGGER.debug("Session expired, re-authenticating")
            self._ubus_session = None
            session_id = await self._ensure_session()
            result = await self._request(
                "call",
                [session_id, service, method, params or {}],
            )

        if isinstance(result, list) and len(result) >= 1 and result[0] != 0:
            raise RutOSAPIError(
                f"ubus call {service}.{method} failed with code {result[0]}"
            )

        # Return the data payload (second element) if present
        if isinstance(result, list) and len(result) >= 2:
            return result[1]
        return result

    async def get_device_info(self) -> dict[str, Any]:
        """Fetch device information (model, serial, MAC, firmware)."""
        info: dict[str, Any] = {}

        # Try mnf_info first (requires file.exec ACL permission)
        try:
            mnf_info = await self.call("file", "exec", {
                "command": "mnf_info",
                "params": ["--name", "--serial", "--mac", "--batch"],
            })
            # mnf_info returns stdout with key=value lines
            stdout = mnf_info.get("stdout", "") if isinstance(mnf_info, dict) else ""
            for line in stdout.strip().split("\n"):
                if "=" in line:
                    key, _, value = line.partition("=")
                    info[key.strip()] = value.strip()
        except RutOSAPIError:
            _LOGGER.debug("Could not fetch mnf_info (file.exec may not be permitted)")

        # Also get firmware version and model from system.board
        try:
            board = await self.call("system", "board")
            if isinstance(board, dict):
                info["firmware"] = board.get("release", {}).get("description", "")
                info["model"] = board.get("model", info.get("name", ""))
        except RutOSAPIError:
            _LOGGER.debug("Could not fetch board info")

        return info

    async def get_wan_interfaces(self) -> list[dict[str, Any]]:
        """Fetch all WAN interface statuses."""
        dump = await self.call("network.interface", "dump")
        interfaces: list[dict[str, Any]] = []

        if not isinstance(dump, dict):
            return interfaces

        for iface in dump.get("interface", []):
            # Filter to WAN-type interfaces (those with a gateway or
            # explicitly tagged as WAN in their config)
            is_wan = (
                iface.get("route")
                or iface.get("interface", "").startswith("wan")
                or iface.get("proto") in ("dhcp", "pppoe", "qmi", "mbim", "ncm", "wwan")
            )
            if not is_wan:
                continue

            ipv4_addrs = iface.get("ipv4-address", [])
            ip_addr = ipv4_addrs[0].get("address") if ipv4_addrs else None

            interfaces.append({
                "name": iface.get("interface", ""),
                "enabled": iface.get("up", False),
                "status": "up" if iface.get("up") else "down",
                "ip_address": ip_addr,
                "proto": iface.get("proto", ""),
                "uptime": iface.get("uptime", 0),
                "metric": iface.get("metric", 0),
                "device": iface.get("device", ""),
                "l3_device": iface.get("l3_device", ""),
            })

        # Sort by metric (failover priority)
        interfaces.sort(key=lambda x: x.get("metric", 0))
        return interfaces

    async def get_internet_status(self) -> bool:
        """Check if the router has internet connectivity."""
        try:
            result = await self.call("network.interface", "dump")
            if not isinstance(result, dict):
                return False
            # Check if any WAN interface has a default route and is up
            for iface in result.get("interface", []):
                if iface.get("up") and iface.get("route"):
                    for route in iface["route"]:
                        if route.get("target") == "0.0.0.0" and route.get("mask") == 0:
                            return True
            return False
        except RutOSAPIError:
            return False

    async def set_interface_enabled(
        self, interface: str, enabled: bool
    ) -> None:
        """Enable or disable a WAN interface."""
        if enabled:
            await self.call("network.interface", "up", {"interface": interface})
        else:
            await self.call("network.interface", "down", {"interface": interface})

    async def set_failover_order(self, interfaces: list[str]) -> None:
        """Set the failover order by updating interface metrics via UCI."""
        for idx, iface_name in enumerate(interfaces):
            metric = (idx + 1) * 10
            await self.call("uci", "set", {
                "config": "network",
                "section": iface_name,
                "values": {"metric": str(metric)},
            })

        await self.call("uci", "commit", {"config": "network"})
        # Reload network to apply changes
        await self.call("file", "exec", {
            "command": "/etc/init.d/network",
            "params": ["reload"],
        })
