"""Tests for the RutOS button platform."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from custom_components.rutos.api import RutOSAPIError
from custom_components.rutos.button import (
    RutOSClearDataUsageButton,
    RutOSModemRebootButton,
    RutOSModemSwitchSimButton,
)
from custom_components.rutos.coordinator import RutOSDataUpdateCoordinator


class TestRutOSClearDataUsageButton:
    """Tests for the clear data usage button."""

    def test_unique_id(self, mock_coordinator: RutOSDataUpdateCoordinator):
        """Test unique_id is {serial}_clear_data_usage."""
        button = RutOSClearDataUsageButton(mock_coordinator)
        assert button.unique_id == "1234567890_clear_data_usage"

    async def test_press_calls_api(self, mock_coordinator: RutOSDataUpdateCoordinator):
        """Test pressing the button calls clear_data_usage + refresh."""
        mock_coordinator.async_request_refresh = AsyncMock()
        button = RutOSClearDataUsageButton(mock_coordinator)

        await button.async_press()

        mock_coordinator.api.clear_data_usage.assert_awaited_once()
        mock_coordinator.async_request_refresh.assert_awaited_once()


class TestRutOSModemRebootButton:
    """Tests for the modem reboot button."""

    def test_unique_id(self, mock_coordinator: RutOSDataUpdateCoordinator):
        """Test unique_id is {serial}_{modem}_reboot."""
        button = RutOSModemRebootButton(mock_coordinator, "modem1")
        assert button.unique_id == "1234567890_modem1_reboot"

    async def test_press_calls_api(self, mock_coordinator: RutOSDataUpdateCoordinator):
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

    def test_single_modem_no_placeholder(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Single modem: base translation key, no placeholder (issue #26)."""
        button = RutOSModemRebootButton(mock_coordinator, "modem1")
        assert button.translation_key == "modem_reboot"
        assert not button.translation_placeholders

    def test_multi_modem_uses_multi_key(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Multi modem: _multi translation key with {modem} placeholder."""
        mock_coordinator.data.modems = [{"id": "2-1"}, {"id": "3-1"}]
        button = RutOSModemRebootButton(mock_coordinator, "2-1")
        assert button.translation_key == "modem_reboot_multi"
        assert button.translation_placeholders == {"modem": "2-1"}


class TestRutOSModemSwitchSimButton:
    """Tests for the modem switch SIM button (issue #26 naming)."""

    def test_unique_id(self, mock_coordinator: RutOSDataUpdateCoordinator):
        """Test unique_id is {serial}_{modem}_switch_sim."""
        button = RutOSModemSwitchSimButton(mock_coordinator, "modem1")
        assert button.unique_id == "1234567890_modem1_switch_sim"

    def test_single_modem_no_placeholder(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Single modem: base translation key, no placeholder."""
        button = RutOSModemSwitchSimButton(mock_coordinator, "modem1")
        assert button.translation_key == "modem_switch_sim"
        assert not button.translation_placeholders

    def test_multi_modem_uses_multi_key(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Multi modem: _multi translation key with placeholder."""
        mock_coordinator.data.modems = [{"id": "2-1"}, {"id": "3-1"}]
        button = RutOSModemSwitchSimButton(mock_coordinator, "2-1")
        assert button.translation_key == "modem_switch_sim_multi"
        assert button.translation_placeholders == {"modem": "2-1"}
