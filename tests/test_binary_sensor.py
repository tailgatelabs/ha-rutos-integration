"""Tests for the RutOS binary sensor platform."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass

from custom_components.rutos.binary_sensor import RutOSInternetConnectivitySensor
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

    def test_unique_id(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Test unique_id is {serial}_internet_connectivity."""
        sensor = RutOSInternetConnectivitySensor(mock_coordinator)
        assert sensor.unique_id == "1234567890_internet_connectivity"
