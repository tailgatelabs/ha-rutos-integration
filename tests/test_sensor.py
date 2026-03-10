"""Tests for the RutOS sensor platform."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from homeassistant.core import HomeAssistant

from custom_components.rutos.const import DOMAIN
from custom_components.rutos.coordinator import RutOSData, RutOSDataUpdateCoordinator
from custom_components.rutos.sensor import (
    DATA_LIMIT_SENSORS,
    INTERFACE_SENSORS,
    RutOSActiveWANSensor,
    RutOSDataLimitSensor,
    RutOSSensorEntity,
)


class TestRutOSSensorEntity:
    """Tests for per-interface sensor entities."""

    def test_creates_expected_entity_count(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Test 4 sensors per interface + 1 active WAN sensor."""
        interfaces = mock_coordinator.data.wan_interfaces
        expected = len(interfaces) * len(INTERFACE_SENSORS) + 1
        assert expected == 9  # 2 interfaces * 4 sensors + 1 active WAN

    def test_status_sensor_value(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Test status sensor returns up/down."""
        desc = INTERFACE_SENSORS[0]  # status
        sensor = RutOSSensorEntity(mock_coordinator, desc, "wan")
        assert sensor.native_value == "up"

        sensor_down = RutOSSensorEntity(mock_coordinator, desc, "mob1s1a1")
        assert sensor_down.native_value == "down"

    def test_ip_address_sensor_value(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Test IP address sensor returns IP or None."""
        desc = INTERFACE_SENSORS[1]  # ip_address
        sensor = RutOSSensorEntity(mock_coordinator, desc, "wan")
        assert sensor.native_value == "192.168.1.100"

        sensor_none = RutOSSensorEntity(mock_coordinator, desc, "mob1s1a1")
        assert sensor_none.native_value is None

    def test_uptime_sensor_value(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Test uptime sensor returns seconds."""
        desc = INTERFACE_SENSORS[3]  # uptime
        sensor = RutOSSensorEntity(mock_coordinator, desc, "wan")
        assert sensor.native_value == 3600

    def test_unique_id_format(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Test unique_id follows {serial}_{interface}_{key} pattern."""
        desc = INTERFACE_SENSORS[0]
        sensor = RutOSSensorEntity(mock_coordinator, desc, "wan")
        assert sensor.unique_id == "1234567890_wan_status"

    def test_device_info(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Test device_info contains correct identifiers and manufacturer."""
        desc = INTERFACE_SENSORS[0]
        sensor = RutOSSensorEntity(mock_coordinator, desc, "wan")
        info = sensor.device_info

        assert (DOMAIN, "1234567890") in info["identifiers"]
        assert info["manufacturer"] == "Teltonika"
        assert info["name"] == "RUTX50"

    def test_missing_interface_returns_none(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Test sensor for non-existent interface returns None."""
        desc = INTERFACE_SENSORS[0]
        sensor = RutOSSensorEntity(mock_coordinator, desc, "nonexistent")
        assert sensor.native_value is None

    def test_proto_sensor_value(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Test protocol sensor returns the proto field."""
        desc = INTERFACE_SENSORS[2]  # proto
        sensor = RutOSSensorEntity(mock_coordinator, desc, "wan")
        assert sensor.native_value == "dhcp"

        sensor_mob = RutOSSensorEntity(mock_coordinator, desc, "mob1s1a1")
        assert sensor_mob.native_value == "qmi"


class TestRutOSActiveWANSensor:
    """Tests for the active WAN sensor."""

    def test_active_wan_returns_first_up(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Test returns name of first 'up' interface."""
        sensor = RutOSActiveWANSensor(mock_coordinator)
        assert sensor.native_value == "wan"

    def test_active_wan_none_when_all_down(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Test returns None when all interfaces are down."""
        for iface in mock_coordinator.data.wan_interfaces:
            iface["status"] = "down"

        sensor = RutOSActiveWANSensor(mock_coordinator)
        assert sensor.native_value is None

    def test_unique_id(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Test unique_id is {serial}_active_wan."""
        sensor = RutOSActiveWANSensor(mock_coordinator)
        assert sensor.unique_id == "1234567890_active_wan"


class TestRutOSDataLimitSensor:
    """Tests for data limit sensor entities."""

    def test_data_used_value(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Test data used sensor returns bytes used."""
        desc = DATA_LIMIT_SENSORS[0]  # data_used
        sensor = RutOSDataLimitSensor(mock_coordinator, desc, "limit1")
        assert sensor.native_value == 2_500_000_000

    def test_data_limit_value(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Test data limit sensor returns limit in bytes."""
        desc = DATA_LIMIT_SENSORS[1]  # data_limit
        sensor = RutOSDataLimitSensor(mock_coordinator, desc, "limit1")
        assert sensor.native_value == 5_000_000_000

    def test_data_usage_percent(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Test data usage percent is calculated correctly."""
        desc = DATA_LIMIT_SENSORS[2]  # data_usage_percent
        sensor = RutOSDataLimitSensor(mock_coordinator, desc, "limit1")
        assert sensor.native_value == 50.0

    def test_data_usage_percent_zero_limit(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Test data usage percent returns None when limit is 0."""
        mock_coordinator.data.data_limit[0]["data_limit"] = 0
        desc = DATA_LIMIT_SENSORS[2]
        sensor = RutOSDataLimitSensor(mock_coordinator, desc, "limit1")
        assert sensor.native_value is None

    def test_missing_limit_returns_none(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Test returns None when limit not found."""
        desc = DATA_LIMIT_SENSORS[0]
        sensor = RutOSDataLimitSensor(mock_coordinator, desc, "nonexistent")
        assert sensor.native_value is None

    def test_unique_id_format(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Test unique_id follows {serial}_{limit}_{key} pattern."""
        desc = DATA_LIMIT_SENSORS[0]
        sensor = RutOSDataLimitSensor(mock_coordinator, desc, "limit1")
        assert sensor.unique_id == "1234567890_limit1_data_used"
