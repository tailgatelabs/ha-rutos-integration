"""Tests for the RutOS REST API client."""

from __future__ import annotations

import asyncio
from unittest.mock import Mock, patch

import aiohttp
import pytest
from aioresponses import CallbackResult, aioresponses
from aioresponses import core as aioresponses_core
from yarl import URL

from custom_components.rutos.api import (
    RutOSAPI,
    RutOSAPIError,
    RutOSAuthError,
    RutOSConnectionError,
)
from custom_components.rutos.const import (
    API_PATH,
    MAX_CONCURRENT_REQUESTS,
    REQUEST_TIMEOUT,
)

TEST_HOST = "192.168.1.1"
TEST_BASE_URL = f"https://{TEST_HOST}{API_PATH}"
TEST_USER = "admin"
TEST_PASS = "admin01"
TEST_TOKEN = "test-token-abc123"


class _ClientResponse(aiohttp.ClientResponse):
    """ClientResponse that tolerates aioresponses omitting ``stream_writer``.

    aiohttp 3.14 made ``stream_writer`` a required argument, and aioresponses
    (0.7.9) does not pass it yet. Drop this once aioresponses ships the fix
    (pnuckowski/aioresponses#288).
    """

    def __init__(self, *args, stream_writer=None, **kwargs):
        if stream_writer is None:
            stream_writer = Mock(output_size=0)
        super().__init__(*args, stream_writer=stream_writer, **kwargs)


@pytest.fixture(autouse=True)
def _aioresponses_aiohttp_compat():
    """Build mocked responses with the aiohttp 3.14-compatible class."""
    with patch.object(aioresponses_core, "ClientResponse", _ClientResponse):
        yield


@pytest.fixture
async def api_client():
    """Create a RutOSAPI with a real aiohttp session."""
    session = aiohttp.ClientSession()
    api = RutOSAPI(TEST_HOST, TEST_USER, TEST_PASS, session)
    yield api
    await session.close()


def _url(path: str) -> str:
    """Build a full API URL."""
    return f"{TEST_BASE_URL}{path}"


def _login_success(token: str = TEST_TOKEN, expires: int = 300):
    """Return a successful login response payload."""
    return {
        "success": True,
        "data": {
            "username": "admin",
            "group": "root",
            "token": token,
            "expires": expires,
        },
    }


def _login_failure(error: str = "Invalid username and/or password!"):
    """Return a failed login response payload."""
    return {
        "success": False,
        "errors": [{"source": "Authorization", "error": error, "code": 120}],
    }


def _success(data=None):
    """Return a successful API response."""
    if data is None:
        data = {}
    return {"success": True, "data": data}


def _error(
    error: str = "Something went wrong", source: str = "General", code: int = 100
):
    """Return an error API response."""
    return {
        "success": False,
        "errors": [{"source": source, "error": error, "code": code}],
    }


class TestLogin:
    """Tests for login/authentication."""

    async def test_login_success(self, api_client):
        """Test successful login stores token."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())

            await api_client.login()

            assert api_client._token == TEST_TOKEN

    async def test_login_invalid_credentials(self, api_client):
        """Test login with bad credentials raises RutOSAuthError."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_failure(), status=401)

            with pytest.raises(RutOSAuthError, match="Invalid username"):
                await api_client.login()

    async def test_login_missing_token(self, api_client):
        """Test login response without token raises RutOSAuthError."""
        with aioresponses() as m:
            m.post(
                _url("/login"),
                payload={"success": True, "data": {"username": "admin"}},
            )

            with pytest.raises(RutOSAuthError, match="No token"):
                await api_client.login()

    async def test_login_connection_error(self, api_client):
        """Test connection error during login raises RutOSConnectionError."""
        with aioresponses() as m:
            m.post(_url("/login"), exception=aiohttp.ClientConnectionError("refused"))

            with pytest.raises(RutOSConnectionError, match="Cannot connect"):
                await api_client.login()

    async def test_login_timeout(self, api_client):
        """Test a stalled login raises RutOSConnectionError instead of hanging."""
        with aioresponses() as m:
            m.post(_url("/login"), exception=TimeoutError())

            with pytest.raises(RutOSConnectionError, match="Timed out"):
                await api_client.login()

    async def test_login_sets_request_timeout(self, api_client):
        """Test login passes an explicit per-request timeout."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())

            await api_client.login()

            request = next(iter(m.requests.values()))[0]
            assert request.kwargs["timeout"].total == REQUEST_TIMEOUT


class TestRequest:
    """Tests for the authenticated _request method."""

    async def test_get_request_success(self, api_client):
        """Test successful GET request returns data."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/test/endpoint"), payload=_success({"key": "value"}))

            result = await api_client.get("/test/endpoint")

            assert result == {"key": "value"}

    async def test_put_request_success(self, api_client):
        """Test successful PUT request returns data."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.put(_url("/test/endpoint"), payload=_success({"updated": True}))

            result = await api_client.put("/test/endpoint", {"data": {"field": "val"}})

            assert result == {"updated": True}

    async def test_request_includes_bearer_token(self, api_client):
        """Test authenticated requests include the Bearer token."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/test"), payload=_success())

            await api_client.get("/test")

            # Check the GET request had the Authorization header
            for key, requests in m.requests.items():
                if key[0] == "GET":
                    headers = requests[0].kwargs.get("headers", {})
                    assert headers.get("Authorization") == f"Bearer {TEST_TOKEN}"

    async def test_request_connection_error(self, api_client):
        """Test connection error raises RutOSConnectionError."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/test"), exception=aiohttp.ClientConnectionError("refused"))

            with pytest.raises(RutOSConnectionError, match="Cannot connect"):
                await api_client.get("/test")

    async def test_request_timeout(self, api_client):
        """Test a stalled request raises RutOSConnectionError instead of hanging."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/test"), exception=TimeoutError())

            with pytest.raises(RutOSConnectionError, match="Timed out"):
                await api_client.get("/test")

    # aioresponses inspects async callbacks with a deprecated asyncio helper.
    @pytest.mark.filterwarnings(
        "ignore:'asyncio.iscoroutinefunction' is deprecated:DeprecationWarning"
    )
    async def test_requests_capped_at_max_concurrency(self, api_client):
        """Test parallel requests never exceed MAX_CONCURRENT_REQUESTS in flight."""
        in_flight = 0
        peak = 0

        async def _slow_response(url, **kwargs):
            nonlocal in_flight, peak
            in_flight += 1
            peak = max(peak, in_flight)
            await asyncio.sleep(0.01)
            in_flight -= 1
            return CallbackResult(payload=_success())

        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/test"), callback=_slow_response, repeat=True)

            await asyncio.gather(*(api_client.get("/test") for _ in range(12)))

        assert peak == MAX_CONCURRENT_REQUESTS

    async def test_request_sets_request_timeout(self, api_client):
        """Test authenticated requests pass an explicit per-request timeout."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/test"), payload=_success())

            await api_client.get("/test")

            for key, requests in m.requests.items():
                if key[0] == "GET":
                    assert requests[0].kwargs["timeout"].total == REQUEST_TIMEOUT

    async def test_request_api_error(self, api_client):
        """Test API error response raises RutOSAPIError."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/test"), payload=_error("bad request"))

            with pytest.raises(RutOSAPIError, match="bad request"):
                await api_client.get("/test")

    async def test_request_http_error(self, api_client):
        """Test non-401 HTTP error raises RutOSAPIError."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/test"), status=500)

            with pytest.raises(RutOSAPIError, match="HTTP 500"):
                await api_client.get("/test")

    async def test_request_auth_error_in_body(self, api_client):
        """Test Authorization error in response body raises RutOSAuthError."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(
                _url("/test"),
                payload=_error("Token expired", source="Authorization"),
            )
            # Need a second login + retry since first 200 with auth error doesn't trigger retry
            # Actually this is a 200 with success=false and Authorization source
            with pytest.raises(RutOSAuthError, match="Token expired"):
                await api_client.get("/test")


class TestTokenRetry:
    """Tests for automatic token refresh on 401."""

    async def test_401_triggers_reauth_and_retry(self, api_client):
        """Test 401 response triggers re-login and retries the request."""
        with aioresponses() as m:
            # Initial login
            m.post(_url("/login"), payload=_login_success("token1"))
            # First request returns 401
            m.get(_url("/test"), status=401)
            # Re-login
            m.post(_url("/login"), payload=_login_success("token2"))
            # Retry succeeds
            m.get(_url("/test"), payload=_success({"retried": True}))

            result = await api_client.get("/test")
            assert result == {"retried": True}

    async def test_401_twice_raises(self, api_client):
        """Test double 401 raises RutOSAuthError."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success("token1"))
            m.get(_url("/test"), status=401)
            m.post(_url("/login"), payload=_login_success("token2"))
            m.get(_url("/test"), status=401)

            with pytest.raises(RutOSAuthError, match="Authentication required"):
                await api_client.get("/test")

    # aioresponses inspects async callbacks with a deprecated asyncio helper.
    @pytest.mark.filterwarnings(
        "ignore:'asyncio.iscoroutinefunction' is deprecated:DeprecationWarning"
    )
    async def test_401_keeps_token_replaced_while_in_flight(self, api_client):
        """Test a 401 for a stale token doesn't discard its replacement."""

        async def _rejected_after_refresh(url, **kwargs):
            api_client._token = "token2"
            return CallbackResult(status=401)

        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success("token1"))
            m.get(_url("/test"), callback=_rejected_after_refresh)
            m.get(_url("/test"), payload=_success({"retried": True}))

            result = await api_client.get("/test")

            assert result == {"retried": True}
            assert api_client._token == "token2"
            assert len(m.requests[("POST", URL(_url("/login")))]) == 1

    async def test_queued_request_uses_current_token(self, api_client):
        """Test a request queued behind another sends the latest token."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success("token1"))
            m.get(_url("/test"), payload=_success())

            await api_client.login()
            await api_client._request_slots.acquire()
            queued = asyncio.create_task(api_client.get("/test"))
            await asyncio.sleep(0)
            api_client._token = "token2"
            api_client._request_slots.release()
            await queued

            request = m.requests[("GET", URL(_url("/test")))][0]
            assert request.kwargs["headers"]["Authorization"] == "Bearer token2"


class TestEnsureSession:
    """Tests for session refresh logic."""

    async def test_token_reused_past_reported_expiry(self, api_client):
        """Test the token is kept until the router rejects it.

        Requests reset the router's token timer, so the reported lifetime is
        not a reason to log in again.
        """
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success(expires=0))
            m.get(_url("/test"), payload=_success(), repeat=True)

            await api_client.get("/test")
            await api_client.get("/test")

            assert len(m.requests[("POST", URL(_url("/login")))]) == 1

    async def test_ensure_session_reuses_valid(self, api_client):
        """Test no refresh when token is still fresh."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())

            await api_client.login()
            token_before = api_client._token

            await api_client._ensure_session()
            assert api_client._token == token_before

    async def test_ensure_session_concurrent_callers(self, api_client):
        """Test lock ensures login is called only once for concurrent callers."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())

            await asyncio.gather(
                api_client._ensure_session(),
                api_client._ensure_session(),
                api_client._ensure_session(),
            )

            # All concurrent calls share one login
            assert api_client._token == TEST_TOKEN


class TestGetDeviceInfo:
    """Tests for get_device_info."""

    async def test_get_device_info_parses_correctly(self, api_client):
        """Test parsing of system device status response."""
        device_status = {
            "mnfinfo": {
                "serial": "1234567890",
                "mac": "00:1E:42:AA:BB:CC",
                "name": "RUTX50",
            },
            "static": {
                "fw_version": "RUTX_R_00.07.06.1",
                "device_name": "RUTX50",
                "hostname": "Teltonika-RUTX50",
            },
        }
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/system/device/status"), payload=_success(device_status))

            info = await api_client.get_device_info()

            assert info["serial"] == "1234567890"
            assert info["mac"] == "00:1E:42:AA:BB:CC"
            assert info["name"] == "RUTX50"
            assert info["firmware"] == "RUTX_R_00.07.06.1"
            assert info["model"] == "RUTX50"
            assert info["hostname"] == "Teltonika-RUTX50"

    async def test_get_device_info_handles_partial_data(self, api_client):
        """Test device info with missing sections."""
        device_status = {
            "static": {
                "fw_version": "RUTX_R_00.07.06.1",
                "device_name": "RUTX50",
            },
        }
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/system/device/status"), payload=_success(device_status))

            info = await api_client.get_device_info()

            assert info["firmware"] == "RUTX_R_00.07.06.1"
            assert info["model"] == "RUTX50"
            assert "serial" not in info


class TestGetWanInterfaces:
    """Tests for get_wan_interfaces."""

    async def test_get_wan_interfaces_filters_wan_only(self, api_client):
        """Test that LAN interfaces are excluded by area_type."""
        interfaces = [
            {
                "id": "lan",
                "area_type": "lan",
                "is_up": True,
                "proto": "static",
                "uptime": 0,
                "metric": 0,
            },
            {
                "id": "wan",
                "area_type": "wan",
                "is_up": True,
                "proto": "dhcp",
                "uptime": 100,
                "metric": 10,
                "ipv4-address": [{"address": "1.2.3.4", "mask": 24}],
                "device": "eth0",
                "l3_device": "eth0",
            },
            {
                "id": "mob1s1a1",
                "area_type": "wan",
                "is_up": False,
                "proto": "wwan",
                "uptime": 0,
                "metric": 20,
                "device": "wwan0",
                "l3_device": "wwan0",
            },
        ]
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/interfaces/status"), payload=_success(interfaces))
            m.get(_url("/interfaces/config"), payload=_success([]))

            result = await api_client.get_wan_interfaces()

            names = [i["name"] for i in result]
            assert "lan" not in names
            assert "wan" in names
            assert "mob1s1a1" in names

    async def test_get_wan_interfaces_sorted_by_metric(self, api_client):
        """Test interfaces are returned sorted by metric ascending."""
        interfaces = [
            {
                "id": "mob1s1a1",
                "area_type": "wan",
                "is_up": False,
                "proto": "wwan",
                "uptime": 0,
                "metric": 20,
                "device": "wwan0",
                "l3_device": "wwan0",
            },
            {
                "id": "wan",
                "area_type": "wan",
                "is_up": True,
                "proto": "dhcp",
                "uptime": 100,
                "metric": 10,
                "ipv4-address": [{"address": "1.2.3.4", "mask": 24}],
                "device": "eth0",
                "l3_device": "eth0",
            },
        ]
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/interfaces/status"), payload=_success(interfaces))
            m.get(_url("/interfaces/config"), payload=_success([]))

            result = await api_client.get_wan_interfaces()

            assert result[0]["name"] == "wan"
            assert result[1]["name"] == "mob1s1a1"
            assert result[0]["metric"] < result[1]["metric"]

    async def test_get_wan_interfaces_extracts_ip(self, api_client):
        """Test IP address is extracted from ipv4-address field with CIDR."""
        interfaces = [
            {
                "id": "wan",
                "area_type": "wan",
                "is_up": True,
                "proto": "dhcp",
                "uptime": 3600,
                "metric": 10,
                "ipv4-address": [{"address": "192.168.1.100", "mask": 24}],
                "device": "eth0",
                "l3_device": "eth0",
            },
        ]
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/interfaces/status"), payload=_success(interfaces))
            m.get(_url("/interfaces/config"), payload=_success([]))

            result = await api_client.get_wan_interfaces()

            assert result[0]["ip_address"] == "192.168.1.100/24"

    async def test_get_wan_interfaces_falls_back_to_ipaddrs(self, api_client):
        """Mobile WANs populate ipaddrs[] (with CIDR) instead of ipv4-address."""
        interfaces = [
            {
                "id": "mob1s2a1",
                "area_type": "wan",
                "is_up": True,
                "proto": "wwan",
                "uptime": 55093,
                "metric": 2,
                "ipv4-address": [],
                "ipaddrs": ["10.153.142.57/32"],
                "device": "wwan0",
                "l3_device": "wwan0",
            },
        ]
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/interfaces/status"), payload=_success(interfaces))
            m.get(_url("/interfaces/config"), payload=_success([]))

            result = await api_client.get_wan_interfaces()

            assert result[0]["ip_address"] == "10.153.142.57/32"

    async def test_get_wan_interfaces_uses_name_for_label(self, api_client):
        """Issue #18: `label` comes from router `name` (GUI label), `name` stays UCI id."""
        interfaces = [
            {
                "id": "wan2",
                "name": "wifi1",
                "area_type": "wan",
                "is_up": True,
                "proto": "dhcp",
                "uptime": 10,
                "metric": 1,
            },
            {
                "id": "wan1",
                "area_type": "wan",
                "is_up": True,
                "proto": "dhcp",
                "uptime": 20,
                "metric": 2,
            },
        ]
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/interfaces/status"), payload=_success(interfaces))
            m.get(_url("/interfaces/config"), payload=_success([]))

            result = await api_client.get_wan_interfaces()

            by_name = {i["name"]: i for i in result}
            assert by_name["wan2"]["label"] == "wifi1"
            assert by_name["wan1"]["label"] == "wan1"

    async def test_get_wan_interfaces_no_ip(self, api_client):
        """Test IP is None when neither ipv4-address nor ipaddrs is populated."""
        interfaces = [
            {
                "id": "mob1s1a1",
                "area_type": "wan",
                "is_up": False,
                "proto": "wwan",
                "uptime": 0,
                "metric": 20,
            },
        ]
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/interfaces/status"), payload=_success(interfaces))
            m.get(_url("/interfaces/config"), payload=_success([]))

            result = await api_client.get_wan_interfaces()

            assert result[0]["ip_address"] is None

    async def test_get_wan_interfaces_enabled_from_config_not_is_up(self, api_client):
        """Issue #20: `enabled` must come from /interfaces/config UCI flag, not is_up.

        The bug scenario: interface is enabled in the router GUI but hasn't yet
        come up (SIM negotiation, DHCP pending). /interfaces/status returns
        is_up=null/false while /interfaces/config has enabled="1". The switch
        must read the config flag so it doesn't flip back off after toggle.
        """
        status = [
            {
                "id": "mob1s1a1",
                "area_type": "wan",
                "is_up": None,
                "proto": "wwan",
                "uptime": 0,
                "metric": 1,
            },
            {
                "id": "wan3",
                "area_type": "wan",
                "is_up": False,
                "proto": "static",
                "uptime": 0,
                "metric": 5,
            },
            {
                "id": "mob1s2a1",
                "area_type": "wan",
                "is_up": True,
                "proto": "wwan",
                "uptime": 100,
                "metric": 2,
            },
        ]
        configs = [
            {"id": "lan", "area_type": "lan", "enabled": "1"},
            {"id": "mob1s1a1", "area_type": "wan", "enabled": "1"},
            {"id": "wan3", "area_type": "wan", "enabled": "0"},
            {"id": "mob1s2a1", "area_type": "wan", "enabled": "1"},
        ]
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/interfaces/status"), payload=_success(status))
            m.get(_url("/interfaces/config"), payload=_success(configs))

            result = await api_client.get_wan_interfaces()

            by_name = {i["name"]: i for i in result}
            # Enabled in config but link not up yet — the bug scenario.
            assert by_name["mob1s1a1"]["enabled"] is True
            assert by_name["mob1s1a1"]["status"] == "down"
            # Disabled in config, link down — switch should be off.
            assert by_name["wan3"]["enabled"] is False
            assert by_name["wan3"]["status"] == "down"
            # Enabled in config and link up.
            assert by_name["mob1s2a1"]["enabled"] is True
            assert by_name["mob1s2a1"]["status"] == "up"

    async def test_get_wan_interfaces_falls_back_to_is_up_when_config_fails(
        self, api_client
    ):
        """If /interfaces/config is unavailable, fall back to is_up for enabled."""
        status = [
            {
                "id": "wan",
                "area_type": "wan",
                "is_up": True,
                "proto": "dhcp",
                "uptime": 100,
                "metric": 1,
            },
        ]
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/interfaces/status"), payload=_success(status))
            m.get(_url("/interfaces/config"), status=500)

            result = await api_client.get_wan_interfaces()

            assert result[0]["enabled"] is True

    async def test_get_wan_interfaces_config_connection_error_propagates(
        self, api_client
    ):
        """A dropped connection on /interfaces/config is not a missing feature."""
        status = [{"id": "wan", "area_type": "wan", "is_up": True, "metric": 1}]
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/interfaces/status"), payload=_success(status))
            m.get(_url("/interfaces/config"), exception=TimeoutError())

            with pytest.raises(RutOSConnectionError):
                await api_client.get_wan_interfaces()


class TestGetInternetStatus:
    """Tests for get_internet_status."""

    async def test_get_internet_status_connected(self, api_client):
        """Test returns True when ipv4_status is connected."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(
                _url("/internet_connection/status"),
                payload=_success(
                    {
                        "ipv4_status": "connected",
                        "ipv6_status": "disconnected",
                        "dns_status": "connected",
                    }
                ),
            )

            assert await api_client.get_internet_status() is True

    async def test_get_internet_status_disconnected(self, api_client):
        """Test returns False when ipv4_status is disconnected."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(
                _url("/internet_connection/status"),
                payload=_success(
                    {
                        "ipv4_status": "disconnected",
                        "ipv6_status": "disconnected",
                        "dns_status": "disconnected",
                    }
                ),
            )

            assert await api_client.get_internet_status() is False

    async def test_get_internet_status_error_returns_false(self, api_client):
        """Test returns False on API error."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(
                _url("/internet_connection/status"),
                payload=_error("Service unavailable"),
            )

            assert await api_client.get_internet_status() is False

    async def test_get_internet_status_connection_error_propagates(self, api_client):
        """Test a timeout is reported as a failure, not as no internet."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/internet_connection/status"), exception=TimeoutError())

            with pytest.raises(RutOSConnectionError):
                await api_client.get_internet_status()


class TestSetInterfaceEnabled:
    """Tests for set_interface_enabled."""

    async def test_enable_interface(self, api_client):
        """Test enabling sends PUT with enabled=1."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.put(_url("/interfaces/config/wan"), payload=_success())

            await api_client.set_interface_enabled("wan", True)

            # Verify the PUT request body
            for key, requests in m.requests.items():
                if key[0] == "PUT":
                    body = requests[0].kwargs["json"]
                    assert body == {"data": {"enabled": "1"}}

    async def test_disable_interface(self, api_client):
        """Test disabling sends PUT with enabled=0."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.put(_url("/interfaces/config/mob1s1a1"), payload=_success())

            await api_client.set_interface_enabled("mob1s1a1", False)

            for key, requests in m.requests.items():
                if key[0] == "PUT":
                    body = requests[0].kwargs["json"]
                    assert body == {"data": {"enabled": "0"}}


class TestSetFailoverOrder:
    """Tests for set_failover_order."""

    async def test_set_failover_order(self, api_client):
        """Test sets mwan3 member metrics via single bulk PUT.

        The API method now takes pre-resolved member IDs, so the caller is
        responsible for the member-ID/interface-ID translation (typically via
        get_active_failover_chain).
        """
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.put(_url("/failover/members/config"), payload=_success())

            await api_client.set_failover_order(
                ["wan1_member_mwan", "mob1s1a1_member_mwan"]
            )

            put_requests = []
            for key, requests in m.requests.items():
                if key[0] == "PUT":
                    for req in requests:
                        put_requests.append(req.kwargs["json"])

            assert len(put_requests) == 1
            assert put_requests[0] == {
                "data": [
                    {"id": "wan1_member_mwan", "metric": "1"},
                    {"id": "mob1s1a1_member_mwan", "metric": "2"},
                ]
            }


class TestGetActiveFailoverChain:
    """Tests for get_active_failover_chain."""

    @staticmethod
    def _failover_setup(
        m: aioresponses,
        *,
        rules: list[dict] | None = None,
        policies: list[dict] | None = None,
        members: list[dict] | None = None,
        interfaces: list[dict] | None = None,
    ) -> None:
        """Stub the policies/rules/members/interfaces endpoints."""
        m.post(_url("/login"), payload=_login_success())
        m.get(_url("/failover/policies/config"), payload=_success(policies or []))
        m.get(_url("/failover/rules/config"), payload=_success(rules or []))
        m.get(_url("/failover/members/config"), payload=_success(members or []))
        m.get(
            _url("/failover/interfaces/config"), payload=_success(interfaces or [])
        )

    async def test_failover_mode_with_default_rule(self, api_client):
        """Default rule selects the failover policy; mode is 'failover'."""
        with aioresponses() as m:
            self._failover_setup(
                m,
                rules=[{"id": "default_rule", "name": "default_rule",
                        "use_policy": "mwan_default"}],
                policies=[{
                    "id": "mwan_default", "name": "mwan",
                    "use_member": ["mob1s1a1_member_mwan", "wan1_member_mwan"],
                }],
                members=[
                    {"id": "mob1s1a1_member_mwan", "interface": "mob1s1a1",
                     "metric": "1"},
                    {"id": "wan1_member_mwan", "interface": "wan1", "metric": "2"},
                ],
                interfaces=[
                    {"id": "mob1s1a1", "name": "mob1s1a1"},
                    {"id": "wan1", "name": "wan1"},
                ],
            )
            chain = await api_client.get_active_failover_chain()

        assert chain["policy_id"] == "mwan_default"
        assert chain["mode"] == "failover"
        assert [m["id"] for m in chain["members"]] == [
            "mob1s1a1_member_mwan",
            "wan1_member_mwan",
        ]
        assert [m["network_id"] for m in chain["members"]] == ["mob1s1a1", "wan1"]

    async def test_member_interface_resolved_via_mwan_interface_bridge(
        self, api_client
    ):
        """``mwan_member.interface`` is the mwan_interface display name, not its id.

        Regression for #38: when the user customizes the display name (or wifi
        interfaces, where defaults already differ), ``member.interface`` no
        longer matches the network UCI id and we have to bridge through
        ``/failover/interfaces/config`` (``mwan_interface.name`` →
        ``mwan_interface.id``).
        """
        with aioresponses() as m:
            self._failover_setup(
                m,
                rules=[{"id": "default_rule", "name": "default_rule",
                        "use_policy": "mwan_default"}],
                policies=[{
                    "id": "mwan_default", "name": "mwan",
                    "use_member": ["wan2_member_mwan"],
                }],
                members=[
                    {"id": "wan2_member_mwan", "interface": "wifi1", "metric": "1"},
                ],
                interfaces=[
                    {"id": "wan2", "name": "wifi1"},
                ],
            )
            chain = await api_client.get_active_failover_chain()

        assert chain["members"][0]["interface"] == "wifi1"
        assert chain["members"][0]["network_id"] == "wan2"

    async def test_member_network_id_none_when_bridge_missing(self, api_client):
        """``network_id`` is None if no mwan_interface entry matches."""
        with aioresponses() as m:
            self._failover_setup(
                m,
                rules=[{"id": "default_rule", "name": "default_rule",
                        "use_policy": "mwan_default"}],
                policies=[{
                    "id": "mwan_default", "name": "mwan",
                    "use_member": ["orphan_member"],
                }],
                members=[
                    {"id": "orphan_member", "interface": "ghost", "metric": "1"},
                ],
                interfaces=[],
            )
            chain = await api_client.get_active_failover_chain()

        assert chain["members"][0]["network_id"] is None

    async def test_balance_mode_detected_via_equal_metrics(self, api_client):
        """Members all sharing one metric => balance mode."""
        with aioresponses() as m:
            self._failover_setup(
                m,
                rules=[{"id": "default_rule", "name": "default_rule",
                        "use_policy": "balance_default"}],
                policies=[{
                    "id": "balance_default", "name": "balance",
                    "use_member": [
                        "mob1s1a1_member_balance", "wan1_member_balance",
                    ],
                }],
                members=[
                    {"id": "mob1s1a1_member_balance", "interface": "mob1s1a1",
                     "metric": "1", "weight": "1"},
                    {"id": "wan1_member_balance", "interface": "wan1",
                     "metric": "1", "weight": "1"},
                ],
            )
            chain = await api_client.get_active_failover_chain()

        assert chain["mode"] == "balance"
        assert chain["policy_id"] == "balance_default"

    async def test_no_naming_assumption_in_discovery(self, api_client):
        """Discovery works regardless of member-ID suffix (regression #38)."""
        with aioresponses() as m:
            self._failover_setup(
                m,
                rules=[{"id": "rule1", "name": "default_rule",
                        "use_policy": "p1"}],
                policies=[{"id": "p1", "name": "p1",
                           "use_member": ["custom_a", "custom_b"]}],
                members=[
                    {"id": "custom_a", "interface": "wan1", "metric": "1"},
                    {"id": "custom_b", "interface": "mob1", "metric": "2"},
                ],
            )
            chain = await api_client.get_active_failover_chain()

        assert chain["mode"] == "failover"
        assert [m["interface"] for m in chain["members"]] == ["wan1", "mob1"]

    async def test_empty_when_no_rules_or_policies(self, api_client):
        """No rules and no policies => empty chain, default failover mode."""
        with aioresponses() as m:
            self._failover_setup(m, rules=[], policies=[], members=[])
            chain = await api_client.get_active_failover_chain()

        assert chain == {"policy_id": None, "mode": "failover", "members": []}

    async def test_stops_at_first_connection_failure(self, api_client):
        """No further config endpoints are queued once the router stops responding."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/failover/policies/config"), exception=TimeoutError())

            with pytest.raises(RutOSConnectionError):
                await api_client.get_active_failover_chain()

            gets = [key for key in m.requests if key[0] == "GET"]
            assert len(gets) == 1


class TestPostMethod:
    """Tests for the post() convenience method."""

    async def test_post_request_success(self, api_client):
        """Test successful POST request returns data."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.post(_url("/some/endpoint"), payload=_success({"created": True}))

            result = await api_client.post("/some/endpoint", {"key": "val"})

            assert result == {"created": True}

    async def test_post_request_no_body(self, api_client):
        """Test POST request with no body passes None as json."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.post(_url("/some/endpoint"), payload=_success())

            result = await api_client.post("/some/endpoint")

            assert result == {}


class TestRequestEdgeCases:
    """Tests for edge cases in _request."""

    async def test_non_dict_response_raises_api_error(self, api_client):
        """Test that a non-dict JSON response raises RutOSAPIError."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            # Return a JSON list instead of a dict
            m.get(_url("/test"), payload=[1, 2, 3])

            with pytest.raises(RutOSAPIError, match="Unexpected response format"):
                await api_client.get("/test")

    async def test_login_client_error_raises_api_error(self, api_client):
        """Test generic aiohttp.ClientError during login raises RutOSAPIError."""
        with aioresponses() as m:
            m.post(_url("/login"), exception=aiohttp.ClientError("generic error"))

            with pytest.raises(RutOSAPIError, match="Login request failed"):
                await api_client.login()

    async def test_request_client_error_raises_api_error(self, api_client):
        """Test generic aiohttp.ClientError during request raises RutOSAPIError."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/test"), exception=aiohttp.ClientError("generic error"))

            with pytest.raises(RutOSAPIError, match="API request failed"):
                await api_client.get("/test")

    async def test_auth_headers_empty_when_no_token(self, api_client):
        """Test _auth_headers returns empty dict when no token is set."""
        assert api_client._token is None
        assert api_client._auth_headers() == {}

    async def test_auth_headers_bearer_when_token_set(self, api_client):
        """Test _auth_headers returns Authorization header when token is set."""
        api_client._token = "my-token"
        headers = api_client._auth_headers()
        assert headers == {"Authorization": "Bearer my-token"}


class TestGetWanInterfacesEdgeCases:
    """Tests for edge cases in get_wan_interfaces."""

    async def test_non_list_response_returns_empty(self, api_client):
        """Test that a non-list response returns an empty list."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/interfaces/status"), payload=_success({"unexpected": "dict"}))

            result = await api_client.get_wan_interfaces()

            assert result == []


class TestGetInternetStatusVariants:
    """Tests for additional internet status values."""

    async def test_get_internet_status_online(self, api_client):
        """Test returns True when ipv4_status is 'online'."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(
                _url("/internet_connection/status"),
                payload=_success({"ipv4_status": "online"}),
            )

            assert await api_client.get_internet_status() is True

    async def test_get_internet_status_up(self, api_client):
        """Test returns True when ipv4_status is 'up'."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(
                _url("/internet_connection/status"),
                payload=_success({"ipv4_status": "up"}),
            )

            assert await api_client.get_internet_status() is True


class TestGetGPSPosition:
    """Tests for get_gps_position."""

    async def test_get_gps_position_success(self, api_client):
        """Test parsing of GPS position response."""
        gps_data = {
            "latitude": 37.7749,
            "longitude": -122.4194,
            "accuracy": 5,
            "altitude": 15.2,
            "speed": 65.3,
            "angle": 180,
            "satellites": 12,
            "fix_status": "3D",
        }
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/gps/position/status"), payload=_success(gps_data))

            result = await api_client.get_gps_position()

            assert result["latitude"] == 37.7749
            assert result["longitude"] == -122.4194
            assert result["speed"] == 65.3
            assert result["satellites"] == 12

    async def test_get_gps_position_no_fix(self, api_client):
        """Test returns None when no GPS fix (no lat/lon)."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(
                _url("/gps/position/status"),
                payload=_success({"fix_status": "no_fix"}),
            )

            result = await api_client.get_gps_position()
            assert result is None

    async def test_get_gps_position_api_error(self, api_client):
        """Test returns None on API error (GPS not available)."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(
                _url("/gps/position/status"),
                payload=_error("Service unavailable"),
            )

            result = await api_client.get_gps_position()
            assert result is None

    async def test_get_gps_position_connection_error_propagates(self, api_client):
        """Test a timeout is not mistaken for GPS being unavailable."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/gps/position/status"), exception=TimeoutError())

            with pytest.raises(RutOSConnectionError):
                await api_client.get_gps_position()

    async def test_get_gps_position_non_dict(self, api_client):
        """Test returns None for non-dict response."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/gps/position/status"), payload=_success([]))

            result = await api_client.get_gps_position()
            assert result is None


class TestGetDataLimit:
    """Tests for get_data_limit."""

    async def test_get_data_limit_success(self, api_client):
        """Test parsing of data limit status response."""
        data = [
            {
                "id": "limit1",
                "interface": "mob1s1a1",
                "enabled": True,
                "data_limit": 5000000000,
                "data_used": 2500000000,
                "data_warning_enabled": True,
                "data_warning_limit": 4000000000,
                "due_reset_time": 1735689600,
            },
        ]
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/data_limit/status"), payload=_success(data))

            result = await api_client.get_data_limit()

            assert len(result) == 1
            assert result[0]["id"] == "limit1"
            assert result[0]["data_used"] == 2500000000
            assert result[0]["data_limit"] == 5000000000

    async def test_get_data_limit_converts_string_values(self, api_client):
        """Test that string numeric values from API are converted to int."""
        data = [
            {
                "id": "limit1",
                "interface": "mob1s1a1",
                "enabled": True,
                "data_limit": "5000000000",
                "data_used": "2500000000",
                "data_warning_enabled": True,
                "data_warning_limit": "4000000000",
                "due_reset_time": 1735689600,
            },
        ]
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/data_limit/status"), payload=_success(data))

            result = await api_client.get_data_limit()

            assert result[0]["data_used"] == 2500000000
            assert result[0]["data_limit"] == 5000000000
            assert result[0]["data_warning_limit"] == 4000000000
            assert isinstance(result[0]["data_used"], int)
            assert isinstance(result[0]["data_limit"], int)

    async def test_get_data_limit_empty(self, api_client):
        """Test returns empty list when no limits configured."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/data_limit/status"), payload=_success([]))

            result = await api_client.get_data_limit()
            assert result == []

    async def test_get_data_limit_api_error(self, api_client):
        """Test returns empty list on API error."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(
                _url("/data_limit/status"),
                payload=_error("Service unavailable"),
            )

            result = await api_client.get_data_limit()
            assert result == []

    async def test_get_data_limit_connection_error_propagates(self, api_client):
        """Test a timeout is not mistaken for no limits being configured."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/data_limit/status"), exception=TimeoutError())

            with pytest.raises(RutOSConnectionError):
                await api_client.get_data_limit()

    async def test_get_data_limit_non_list(self, api_client):
        """Test returns empty list for non-list response."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/data_limit/status"), payload=_success({"unexpected": True}))

            result = await api_client.get_data_limit()
            assert result == []


class TestClearDataUsage:
    """Tests for clear_data_usage."""

    async def test_clear_data_usage(self, api_client):
        """Test clear data usage sends POST."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.post(_url("/data_limit/actions/clear"), payload=_success())

            await api_client.clear_data_usage()

            # Verify the POST was sent
            post_count = sum(
                1 for key in m.requests if key[0] == "POST" and "clear" in str(key[1])
            )
            assert post_count == 1


class TestRebootModem:
    """Tests for reboot_modem."""

    async def test_reboot_modem(self, api_client):
        """Test modem reboot sends POST to correct endpoint."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.post(_url("/modems/modem1/actions/reboot"), payload=_success())

            await api_client.reboot_modem("modem1")

            post_count = sum(
                1 for key in m.requests if key[0] == "POST" and "modem1" in str(key[1])
            )
            assert post_count == 1


class TestGetModems:
    """Tests for the modem list from get_modem_data."""

    async def test_get_modems_success(self, api_client):
        """Test parsing modem list from /modems/status (top-level id)."""
        status_data = [
            {"id": "2-1", "operator": "Rogers"},
            {"id": "3-1", "operator": "Bell"},
        ]
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/modems/status"), payload=_success(status_data))

            result = (await api_client.get_modem_data()).modems

            assert len(result) == 2
            assert result[0]["id"] == "2-1"
            assert result[1]["id"] == "3-1"

    async def test_get_modems_falls_back_to_signal_status(self, api_client):
        """If /modems/status errors, fall back to /modems/signal/status.

        /modems/signal/status uses 'modem' as the id key instead of 'id'.
        """
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/modems/status"), payload=_error("unavailable"))
            m.get(
                _url("/modems/signal/status"),
                payload=_success([{"modem": "2-1"}, {"modem": "3-1"}]),
            )

            result = (await api_client.get_modem_data()).modems

            assert [r["id"] for r in result] == ["2-1", "3-1"]

    async def test_get_modems_empty(self, api_client):
        """Test returns empty list when no modems."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/modems/status"), payload=_success([]))

            result = (await api_client.get_modem_data()).modems
            assert result == []

    async def test_get_modems_api_error(self, api_client):
        """Test returns empty list when both endpoints fail."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/modems/status"), payload=_error("Service unavailable"))
            m.get(
                _url("/modems/signal/status"),
                payload=_error("Service unavailable"),
            )

            result = (await api_client.get_modem_data()).modems
            assert result == []


class TestGetModemSignal:
    """Tests for the modem signal data from get_modem_data."""

    async def test_get_modem_signal_from_status(self, api_client):
        """Primary path: /modems/status has flat signal fields."""
        status_data = [
            {
                "id": "2-1",
                "rssi": -73,
                "rsrp": -98,
                "rsrq": -8,
                "sinr": 10,
                "signal_quality": 71,
                "band": "LTE B12",
                "conntype": "5G (NSA)",
                "ntype": "5G-NSA",
                "ca_signal": [{"frequency": 5060}],
            },
        ]
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/modems/status"), payload=_success(status_data))

            result = (await api_client.get_modem_data()).signal

            assert len(result) == 1
            assert result[0]["id"] == "2-1"
            assert result[0]["rssi"] == -73
            assert result[0]["rsrp"] == -98
            assert result[0]["rsrq"] == -8
            assert result[0]["sinr"] == 10
            assert result[0]["signal_quality"] == 71
            assert result[0]["band"] == "LTE B12"
            # conntype wins over ntype for human-readable network_type
            assert result[0]["network_type"] == "5G (NSA)"
            assert result[0]["channel_number"] == 5060

    async def test_get_modem_signal_network_type_ntype_fallback(self, api_client):
        """When conntype is absent, fall back to ntype."""
        status_data = [{"id": "2-1", "rssi": -65, "ntype": "LTE-A"}]
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/modems/status"), payload=_success(status_data))

            result = (await api_client.get_modem_data()).signal

            assert result[0]["network_type"] == "LTE-A"

    async def test_get_modem_signal_nested_signal_fallback(self, api_client):
        """Fall back to /modems/signal/status nested 'signal' array when status fails."""
        signal_data = [
            {
                "modem": "2-1",
                "signal": [
                    {
                        "rssi": -80,
                        "rsrp": -100,
                        "rsrq": -12,
                        "sinr": 5,
                        "band": "LTE B12",
                        "network_type": 24,
                        "channel_number": 5060,
                        "timestamp": "1776519700",
                    },
                    {
                        "rssi": -72,
                        "rsrp": -98,
                        "rsrq": -8,
                        "sinr": 9,
                        "band": "LTE B12",
                        "network_type": 24,
                        "channel_number": 5060,
                        "timestamp": "1776523359",
                    },
                ],
            }
        ]
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/modems/status"), payload=_error("unavailable"))
            m.get(_url("/modems/signal/status"), payload=_success(signal_data))

            result = (await api_client.get_modem_data()).signal

            assert len(result) == 1
            assert result[0]["id"] == "2-1"
            # Latest sample (last element of signal[]) should win
            assert result[0]["rssi"] == -72
            assert result[0]["rsrp"] == -98
            assert result[0]["channel_number"] == 5060

    async def test_get_modem_signal_empty(self, api_client):
        """Test a router with no modems isn't sent the fallback request."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/modems/status"), payload=_success([]))

            result = (await api_client.get_modem_data()).signal
            assert result == []
            assert ("GET", URL(_url("/modems/signal/status"))) not in m.requests

    async def test_get_modem_signal_api_error(self, api_client):
        """Test returns empty list when both endpoints error."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/modems/status"), payload=_error("Service unavailable"))
            m.get(
                _url("/modems/signal/status"),
                payload=_error("Service unavailable"),
            )

            result = (await api_client.get_modem_data()).signal
            assert result == []

    async def test_get_modem_signal_non_list(self, api_client):
        """Test returns empty list when both endpoints return non-list."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/modems/status"), payload=_success({"unexpected": True}))
            m.get(_url("/modems/signal/status"), payload=_success({"unexpected": True}))

            result = (await api_client.get_modem_data()).signal
            assert result == []

    async def test_get_modem_signal_carrier_aggregation(self, api_client):
        """5G-NSA with aggregated LTE + NR carriers: primary PCell overrides top-level band."""
        status_data = [
            {
                "id": "2-1",
                "rssi": -62,
                "band": "5G N78",
                "conntype": "5G (NSA)",
                "ca_signal": [
                    {
                        "band": "LTE B7",
                        "primary": True,
                        "bandwidth": "20",
                        "rsrp": -97,
                        "rsrq": -12,
                        "sinr": 11,
                        "pcid": 82,
                        "frequency": 2850,
                    },
                    {
                        "band": "5G N78",
                        "primary": False,
                        "bandwidth": "50",
                        "rsrp": -113,
                        "rsrq": -19,
                        "sinr": -7,
                        "pcid": 129,
                        "frequency": 640608,
                    },
                ],
            }
        ]
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/modems/status"), payload=_success(status_data))

            result = (await api_client.get_modem_data()).signal

            assert len(result) == 1
            # Primary carrier (LTE B7) overrides the misleading top-level "5G N78".
            assert result[0]["band"] == "LTE B7"
            assert result[0]["channel_number"] == 2850
            assert len(result[0]["carriers"]) == 2
            assert result[0]["carriers"][0]["band"] == "LTE B7"
            assert result[0]["carriers"][0]["primary"] is True
            assert result[0]["carriers"][1]["band"] == "5G N78"
            assert result[0]["carriers"][1]["primary"] is False

    async def test_get_modem_signal_carriers_empty_without_ca_signal(self, api_client):
        """Modems with no ca_signal still get carriers=[] for attribute parity."""
        status_data = [{"id": "2-1", "band": "LTE B12"}]
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/modems/status"), payload=_success(status_data))

            result = (await api_client.get_modem_data()).signal
            assert result[0]["carriers"] == []
            assert result[0]["band"] == "LTE B12"

    async def test_get_modem_signal_fallback_emits_empty_carriers(self, api_client):
        """Fallback /modems/signal/status path has no ca_signal — carriers must be []."""
        signal_data = [
            {
                "modem": "2-1",
                "signal": [
                    {
                        "rssi": -72,
                        "band": "LTE B12",
                        "channel_number": 5060,
                    }
                ],
            }
        ]
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/modems/status"), payload=_error("unavailable"))
            m.get(_url("/modems/signal/status"), payload=_success(signal_data))

            result = (await api_client.get_modem_data()).signal
            assert result[0]["carriers"] == []


class TestGetModemStatus:
    """Tests for the modem operator data from get_modem_data."""

    async def test_get_modem_status_home(self, api_client):
        """Test parsing of modem status response with home network."""
        status_data = [
            {
                "id": "2-1",
                "operator": "Bell",
                "operator_state": "Registered, home",
            },
        ]
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/modems/status"), payload=_success(status_data))

            result = (await api_client.get_modem_data()).status

            assert len(result) == 1
            assert result[0]["id"] == "2-1"
            assert result[0]["operator"] == "Bell"
            assert result[0]["roaming"] is False

    async def test_get_modem_status_roaming(self, api_client):
        """Test roaming detection from operator_state."""
        status_data = [
            {
                "id": "2-1",
                "operator": "AT&T",
                "operator_state": "Registered, roaming",
            },
        ]
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/modems/status"), payload=_success(status_data))

            result = (await api_client.get_modem_data()).status

            assert len(result) == 1
            assert result[0]["operator"] == "AT&T"
            assert result[0]["roaming"] is True

    async def test_get_modem_status_empty(self, api_client):
        """Test returns empty list when no modems."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/modems/status"), payload=_success([]))

            result = (await api_client.get_modem_data()).status
            assert result == []

    async def test_get_modem_status_api_error(self, api_client):
        """Test returns empty list on API error."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(
                _url("/modems/status"),
                payload=_error("Service unavailable"),
            )
            m.get(
                _url("/modems/signal/status"),
                payload=_error("Service unavailable"),
            )

            result = (await api_client.get_modem_data()).status
            assert result == []

    async def test_get_modem_status_non_list(self, api_client):
        """Test returns empty list for non-list response."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/modems/status"), payload=_success({"unexpected": True}))
            m.get(_url("/modems/signal/status"), payload=_success({"unexpected": True}))

            result = (await api_client.get_modem_data()).status
            assert result == []


class TestGetModemData:
    """Tests for how get_modem_data uses the router."""

    async def test_single_request_supplies_all_modem_data(self, api_client):
        """Signal, operator, and identity all come from one /modems/status call."""
        status_data = [{"id": "2-1", "rssi": -73, "operator": "Bell"}]
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/modems/status"), payload=_success(status_data))

            result = await api_client.get_modem_data()

            assert result.signal[0]["rssi"] == -73
            assert result.status[0]["operator"] == "Bell"
            assert result.modems == [{"id": "2-1"}]
            assert len(m.requests[("GET", URL(_url("/modems/status")))]) == 1

    async def test_connection_error_skips_fallback(self, api_client):
        """A stalled router isn't sent the fallback request as well."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/modems/status"), exception=TimeoutError())

            with pytest.raises(RutOSConnectionError):
                await api_client.get_modem_data()

            assert ("GET", URL(_url("/modems/signal/status"))) not in m.requests


class TestGetFailoverStatus:
    """Tests for get_failover_status (mwan3 tracking state)."""

    async def test_returns_status_keyed_by_interface(self, api_client):
        """Per-interface mwan3 status dicts are returned as-is."""
        status_data = {
            "wan1": {"status": "offline", "up": True, "uptime": 36000},
            "mob1s2a1": {"status": "online", "up": True, "uptime": 1300},
        }
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/failover/status"), payload=_success(status_data))

            result = await api_client.get_failover_status()

            assert result == status_data

    async def test_skips_non_dict_entries(self, api_client):
        """Malformed per-interface entries are dropped."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(
                _url("/failover/status"),
                payload=_success({"wan1": {"status": "online"}, "bogus": "x"}),
            )

            result = await api_client.get_failover_status()

            assert result == {"wan1": {"status": "online"}}

    async def test_api_error_returns_empty(self, api_client):
        """Endpoint failure degrades to an empty dict."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/failover/status"), payload=_error("Unauthorized"))

            result = await api_client.get_failover_status()

            assert result == {}

    async def test_connection_error_propagates(self, api_client):
        """A timeout is not mistaken for the endpoint being unavailable."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/failover/status"), exception=TimeoutError())

            with pytest.raises(RutOSConnectionError):
                await api_client.get_failover_status()

    async def test_non_dict_returns_empty(self, api_client):
        """Unexpected payload shape degrades to an empty dict."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/failover/status"), payload=_success([]))

            result = await api_client.get_failover_status()

            assert result == {}
