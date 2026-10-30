"""REST API client for Teltonika RutOS devices (Vuci API v1.13+)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, NamedTuple

import aiohttp

from .const import API_PATH, MAX_CONCURRENT_REQUESTS, REQUEST_TIMEOUT

_LOGGER = logging.getLogger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)


def _extract_ip(iface: dict[str, Any]) -> str | None:
    """Extract a WAN IPv4 address in CIDR notation from an interface entry.

    Different proto types report addresses differently: wired/DHCP interfaces
    populate ``ipv4-address: [{address, mask}]``, while mobile interfaces on
    some firmwares only populate ``ipaddrs: ["a.b.c.d/32"]``. CIDR is kept so
    carrier-assigned subnet size is preserved.
    """
    ipv4_addrs = iface.get("ipv4-address") or []
    if ipv4_addrs and isinstance(ipv4_addrs[0], dict):
        addr = ipv4_addrs[0].get("address")
        mask = ipv4_addrs[0].get("mask")
        if addr:
            return f"{addr}/{mask}" if mask is not None else addr
    ipaddrs = iface.get("ipaddrs") or []
    if ipaddrs and isinstance(ipaddrs[0], str) and ipaddrs[0]:
        return ipaddrs[0]
    return None


def _normalize_carriers(ca_signal: Any) -> list[dict[str, Any]]:
    """Normalize the /modems/status ``ca_signal`` array into a carriers list.

    The Vuci API returns one entry per aggregated carrier (LTE CA and/or 5G
    NSA/NR-CA). Each entry carries its own band/bandwidth/RSRP/RSRQ/SINR and a
    ``primary`` flag identifying the PCell.
    """
    out: list[dict[str, Any]] = []
    if not isinstance(ca_signal, list):
        return out
    for c in ca_signal:
        if not isinstance(c, dict):
            continue
        out.append(
            {
                "band": c.get("band"),
                "primary": bool(c.get("primary")),
                "bandwidth": c.get("bandwidth"),
                "rsrp": c.get("rsrp"),
                "rsrq": c.get("rsrq"),
                "sinr": c.get("sinr"),
                "pcid": c.get("pcid"),
                "frequency": c.get("frequency"),
            }
        )
    return out


def _resolve_active_policy_id(
    rules: list[dict[str, Any]], policies: list[dict[str, Any]]
) -> str | None:
    """Pick the policy that drives default-bound traffic.

    Prefers the rule named ``default_rule`` (Teltonika's catch-all), falls
    back to the first rule, then to the only policy if exactly one exists.
    """
    if rules:
        default_rule = next((r for r in rules if r.get("name") == "default_rule"), None)
        rule = default_rule or rules[0]
        policy_id = rule.get("use_policy")
        if isinstance(policy_id, str) and policy_id:
            return policy_id
    if len(policies) == 1:
        policy_id = policies[0].get("id")
        if isinstance(policy_id, str) and policy_id:
            return policy_id
    return None


def _detect_failover_mode(members: list[dict[str, Any]]) -> str:
    """Return ``"balance"`` when members share the same metric, else ``"failover"``.

    A load-balance policy assigns equal metrics to all members and uses
    ``weight`` for traffic share; failover policies use distinct metrics for
    priority. With fewer than 2 members the distinction is meaningless;
    default to ``"failover"`` so the integration shows whatever single
    interface exists.
    """
    if len(members) < 2:
        return "failover"
    metrics = {m.get("metric") for m in members}
    return "balance" if len(metrics) == 1 else "failover"


def _parse_modem_ids(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract modem identities; /modems/signal/status uses "modem" for the id."""
    modems: list[dict[str, Any]] = []
    for entry in entries:
        modem_id = entry.get("id") or entry.get("modem")
        if modem_id:
            modems.append({"id": modem_id})
    return modems


def _parse_modem_signal(modem: dict[str, Any]) -> dict[str, Any]:
    """Normalize signal metrics from a /modems/status entry."""
    carriers = _normalize_carriers(modem.get("ca_signal"))
    primary = next((c for c in carriers if c["primary"]), None)
    if primary is not None:
        band = primary["band"]
        channel = primary["frequency"]
    else:
        band = modem.get("band")
        channel = carriers[0]["frequency"] if carriers else None
    return {
        "id": modem.get("id") or modem.get("modem") or "",
        "rssi": modem.get("rssi"),
        "rsrp": modem.get("rsrp"),
        "rsrq": modem.get("rsrq"),
        "sinr": modem.get("sinr"),
        "signal_quality": modem.get("signal_quality"),
        "network_type": modem.get("conntype") or modem.get("ntype"),
        "band": band,
        "channel_number": channel,
        "carriers": carriers,
    }


def _parse_modem_signal_samples(entry: dict[str, Any]) -> dict[str, Any]:
    """Normalize a /modems/signal/status entry using its latest sample."""
    samples = entry.get("signal")
    if isinstance(samples, list) and samples and isinstance(samples[-1], dict):
        src = samples[-1]
    else:
        src = entry
    return {
        "id": entry.get("id") or entry.get("modem") or "",
        "rssi": src.get("rssi"),
        "rsrp": src.get("rsrp"),
        "rsrq": src.get("rsrq"),
        "sinr": src.get("sinr"),
        "signal_quality": src.get("signal_quality"),
        "network_type": src.get("network_type"),
        "band": src.get("band"),
        "channel_number": src.get("channel_number"),
        "carriers": [],
    }


def _parse_modem_status(modem: dict[str, Any]) -> dict[str, Any]:
    """Extract operator and roaming state from a /modems/status entry."""
    operator_state = str(modem.get("operator_state", ""))
    return {
        "id": modem.get("id", ""),
        "operator": modem.get("operator"),
        "roaming": "roaming" in operator_state.lower(),
        "active_sim": modem.get("active_sim"),
        "dual_sim": modem.get("dual_sim"),
        "sim_count": modem.get("sim_count"),
    }


class ModemData(NamedTuple):
    """Modem data parsed from a single /modems/status response."""

    signal: list[dict[str, Any]]
    status: list[dict[str, Any]]
    modems: list[dict[str, Any]]


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
        self._lock = asyncio.Lock()
        self._request_slots = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

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
        json_data: dict[str, Any] | None = None,
    ) -> Any:
        """Send an authenticated HTTP request, retrying once on 401."""
        url = self._url(path)
        for attempt in range(2):
            await self._ensure_session()
            try:
                async with self._request_slots:
                    # Read the token only once it's our turn: it may have been
                    # replaced while this request was queued.
                    sent_token = self._token
                    async with self._session.request(
                        method,
                        url,
                        json=json_data,
                        headers=self._auth_headers(),
                        ssl=False,
                        timeout=_TIMEOUT,
                    ) as resp:
                        status = resp.status
                        try:
                            data = await resp.json(content_type=None)
                        except (ValueError, aiohttp.ContentTypeError):
                            data = None
            except TimeoutError as err:
                raise RutOSConnectionError(
                    f"Timed out after {REQUEST_TIMEOUT}s requesting {path} "
                    f"from {self._host}"
                ) from err
            except aiohttp.ClientConnectionError as err:
                raise RutOSConnectionError(
                    f"Cannot connect to {self._host}: {err}"
                ) from err
            except aiohttp.ClientError as err:
                raise RutOSAPIError(f"API request failed: {err}") from err

            # Retry once on 401 with a fresh token
            if status == 401 and attempt == 0:
                _LOGGER.debug("Got 401, re-authenticating")
                if self._token == sent_token:
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
            async with (
                self._request_slots,
                self._session.post(
                    url,
                    json=payload,
                    ssl=False,
                    timeout=_TIMEOUT,
                ) as resp,
            ):
                try:
                    data = await resp.json(content_type=None)
                except (ValueError, aiohttp.ContentTypeError):
                    data = None
        except TimeoutError as err:
            raise RutOSConnectionError(
                f"Timed out after {REQUEST_TIMEOUT}s logging in to {self._host}"
            ) from err
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
        _LOGGER.debug("Authenticated to %s", self._host)

    async def _ensure_session(self) -> None:
        """Log in if we have no token.

        The router resets a token's timer on every request, so polling keeps it
        alive indefinitely. Tokens are only replaced after the router rejects
        one, because each login costs the router far more than a typical read.
        """
        async with self._lock:
            if self._token is None:
                await self.login()

    async def get(self, path: str) -> Any:
        """Make an authenticated GET request."""
        return await self._request("GET", path)

    async def _get_optional(self, path: str) -> Any:
        """GET an endpoint the router may not offer, returning None if rejected.

        Connection failures still propagate. They mean the router is struggling
        rather than lacking a feature, so the poll must stop instead of carrying
        on with more requests.
        """
        try:
            return await self.get(path)
        except RutOSConnectionError:
            raise
        except RutOSAPIError as err:
            _LOGGER.debug("%s unavailable: %s", path, err)
            return None

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

        # /interfaces/status reports live link state (is_up); the UCI "enabled"
        # flag the router GUI and switch should track lives in /interfaces/config.
        # Fall back to is_up if the config endpoint is unavailable.
        config_by_id: dict[str, dict[str, Any]] = {}
        configs = await self._get_optional("/interfaces/config")
        if isinstance(configs, list):
            for cfg in configs:
                if isinstance(cfg, dict) and cfg.get("area_type") == "wan":
                    cfg_id = cfg.get("id")
                    if isinstance(cfg_id, str):
                        config_by_id[cfg_id] = cfg

        for iface in data:
            if iface.get("area_type") != "wan":
                continue

            ip_addr = _extract_ip(iface)
            iface_id = iface.get("id", "")
            cfg = config_by_id.get(iface_id)
            if cfg is not None:
                enabled = str(cfg.get("enabled", "0")) == "1"
            else:
                enabled = bool(iface.get("is_up", False))

            interfaces.append(
                {
                    "name": iface_id,
                    "label": iface.get("name") or iface_id,
                    "enabled": enabled,
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
        data = await self._get_optional("/internet_connection/status")
        if not isinstance(data, dict):
            return False
        ipv4 = str(data.get("ipv4_status", "")).lower()
        return ipv4 in ("connected", "online", "up")

    async def set_interface_enabled(self, interface: str, enabled: bool) -> None:
        """Enable or disable a network interface."""
        await self.put(
            f"/interfaces/config/{interface}",
            {"data": {"enabled": "1" if enabled else "0"}},
        )

    async def get_data_limit(self) -> list[dict[str, Any]]:
        """Fetch data limit/usage status for all configured limits."""
        data = await self._get_optional("/data_limit/status")
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

    async def switch_sim(self, modem_id: str) -> None:
        """Switch to the next SIM card on a specific modem."""
        await self.post(f"/modems/{modem_id}/actions/switch_sim")

    async def send_sms(self, number: str, message: str, modem: str) -> dict[str, Any]:
        """Send an SMS message via the specified modem."""
        return await self.post(
            "/messages/actions/send",
            {"data": {"number": number, "message": message, "modem": modem}},
        )

    async def get_modem_data(self) -> ModemData:
        """Fetch signal, operator, and identity data for all modems.

        /modems/status carries all three. /modems/signal/status, where metrics
        live in a nested 'signal' array of historical samples, is only tried when
        the router rejects /modems/status; an empty list just means no modems.
        """
        status = await self._get_optional("/modems/status")
        if isinstance(status, list):
            modems = [m for m in status if isinstance(m, dict)]
            return ModemData(
                signal=[_parse_modem_signal(m) for m in modems],
                status=[_parse_modem_status(m) for m in modems],
                modems=_parse_modem_ids(modems),
            )

        signal = await self._get_optional("/modems/signal/status")
        if not isinstance(signal, list):
            return ModemData(signal=[], status=[], modems=[])

        entries = [e for e in signal if isinstance(e, dict)]
        return ModemData(
            signal=[_parse_modem_signal_samples(e) for e in entries],
            status=[],
            modems=_parse_modem_ids(entries),
        )

    async def set_failover_order(self, member_ids: list[str]) -> None:
        """Set the failover order by updating mwan3 member metrics.

        Caller must pass the active policy's member IDs (resolved via
        ``get_active_failover_chain``) in the desired priority order.
        """
        members = [
            {"id": member_id, "metric": str(idx + 1)}
            for idx, member_id in enumerate(member_ids)
        ]
        await self.put("/failover/members/config", {"data": members})

    async def get_failover_policies(self) -> list[dict[str, Any]]:
        """Fetch mwan3 policy configs."""
        data = await self.get("/failover/policies/config")
        if not isinstance(data, list):
            return []
        return data

    async def get_failover_rules(self) -> list[dict[str, Any]]:
        """Fetch mwan3 rule configs (which traffic uses which policy)."""
        data = await self.get("/failover/rules/config")
        if not isinstance(data, list):
            return []
        return data

    async def get_failover_interfaces(self) -> list[dict[str, Any]]:
        """Fetch mwan3 interface configs (the bridge to network interfaces).

        Each entry has ``id`` (matches network interface UCI id) and ``name``
        (matches the display name used in ``mwan_member.interface``).
        """
        data = await self.get("/failover/interfaces/config")
        if not isinstance(data, list):
            return []
        return data

    async def get_active_failover_chain(self) -> dict[str, Any]:
        """Resolve the active failover chain.

        Reads policies, rules, members, and the mwan_interface bridge table,
        picks the active policy from the default rule (or first rule, or the
        only policy), and returns its members in policy-defined order. Each
        returned member has a ``network_id`` field set to the UCI id of the
        underlying network interface — derived by mapping
        ``mwan_member.interface`` (a display name) through
        ``mwan_interface.name`` to ``mwan_interface.id``. ``network_id`` is
        ``None`` when the bridge entry is missing.

        Returns a dict with keys:
            policy_id: str | None - active policy id, None if not resolvable
            mode: "failover" | "balance" - balance when all members share metric
            members: list[dict] - member dicts in policy order with
                ``network_id`` attached.
        """
        policies = await self.get_failover_policies()
        rules = await self.get_failover_rules()
        all_members = await self._get_all_failover_members()
        fo_interfaces = await self.get_failover_interfaces()

        network_id_by_mwan_name = {
            fi.get("name"): fi.get("id")
            for fi in fo_interfaces
            if isinstance(fi.get("name"), str) and isinstance(fi.get("id"), str)
        }

        policy_id = _resolve_active_policy_id(rules, policies)
        if policy_id is None:
            return {"policy_id": None, "mode": "failover", "members": []}

        policy = next((p for p in policies if p.get("id") == policy_id), None)
        if policy is None:
            return {"policy_id": None, "mode": "failover", "members": []}

        use_member = policy.get("use_member") or []
        members_by_id = {m.get("id"): m for m in all_members}
        ordered_members: list[dict[str, Any]] = []
        for member_id in use_member:
            member = members_by_id.get(member_id)
            if member is not None:
                resolved = dict(member)
                resolved["network_id"] = network_id_by_mwan_name.get(
                    member.get("interface")
                )
                ordered_members.append(resolved)

        mode = _detect_failover_mode(ordered_members)
        return {"policy_id": policy_id, "mode": mode, "members": ordered_members}

    async def get_failover_status(self) -> dict[str, dict[str, Any]]:
        """Fetch mwan3 tracking status keyed by network interface id.

        Each value carries mwan3's view of the interface (``status`` is one of
        ``online``, ``offline``, ``standby``, ``notracking``, ``disabled``) plus
        the raw link flag ``up``. Unlike ``/interfaces/status``, this reflects
        whether the interface actually passes traffic, not just link state.
        Returns ``{}`` when the endpoint is unavailable.
        """
        data = await self._get_optional("/failover/status")
        if not isinstance(data, dict):
            return {}
        return {k: v for k, v in data.items() if isinstance(v, dict)}

    async def _get_all_failover_members(self) -> list[dict[str, Any]]:
        """Fetch all mwan3 member configs (no naming-based filter)."""
        data = await self.get("/failover/members/config")
        if not isinstance(data, list):
            return []
        return data

    async def get_gps_position(self) -> dict[str, Any] | None:
        """Fetch GPS position data (lat, lon, speed, altitude, etc.)."""
        data = await self._get_optional("/gps/position/status")
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
