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

    def test_single_modem_no_placeholder(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Single modem: base translation key, no placeholder (issue #26)."""
        sensor = RutOSModemRoamingSensor(mock_coordinator, "modem1")
        assert sensor.translation_key == "modem_roaming"
        assert not sensor.translation_placeholders

    def test_multi_modem_uses_multi_key(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Multi modem: _multi translation key with {modem} placeholder."""
        mock_coordinator.data.modems = [{"id": "2-1"}, {"id": "3-1"}]
        sensor = RutOSModemRoamingSensor(mock_coordinator, "2-1")
        assert sensor.translation_key == "modem_roaming_multi"
        assert sensor.translation_placeholders == {"modem": "2-1"}
