"""Tests for the RutOS device tracker platform."""

from __future__ import annotations

from homeassistant.components.device_tracker.const import SourceType

from custom_components.rutos.coordinator import RutOSDataUpdateCoordinator
from custom_components.rutos.device_tracker import RutOSDeviceTracker


class TestRutOSDeviceTracker:
    """Tests for the GPS device tracker."""

    def test_latitude(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Test latitude from GPS data."""
        tracker = RutOSDeviceTracker(mock_coordinator)
        assert tracker.latitude == 37.7749

    def test_longitude(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Test longitude from GPS data."""
        tracker = RutOSDeviceTracker(mock_coordinator)
        assert tracker.longitude == -122.4194

    def test_location_accuracy(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Test location accuracy from GPS data."""
        tracker = RutOSDeviceTracker(mock_coordinator)
        assert tracker.location_accuracy == 5

    def test_source_type(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Test source type is GPS."""
        tracker = RutOSDeviceTracker(mock_coordinator)
        assert tracker.source_type == SourceType.GPS

    def test_unique_id(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Test unique_id is {serial}_gps_location."""
        tracker = RutOSDeviceTracker(mock_coordinator)
        assert tracker.unique_id == "1234567890_gps_location"

    def test_no_gps_data_returns_none(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Test returns None when no GPS data available."""
        mock_coordinator.data.gps_position = None
        tracker = RutOSDeviceTracker(mock_coordinator)
        assert tracker.latitude is None
        assert tracker.longitude is None
        assert tracker.location_accuracy == 0
