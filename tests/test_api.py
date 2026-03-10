"""Tests for the RutOS REST API client."""

from __future__ import annotations

import asyncio
import time
import aiohttp
import pytest
from aioresponses import aioresponses

from custom_components.rutos.api import (
    RutOSAPI,
    RutOSAPIError,
    RutOSAuthError,
    RutOSConnectionError,
)
from custom_components.rutos.const import API_PATH, SESSION_REFRESH_MARGIN

TEST_HOST = "192.168.1.1"
TEST_BASE_URL = f"https://{TEST_HOST}{API_PATH}"
TEST_USER = "admin"
TEST_PASS = "admin01"
TEST_TOKEN = "test-token-abc123"


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


def _error(error: str = "Something went wrong", source: str = "General", code: int = 100):
    """Return an error API response."""
    return {
        "success": False,
        "errors": [{"source": source, "error": error, "code": code}],
    }


class TestLogin:
    """Tests for login/authentication."""

    async def test_login_success(self, api_client):
        """Test successful login stores token and sets expiry."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())

            await api_client.login()

            assert api_client._token == TEST_TOKEN
            assert api_client._token_expiry > time.monotonic()

    async def test_login_custom_expiry(self, api_client):
        """Test login respects the expires field from response."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success(expires=600))

            before = time.monotonic()
            await api_client.login()

            assert api_client._token_expiry >= before + 600

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


class TestEnsureSession:
    """Tests for session refresh logic."""

    async def test_ensure_session_refreshes_near_expiry(self, api_client):
        """Test session is refreshed when within margin of expiry."""
        with aioresponses() as m:
            # First login
            m.post(_url("/login"), payload=_login_success("token1"))
            await api_client.login()
            assert api_client._token == "token1"

            # Simulate near-expiry
            api_client._token_expiry = time.monotonic() + SESSION_REFRESH_MARGIN - 1

            # Should trigger refresh
            m.post(_url("/login"), payload=_login_success("token2"))
            await api_client._ensure_session()
            assert api_client._token == "token2"

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

            results = await asyncio.gather(
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

            result = await api_client.get_wan_interfaces()

            assert result[0]["name"] == "wan"
            assert result[1]["name"] == "mob1s1a1"
            assert result[0]["metric"] < result[1]["metric"]

    async def test_get_wan_interfaces_extracts_ip(self, api_client):
        """Test IP address is extracted from ipv4-address field."""
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

            result = await api_client.get_wan_interfaces()

            assert result[0]["ip_address"] == "192.168.1.100"

    async def test_get_wan_interfaces_no_ip(self, api_client):
        """Test IP is None when no ipv4-address."""
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

            result = await api_client.get_wan_interfaces()

            assert result[0]["ip_address"] is None


class TestGetInternetStatus:
    """Tests for get_internet_status."""

    async def test_get_internet_status_connected(self, api_client):
        """Test returns True when ipv4_status is connected."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(
                _url("/internet_connection/status"),
                payload=_success({
                    "ipv4_status": "connected",
                    "ipv6_status": "disconnected",
                    "dns_status": "connected",
                }),
            )

            assert await api_client.get_internet_status() is True

    async def test_get_internet_status_disconnected(self, api_client):
        """Test returns False when ipv4_status is disconnected."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(
                _url("/internet_connection/status"),
                payload=_success({
                    "ipv4_status": "disconnected",
                    "ipv6_status": "disconnected",
                    "dns_status": "disconnected",
                }),
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
        """Test sets metrics via individual PUT calls."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.put(_url("/interfaces/config/wan"), payload=_success())
            m.put(_url("/interfaces/config/mob1s1a1"), payload=_success())

            await api_client.set_failover_order(["wan", "mob1s1a1"])

            # Verify PUT calls
            put_requests = []
            for key, requests in m.requests.items():
                if key[0] == "PUT":
                    for req in requests:
                        put_requests.append((str(key[1]), req.kwargs["json"]))

            assert len(put_requests) == 2

            # First interface gets metric 10
            wan_put = next(p for p in put_requests if "wan" in p[0] and "mob" not in p[0])
            assert wan_put[1] == {"data": {"metric": "10"}}

            # Second interface gets metric 20
            mob_put = next(p for p in put_requests if "mob1s1a1" in p[0])
            assert mob_put[1] == {"data": {"metric": "20"}}


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
                1 for key in m.requests
                if key[0] == "POST" and "clear" in str(key[1])
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
                1 for key in m.requests
                if key[0] == "POST" and "modem1" in str(key[1])
            )
            assert post_count == 1


class TestGetModems:
    """Tests for get_modems."""

    async def test_get_modems_success(self, api_client):
        """Test parsing modem list from signal status."""
        signal_data = [
            {"id": "modem1", "rssi": -65},
            {"id": "modem2", "rssi": -70},
        ]
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/modems/signal/status"), payload=_success(signal_data))

            result = await api_client.get_modems()

            assert len(result) == 2
            assert result[0]["id"] == "modem1"
            assert result[1]["id"] == "modem2"

    async def test_get_modems_empty(self, api_client):
        """Test returns empty list when no modems."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/modems/signal/status"), payload=_success([]))

            result = await api_client.get_modems()
            assert result == []

    async def test_get_modems_api_error(self, api_client):
        """Test returns empty list on API error."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(
                _url("/modems/signal/status"),
                payload=_error("Service unavailable"),
            )

            result = await api_client.get_modems()
            assert result == []


class TestGetModemSignal:
    """Tests for get_modem_signal."""

    async def test_get_modem_signal_success(self, api_client):
        """Test parsing of modem signal response."""
        signal_data = [
            {
                "id": "modem1",
                "rssi": -65,
                "rsrp": -95,
                "rsrq": -10,
                "sinr": 12,
                "network_type": "LTE",
                "band": "B7",
                "channel_number": 3100,
            },
        ]
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/modems/signal/status"), payload=_success(signal_data))

            result = await api_client.get_modem_signal()

            assert len(result) == 1
            assert result[0]["id"] == "modem1"
            assert result[0]["rsrp"] == -95
            assert result[0]["network_type"] == "LTE"

    async def test_get_modem_signal_empty(self, api_client):
        """Test returns empty list when no modems."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/modems/signal/status"), payload=_success([]))

            result = await api_client.get_modem_signal()
            assert result == []

    async def test_get_modem_signal_api_error(self, api_client):
        """Test returns empty list on API error."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(
                _url("/modems/signal/status"),
                payload=_error("Service unavailable"),
            )

            result = await api_client.get_modem_signal()
            assert result == []

    async def test_get_modem_signal_non_list(self, api_client):
        """Test returns empty list for non-list response."""
        with aioresponses() as m:
            m.post(_url("/login"), payload=_login_success())
            m.get(_url("/modems/signal/status"), payload=_success({"unexpected": True}))

            result = await api_client.get_modem_signal()
            assert result == []
