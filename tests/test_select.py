"""Tests for the RutOS failover priority select entity."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from custom_components.rutos.select import RutOSFailoverSelect


GROUPS = {
    "Cellular": ["mob1s1a1", "mob1s2a1"],
    "Starlink": ["wan1"],
    "WiFi": ["wan2"],
}


class TestRutOSFailoverSelect:
    """Tests for the failover priority select entity."""

    def test_options_are_all_permutations(self, mock_coordinator):
        """Test that options include all permutations of group labels."""
        entity = RutOSFailoverSelect(mock_coordinator, GROUPS)
        assert len(entity.options) == 6
        assert "Cellular, Starlink, WiFi" in entity.options
        assert "Starlink, Cellular, WiFi" in entity.options
        assert "WiFi, Cellular, Starlink" in entity.options

    def test_current_option_cellular_first(self, mock_coordinator):
        """Test current_option when cellular has lowest metric."""
        mock_coordinator.data.failover_members = [
            {"interface": "mob1s1a1", "metric": "1"},
            {"interface": "mob1s2a1", "metric": "2"},
            {"interface": "wan1", "metric": "3"},
            {"interface": "wan2", "metric": "4"},
        ]
        entity = RutOSFailoverSelect(mock_coordinator, GROUPS)
        assert entity.current_option == "Cellular, Starlink, WiFi"

    def test_current_option_starlink_first(self, mock_coordinator):
        """Test current_option when starlink has lowest metric."""
        mock_coordinator.data.failover_members = [
            {"interface": "wan1", "metric": "1"},
            {"interface": "mob1s1a1", "metric": "2"},
            {"interface": "mob1s2a1", "metric": "3"},
            {"interface": "wan2", "metric": "4"},
        ]
        entity = RutOSFailoverSelect(mock_coordinator, GROUPS)
        assert entity.current_option == "Starlink, Cellular, WiFi"

    def test_current_option_none_when_missing_interface(self, mock_coordinator):
        """Test current_option returns None when interface is missing."""
        mock_coordinator.data.failover_members = [
            {"interface": "mob1s1a1", "metric": "1"},
        ]
        entity = RutOSFailoverSelect(mock_coordinator, GROUPS)
        assert entity.current_option is None

    @pytest.mark.asyncio
    async def test_select_option_expands_groups(self, mock_coordinator):
        """Test that selecting an option expands groups into interface list."""
        mock_coordinator.async_request_refresh = AsyncMock()
        entity = RutOSFailoverSelect(mock_coordinator, GROUPS)
        await entity.async_select_option("Starlink, Cellular, WiFi")

        mock_coordinator.api.set_failover_order.assert_awaited_once_with(
            ["wan1", "mob1s1a1", "mob1s2a1", "wan2"]
        )
        mock_coordinator.async_request_refresh.assert_awaited_once()

    def test_available_when_interfaces_match(self, mock_coordinator):
        """Test entity is available when configured interfaces exist on router."""
        mock_coordinator.data.failover_members = [
            {"interface": "mob1s1a1", "metric": "1"},
            {"interface": "mob1s2a1", "metric": "2"},
            {"interface": "wan1", "metric": "3"},
            {"interface": "wan2", "metric": "4"},
            {"interface": "wan3", "metric": "5"},
        ]
        entity = RutOSFailoverSelect(mock_coordinator, GROUPS)
        assert entity.available is True

    def test_unavailable_when_interface_missing(self, mock_coordinator):
        """Test entity is unavailable when a configured interface is gone."""
        mock_coordinator.data.failover_members = [
            {"interface": "mob1s1a1", "metric": "1"},
        ]
        entity = RutOSFailoverSelect(mock_coordinator, GROUPS)
        assert entity.available is False

    def test_unique_id_format(self, mock_coordinator):
        """Test unique_id includes serial and suffix."""
        entity = RutOSFailoverSelect(mock_coordinator, GROUPS)
        assert entity.unique_id == "1234567890_failover_priority"

    def test_two_groups_only(self, mock_coordinator):
        """Test with only two groups."""
        groups = {"Cellular": ["mob1s1a1"], "Starlink": ["wan1"]}
        entity = RutOSFailoverSelect(mock_coordinator, groups)
        assert len(entity.options) == 2
        assert "Cellular, Starlink" in entity.options
        assert "Starlink, Cellular" in entity.options
