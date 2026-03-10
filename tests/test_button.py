"""Tests for the RutOS button platform."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from custom_components.rutos.api import RutOSAPIError
from custom_components.rutos.button import RutOSClearDataUsageButton, RutOSModemRebootButton
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


class TestRutOSModemRebootButton:
    """Tests for the modem reboot button."""

    def test_unique_id(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Test unique_id is {serial}_{modem}_reboot."""
        button = RutOSModemRebootButton(mock_coordinator, "modem1")
        assert button.unique_id == "1234567890_modem1_reboot"

    async def test_press_calls_api(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Test pressing the button calls reboot_modem + refresh."""
        mock_coordinator.async_request_refresh = AsyncMock()
        button = RutOSModemRebootButton(mock_coordinator, "modem1")

        await button.async_press()

        mock_coordinator.api.reboot_modem.assert_awaited_once_with("modem1")
        mock_coordinator.async_request_refresh.assert_awaited_once()

    async def test_api_error_propagates(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Test API errors are not swallowed."""
        mock_coordinator.api.reboot_modem.side_effect = RutOSAPIError("fail")
        mock_coordinator.async_request_refresh = AsyncMock()
        button = RutOSModemRebootButton(mock_coordinator, "modem1")

        with pytest.raises(RutOSAPIError):
            await button.async_press()

    def test_translation_placeholders(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Test translation placeholders include modem id."""
        button = RutOSModemRebootButton(mock_coordinator, "modem1")
        assert button.translation_placeholders == {"modem": "modem1"}
