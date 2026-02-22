"""Tests for the RutOS API client."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest
from aioresponses import aioresponses
from yarl import URL

from custom_components.rutos.api import (
    JSONRPC_SESSION_EXPIRED,
    RutOSAPI,
    RutOSAPIError,
    RutOSAuthError,
    RutOSConnectionError,
)
from custom_components.rutos.const import API_PATH, SESSION_EXPIRY, SESSION_REFRESH_MARGIN

TEST_HOST = "192.168.1.1"
TEST_URL = f"https://{TEST_HOST}{API_PATH}"
TEST_URL_KEY = ("POST", URL(TEST_URL))
TEST_USER = "admin"
TEST_PASS = "admin01"
TEST_SESSION_ID = "abcdef1234567890abcdef1234567890"


@pytest.fixture
async def api_client():
    """Create a real RutOSAPI with a real aiohttp session."""
    session = aiohttp.ClientSession()
    api = RutOSAPI(TEST_HOST, TEST_USER, TEST_PASS, session)
    yield api
    await session.close()


def _login_response(session_id: str = TEST_SESSION_ID):
    """Return a successful login response payload."""
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "result": [0, {"ubus_rpc_session": session_id}],
    }


def _call_response(data=None, status_code=0):
    """Return a successful ubus call response."""
    result = [status_code, data] if data is not None else [status_code]
    return {"jsonrpc": "2.0", "id": 1, "result": result}


def _error_response(message="Something went wrong"):
    """Return a JSON-RPC error response."""
    return {"jsonrpc": "2.0", "id": 1, "error": {"code": -1, "message": message}}


class TestLogin:
    """Tests for login/authentication."""

    async def test_login_success(self, api_client):
        """Test successful login stores session and sets expiry."""
        with aioresponses() as m:
            m.post(TEST_URL, payload=_login_response())

            await api_client.login()

            assert api_client._ubus_session == TEST_SESSION_ID
            assert api_client._session_expiry > time.monotonic()

    async def test_login_invalid_credentials(self, api_client):
        """Test login with non-zero status raises RutOSAuthError."""
        with aioresponses() as m:
            m.post(TEST_URL, payload={
                "jsonrpc": "2.0", "id": 1,
                "result": [6, {}],
            })

            with pytest.raises(RutOSAuthError, match="status code 6"):
                await api_client.login()

    async def test_login_unexpected_format(self, api_client):
        """Test malformed login response raises RutOSAuthError."""
        with aioresponses() as m:
            m.post(TEST_URL, payload={
                "jsonrpc": "2.0", "id": 1,
                "result": "not-a-list",
            })

            with pytest.raises(RutOSAuthError, match="Unexpected login response"):
                await api_client.login()

    async def test_login_missing_session_id(self, api_client):
        """Test login response without session ID raises RutOSAuthError."""
        with aioresponses() as m:
            m.post(TEST_URL, payload={
                "jsonrpc": "2.0", "id": 1,
                "result": [0, {"other": "data"}],
            })

            with pytest.raises(RutOSAuthError, match="No session ID"):
                await api_client.login()


class TestRequest:
    """Tests for the low-level _request method."""

    async def test_request_connection_error(self, api_client):
        """Test connection error raises RutOSConnectionError."""
        with aioresponses() as m:
            m.post(TEST_URL, exception=aiohttp.ClientConnectionError("refused"))

            with pytest.raises(RutOSConnectionError, match="Cannot connect"):
                await api_client._request("call", [])

    async def test_request_jsonrpc_error(self, api_client):
        """Test JSON-RPC error response raises RutOSAPIError."""
        with aioresponses() as m:
            m.post(TEST_URL, payload=_error_response("bad method"))

            with pytest.raises(RutOSAPIError, match="JSON-RPC error"):
                await api_client._request("call", [])


class TestCall:
    """Tests for the authenticated call method."""

    async def test_call_sends_session_id(self, api_client):
        """Test that authenticated calls include the session ID."""
        with aioresponses() as m:
            m.post(TEST_URL, payload=_login_response())
            m.post(TEST_URL, payload=_call_response({"key": "value"}))

            result = await api_client.call("test", "method")

            assert result == {"key": "value"}
            # Verify the second request included the session
            requests = m.requests[TEST_URL_KEY]
            body = requests[1].kwargs["json"]
            assert body["params"][0] == TEST_SESSION_ID

    async def test_call_returns_data_payload(self, api_client):
        """Test that call extracts the data from [0, data] result."""
        with aioresponses() as m:
            m.post(TEST_URL, payload=_login_response())
            m.post(TEST_URL, payload=_call_response({"result": "ok"}))

            result = await api_client.call("svc", "meth")
            assert result == {"result": "ok"}

    async def test_call_non_zero_status_raises(self, api_client):
        """Test non-zero status code raises RutOSAPIError."""
        with aioresponses() as m:
            m.post(TEST_URL, payload=_login_response())
            m.post(TEST_URL, payload=_call_response(status_code=7))

            with pytest.raises(RutOSAPIError, match="failed with code 7"):
                await api_client.call("svc", "meth")


class TestSessionRetry:
    """Tests for session expired retry logic."""

    async def test_session_expired_retry_success(self, api_client):
        """Test code 6 triggers re-login and successful retry."""
        with aioresponses() as m:
            # Initial login
            m.post(TEST_URL, payload=_login_response("session1"))
            # First call returns expired
            m.post(TEST_URL, payload={
                "jsonrpc": "2.0", "id": 1,
                "result": [JSONRPC_SESSION_EXPIRED],
            })
            # Re-login
            m.post(TEST_URL, payload=_login_response("session2"))
            # Retry succeeds
            m.post(TEST_URL, payload=_call_response({"data": "ok"}))

            result = await api_client.call("svc", "meth")
            assert result == {"data": "ok"}

    async def test_session_expired_retry_fails(self, api_client):
        """Test code 6 → re-login → second failure raises."""
        with aioresponses() as m:
            # Initial login
            m.post(TEST_URL, payload=_login_response("session1"))
            # First call returns expired
            m.post(TEST_URL, payload={
                "jsonrpc": "2.0", "id": 1,
                "result": [JSONRPC_SESSION_EXPIRED],
            })
            # Re-login
            m.post(TEST_URL, payload=_login_response("session2"))
            # Retry also fails
            m.post(TEST_URL, payload=_call_response(status_code=7))

            with pytest.raises(RutOSAPIError, match="failed with code 7"):
                await api_client.call("svc", "meth")


class TestEnsureSession:
    """Tests for session refresh logic."""

    async def test_ensure_session_refreshes_near_expiry(self, api_client):
        """Test session is refreshed when within margin of expiry."""
        with aioresponses() as m:
            # First login
            m.post(TEST_URL, payload=_login_response("session1"))

            await api_client.login()
            assert api_client._ubus_session == "session1"

            # Simulate near-expiry
            api_client._session_expiry = time.monotonic() + SESSION_REFRESH_MARGIN - 1

            # Should trigger refresh
            m.post(TEST_URL, payload=_login_response("session2"))
            session_id = await api_client._ensure_session()
            assert session_id == "session2"

    async def test_ensure_session_reuses_valid(self, api_client):
        """Test no refresh when session is still fresh."""
        with aioresponses() as m:
            m.post(TEST_URL, payload=_login_response())

            await api_client.login()
            # Session should be valid - no additional HTTP calls needed
            session_id = await api_client._ensure_session()
            assert session_id == TEST_SESSION_ID
            # Only 1 request (the login)
            assert len(m.requests[TEST_URL_KEY]) == 1

    async def test_ensure_session_concurrent_callers(self, api_client):
        """Test lock ensures login is called only once for concurrent callers."""
        with aioresponses() as m:
            m.post(TEST_URL, payload=_login_response())

            results = await asyncio.gather(
                api_client._ensure_session(),
                api_client._ensure_session(),
                api_client._ensure_session(),
            )

            # All should get the same session
            assert all(r == TEST_SESSION_ID for r in results)
            # Login called only once
            assert len(m.requests[TEST_URL_KEY]) == 1


class TestGetDeviceInfo:
    """Tests for get_device_info."""

    async def test_get_device_info_parses_correctly(self, api_client):
        """Test parsing of mnf_info and board info."""
        with aioresponses() as m:
            m.post(TEST_URL, payload=_login_response())
            # mnf_info response
            m.post(TEST_URL, payload=_call_response({
                "stdout": "name=RUTX50\nserial=1234567890\nmac=00:1E:42:AA:BB:CC\n",
            }))
            # board info response
            m.post(TEST_URL, payload=_call_response({
                "model": "Teltonika RUTX50",
                "release": {"description": "RUTX_R_00.07.06.1"},
            }))

            info = await api_client.get_device_info()

            assert info["name"] == "RUTX50"
            assert info["serial"] == "1234567890"
            assert info["mac"] == "00:1E:42:AA:BB:CC"
            assert info["firmware"] == "RUTX_R_00.07.06.1"
            assert info["model"] == "Teltonika RUTX50"


class TestGetWanInterfaces:
    """Tests for get_wan_interfaces."""

    async def test_get_wan_interfaces_filters_wan_only(self, api_client):
        """Test that loopback/LAN interfaces are excluded."""
        dump = {
            "interface": [
                {"interface": "loopback", "up": True, "proto": "static", "uptime": 0, "metric": 0},
                {"interface": "lan", "up": True, "proto": "static", "uptime": 0, "metric": 0},
                {"interface": "wan", "up": True, "proto": "dhcp", "uptime": 100, "metric": 10,
                 "ipv4-address": [{"address": "1.2.3.4"}], "device": "eth0", "l3_device": "eth0",
                 "route": [{"target": "0.0.0.0", "mask": 0}]},
                {"interface": "mob1s1a1", "up": False, "proto": "qmi", "uptime": 0, "metric": 20,
                 "device": "wwan0", "l3_device": "wwan0"},
            ]
        }
        with aioresponses() as m:
            m.post(TEST_URL, payload=_login_response())
            m.post(TEST_URL, payload=_call_response(dump))

            interfaces = await api_client.get_wan_interfaces()

            names = [i["name"] for i in interfaces]
            assert "loopback" not in names
            assert "lan" not in names
            assert "wan" in names
            assert "mob1s1a1" in names

    async def test_get_wan_interfaces_sorted_by_metric(self, api_client):
        """Test interfaces are returned sorted by metric ascending."""
        dump = {
            "interface": [
                {"interface": "mob1s1a1", "up": False, "proto": "qmi", "uptime": 0, "metric": 20,
                 "device": "wwan0", "l3_device": "wwan0"},
                {"interface": "wan", "up": True, "proto": "dhcp", "uptime": 100, "metric": 10,
                 "ipv4-address": [{"address": "1.2.3.4"}], "device": "eth0", "l3_device": "eth0",
                 "route": [{"target": "0.0.0.0", "mask": 0}]},
            ]
        }
        with aioresponses() as m:
            m.post(TEST_URL, payload=_login_response())
            m.post(TEST_URL, payload=_call_response(dump))

            interfaces = await api_client.get_wan_interfaces()

            assert interfaces[0]["name"] == "wan"
            assert interfaces[1]["name"] == "mob1s1a1"
            assert interfaces[0]["metric"] < interfaces[1]["metric"]


class TestGetInternetStatus:
    """Tests for get_internet_status."""

    async def test_get_internet_status_true(self, api_client):
        """Test returns True when default route is present."""
        dump = {
            "interface": [{
                "interface": "wan", "up": True, "proto": "dhcp",
                "route": [{"target": "0.0.0.0", "mask": 0}],
            }]
        }
        with aioresponses() as m:
            m.post(TEST_URL, payload=_login_response())
            m.post(TEST_URL, payload=_call_response(dump))

            assert await api_client.get_internet_status() is True

    async def test_get_internet_status_false(self, api_client):
        """Test returns False when no default route."""
        dump = {
            "interface": [{
                "interface": "wan", "up": True, "proto": "dhcp",
                "route": [{"target": "10.0.0.0", "mask": 8}],
            }]
        }
        with aioresponses() as m:
            m.post(TEST_URL, payload=_login_response())
            m.post(TEST_URL, payload=_call_response(dump))

            assert await api_client.get_internet_status() is False


class TestSetInterfaceEnabled:
    """Tests for set_interface_enabled."""

    async def test_set_interface_enabled_up(self, api_client):
        """Test enabling calls network.interface up."""
        with aioresponses() as m:
            m.post(TEST_URL, payload=_login_response())
            m.post(TEST_URL, payload=_call_response())

            await api_client.set_interface_enabled("wan", True)

            requests = m.requests[TEST_URL_KEY]
            body = requests[1].kwargs["json"]
            assert body["params"][1] == "network.interface"
            assert body["params"][2] == "up"

    async def test_set_interface_enabled_down(self, api_client):
        """Test disabling calls network.interface down."""
        with aioresponses() as m:
            m.post(TEST_URL, payload=_login_response())
            m.post(TEST_URL, payload=_call_response())

            await api_client.set_interface_enabled("wan", False)

            requests = m.requests[TEST_URL_KEY]
            body = requests[1].kwargs["json"]
            assert body["params"][2] == "down"


class TestSetFailoverOrder:
    """Tests for set_failover_order."""

    async def test_set_failover_order(self, api_client):
        """Test sets UCI metrics, commits, and reloads network."""
        with aioresponses() as m:
            m.post(TEST_URL, payload=_login_response())
            # uci set for wan (metric=10)
            m.post(TEST_URL, payload=_call_response())
            # uci set for mob1s1a1 (metric=20)
            m.post(TEST_URL, payload=_call_response())
            # uci commit
            m.post(TEST_URL, payload=_call_response())
            # network reload
            m.post(TEST_URL, payload=_call_response())

            await api_client.set_failover_order(["wan", "mob1s1a1"])

            requests = m.requests[TEST_URL_KEY]
            # Should have 5 total requests (login + 2 sets + commit + reload)
            assert len(requests) == 5

            # Verify UCI set calls
            uci_set_1 = requests[1].kwargs["json"]
            assert uci_set_1["params"][1] == "uci"
            assert uci_set_1["params"][2] == "set"
            assert uci_set_1["params"][3]["values"]["metric"] == "10"

            uci_set_2 = requests[2].kwargs["json"]
            assert uci_set_2["params"][3]["values"]["metric"] == "20"

            # Verify commit
            commit = requests[3].kwargs["json"]
            assert commit["params"][2] == "commit"
