"""Tests for the RutOS button platform."""

from __future__ import annotations

from unittest.mock import AsyncMock

from custom_components.rutos.button import RutOSClearDataUsageButton
from custom_components.rutos.coordinator import RutOSDataUpdateCoordinator


class TestRutOSClearDataUsageButton:
    """Tests for the clear data usage button."""

    def test_unique_id(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Test unique_id is {serial}_clear_data_usage."""
        button = RutOSClearDataUsageButton(mock_coordinator)
        assert button.unique_id == "1234567890_clear_data_usage"

    async def test_press_calls_api(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Test pressing the button calls clear_data_usage + refresh."""
        mock_coordinator.async_request_refresh = AsyncMock()
        button = RutOSClearDataUsageButton(mock_coordinator)

        await button.async_press()

        mock_coordinator.api.clear_data_usage.assert_awaited_once()
        mock_coordinator.async_request_refresh.assert_awaited_once()
