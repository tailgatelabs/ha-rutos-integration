"""Tests for the RutOS binary sensor platform."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass

from custom_components.rutos.binary_sensor import (
    RutOSInternetConnectivitySensor,
    RutOSModemRoamingSensor,
)
from custom_components.rutos.coordinator import RutOSDataUpdateCoordinator


class TestRutOSInternetConnectivitySensor:
    """Tests for the internet connectivity binary sensor."""

    def test_is_on_when_internet_available(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Test is_on is True when internet is available."""
        mock_coordinator.data.internet_available = True
        sensor = RutOSInternetConnectivitySensor(mock_coordinator)
        assert sensor.is_on is True

    def test_is_off_when_no_internet(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Test is_on is False when no internet."""
        mock_coordinator.data.internet_available = False
        sensor = RutOSInternetConnectivitySensor(mock_coordinator)
        assert sensor.is_on is False

    def test_device_class_connectivity(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Test device class is CONNECTIVITY."""
        sensor = RutOSInternetConnectivitySensor(mock_coordinator)
        assert sensor.device_class == BinarySensorDeviceClass.CONNECTIVITY

    def test_unique_id(self, mock_coordinator: RutOSDataUpdateCoordinator):
        """Test unique_id is {serial}_internet_connectivity."""
        sensor = RutOSInternetConnectivitySensor(mock_coordinator)
        assert sensor.unique_id == "1234567890_internet_connectivity"


class TestRutOSModemRoamingSensor:
    """Tests for the modem roaming binary sensor."""

    def test_is_off_when_not_roaming(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Test is_on is False when not roaming."""
        mock_coordinator.data.modem_status = [
            {"id": "modem1", "operator": "T-Mobile", "roaming": False},
        ]
        sensor = RutOSModemRoamingSensor(mock_coordinator, "modem1")
        assert sensor.is_on is False

    def test_is_on_when_roaming(self, mock_coordinator: RutOSDataUpdateCoordinator):
        """Test is_on is True when roaming."""
        mock_coordinator.data.modem_status = [
            {"id": "modem1", "operator": "AT&T", "roaming": True},
        ]
        sensor = RutOSModemRoamingSensor(mock_coordinator, "modem1")
        assert sensor.is_on is True

    def test_missing_modem_returns_none(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Test returns None when modem not found."""
        sensor = RutOSModemRoamingSensor(mock_coordinator, "nonexistent")
        assert sensor.is_on is None

    def test_unique_id(self, mock_coordinator: RutOSDataUpdateCoordinator):
        """Test unique_id follows {serial}_{modem}_roaming pattern."""
        sensor = RutOSModemRoamingSensor(mock_coordinator, "modem1")
        assert sensor.unique_id == "1234567890_modem1_roaming"
