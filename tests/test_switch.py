"""Tests for the RutOS switch platform."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from custom_components.rutos.api import RutOSAPIError
from custom_components.rutos.coordinator import RutOSDataUpdateCoordinator
from custom_components.rutos.switch import RutOSInterfaceSwitch


class TestRutOSInterfaceSwitch:
    """Tests for the WAN interface switch."""

    def test_creates_per_interface(self, mock_coordinator: RutOSDataUpdateCoordinator):
        """Test one switch is created per WAN interface."""
        switches = [
            RutOSInterfaceSwitch(mock_coordinator, iface["name"])
            for iface in mock_coordinator.data.wan_interfaces
        ]
        assert len(switches) == 4
        names = {s._interface_name for s in switches}
        assert names == {"mob1s1a1", "mob1s2a1", "wan1", "wan2"}

    def test_is_on_reflects_enabled_state(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Test is_on matches interface enabled field."""
        switch = RutOSInterfaceSwitch(mock_coordinator, "mob1s1a1")
        assert switch.is_on is True

    async def test_turn_on_calls_api(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Test turn_on calls set_interface_enabled(name, True) + refresh."""
        mock_coordinator.async_request_refresh = AsyncMock()
        switch = RutOSInterfaceSwitch(mock_coordinator, "wan1")

        await switch.async_turn_on()

        mock_coordinator.api.set_interface_enabled.assert_awaited_once_with("wan1", True)
        mock_coordinator.async_request_refresh.assert_awaited_once()

    async def test_turn_off_calls_api(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Test turn_off calls set_interface_enabled(name, False) + refresh."""
        mock_coordinator.async_request_refresh = AsyncMock()
        switch = RutOSInterfaceSwitch(mock_coordinator, "mob1s1a1")

        await switch.async_turn_off()

        mock_coordinator.api.set_interface_enabled.assert_awaited_once_with(
            "mob1s1a1", False
        )
        mock_coordinator.async_request_refresh.assert_awaited_once()

    async def test_api_error_propagates(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Test API errors are not silently swallowed."""
        mock_coordinator.api.set_interface_enabled.side_effect = RutOSAPIError("fail")
        mock_coordinator.async_request_refresh = AsyncMock()
        switch = RutOSInterfaceSwitch(mock_coordinator, "wan1")

        with pytest.raises(RutOSAPIError):
            await switch.async_turn_on()

    def test_is_on_returns_false_when_interface_not_found(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Test is_on returns False when interface is not found in data."""
        switch = RutOSInterfaceSwitch(mock_coordinator, "nonexistent")
        assert switch.is_on is False

    def test_unique_id_format(self, mock_coordinator: RutOSDataUpdateCoordinator):
        """Test unique_id follows {serial}_{interface}_enabled pattern."""
        switch = RutOSInterfaceSwitch(mock_coordinator, "wan1")
        assert switch.unique_id == "1234567890_wan1_enabled"
