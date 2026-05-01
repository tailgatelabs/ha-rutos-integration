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


def _chain(members: list[dict], mode: str = "failover") -> dict:
    """Build an active-failover-chain dict for tests."""
    return {"policy_id": "mwan_default", "mode": mode, "members": members}


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
        mock_coordinator.data.failover_chain = _chain(
            [
                {"id": "mob1s1a1_member_mwan", "interface": "mob1s1a1", "metric": "1"},
                {"id": "mob1s2a1_member_mwan", "interface": "mob1s2a1", "metric": "2"},
                {"id": "wan1_member_mwan", "interface": "wan1", "metric": "3"},
                {"id": "wan2_member_mwan", "interface": "wan2", "metric": "4"},
            ]
        )
        entity = RutOSFailoverSelect(mock_coordinator, GROUPS)
        assert entity.current_option == "Cellular, Starlink, WiFi"

    def test_current_option_starlink_first(self, mock_coordinator):
        """Test current_option when starlink has lowest metric."""
        mock_coordinator.data.failover_chain = _chain(
            [
                {"id": "wan1_member_mwan", "interface": "wan1", "metric": "1"},
                {"id": "mob1s1a1_member_mwan", "interface": "mob1s1a1", "metric": "2"},
                {"id": "mob1s2a1_member_mwan", "interface": "mob1s2a1", "metric": "3"},
                {"id": "wan2_member_mwan", "interface": "wan2", "metric": "4"},
            ]
        )
        entity = RutOSFailoverSelect(mock_coordinator, GROUPS)
        assert entity.current_option == "Starlink, Cellular, WiFi"

    def test_current_option_none_when_missing_interface(self, mock_coordinator):
        """Test current_option returns None when interface is missing."""
        mock_coordinator.data.failover_chain = _chain(
            [{"id": "mob1s1a1_member_mwan", "interface": "mob1s1a1", "metric": "1"}]
        )
        entity = RutOSFailoverSelect(mock_coordinator, GROUPS)
        assert entity.current_option is None

    @pytest.mark.asyncio
    async def test_select_option_expands_groups(self, mock_coordinator):
        """Test that selecting an option resolves member IDs from the active policy."""
        mock_coordinator.async_request_refresh = AsyncMock()
        entity = RutOSFailoverSelect(mock_coordinator, GROUPS)
        await entity.async_select_option("Starlink, Cellular, WiFi")

        mock_coordinator.api.set_failover_order.assert_awaited_once_with(
            [
                "wan1_member_mwan",
                "mob1s1a1_member_mwan",
                "mob1s2a1_member_mwan",
                "wan2_member_mwan",
            ]
        )
        mock_coordinator.async_request_refresh.assert_awaited_once()

    def test_available_when_groups_active(self, mock_coordinator):
        """Test entity is available when at least 2 groups have active interfaces."""
        entity = RutOSFailoverSelect(mock_coordinator, GROUPS)
        assert entity.available is True

    def test_unavailable_when_too_few_groups_active(self, mock_coordinator):
        """Test entity is unavailable when fewer than 2 groups are active."""
        for iface in mock_coordinator.data.wan_interfaces:
            if iface["name"] in ("wan1", "wan2"):
                iface["status"] = "down"
        entity = RutOSFailoverSelect(mock_coordinator, GROUPS)
        assert entity.available is False

    def test_inactive_group_excluded_from_options(self, mock_coordinator):
        """Test that groups with all interfaces down are excluded from options."""
        for iface in mock_coordinator.data.wan_interfaces:
            if iface["name"] == "wan2":
                iface["status"] = "down"
        entity = RutOSFailoverSelect(mock_coordinator, GROUPS)
        assert len(entity.options) == 2
        assert "Cellular, Starlink" in entity.options
        assert "Starlink, Cellular" in entity.options
        assert all("WiFi" not in opt for opt in entity.options)

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


@pytest.mark.asyncio
async def test_async_setup_entry_skips_in_balance_mode(hass, mock_coordinator):
    """Test that no entity is created when the active policy is balance mode."""
    from custom_components.rutos.const import CONF_FAILOVER_GROUPS
    from custom_components.rutos.select import async_setup_entry

    mock_coordinator.data.failover_chain = _chain(
        [
            {"id": "wan1_member_balance", "interface": "wan1", "metric": "1"},
            {"id": "mob1s1a1_member_balance", "interface": "mob1s1a1", "metric": "1"},
        ],
        mode="balance",
    )

    entry = AsyncMock()
    entry.options = {
        CONF_FAILOVER_GROUPS: {"Cellular": ["mob1s1a1"], "Starlink": ["wan1"]}
    }
    entry.runtime_data = mock_coordinator
    add_entities = AsyncMock()

    await async_setup_entry(hass, entry, add_entities)
    add_entities.assert_not_called()
