"""Tests for the RutOS sensor platform."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

from custom_components.rutos.const import DOMAIN
from custom_components.rutos.coordinator import RutOSDataUpdateCoordinator
from custom_components.rutos.sensor import (
    DATA_LIMIT_SENSORS,
    GPS_SENSORS,
    INTERFACE_SENSORS,
    MODEM_SIGNAL_SENSORS,
    MODEM_STATUS_SENSORS,
    RutOSActiveWANSensor,
    RutOSConnectedSinceSensor,
    RutOSDataLimitSensor,
    RutOSGPSSensorEntity,
    RutOSModemSignalSensor,
    RutOSModemStatusSensor,
    RutOSSensorEntity,
    _format_bands,
)

_DT_UTCNOW = "custom_components.rutos.sensor.dt_util.utcnow"


def _bands_desc():
    """Locate the bands entity description by key."""
    return next(d for d in MODEM_SIGNAL_SENSORS if d.key == "bands")


def _signal_desc(key: str):
    """Locate a modem signal entity description by key."""
    return next(d for d in MODEM_SIGNAL_SENSORS if d.key == key)


def _band_desc():
    """Locate the legacy single-band entity description by key."""
    return next(d for d in MODEM_SIGNAL_SENSORS if d.key == "band")


class TestRutOSSensorEntity:
    """Tests for per-interface sensor entities."""

    def test_creates_expected_entity_count(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Test 4 sensors per interface + 1 active WAN sensor."""
        interfaces = mock_coordinator.data.wan_interfaces
        expected = len(interfaces) * len(INTERFACE_SENSORS) + 1
        assert expected == 17  # 4 interfaces * 4 sensors + 1 active WAN

    def test_status_sensor_value(self, mock_coordinator: RutOSDataUpdateCoordinator):
        """Test status sensor returns up/down."""
        desc = INTERFACE_SENSORS[0]  # status
        sensor = RutOSSensorEntity(mock_coordinator, desc, "wan1")
        assert sensor.native_value == "up"

        sensor_mob = RutOSSensorEntity(mock_coordinator, desc, "mob1s1a1")
        assert sensor_mob.native_value == "up"

    def test_ip_address_sensor_value(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Test IP address sensor returns IP or None."""
        desc = INTERFACE_SENSORS[1]  # ip_address
        sensor = RutOSSensorEntity(mock_coordinator, desc, "wan1")
        assert sensor.native_value == "192.168.1.100"

        sensor_mob = RutOSSensorEntity(mock_coordinator, desc, "mob1s1a1")
        assert sensor_mob.native_value == "10.0.0.1"

    def test_connected_since_is_floored_timestamp(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Issue #51: uptime is reported as a connected-since minute."""
        desc = INTERFACE_SENSORS[3]  # uptime
        sensor = RutOSConnectedSinceSensor(mock_coordinator, desc, "wan1")
        now = datetime(2026, 10, 28, 12, 0, 45, tzinfo=UTC)
        with patch(_DT_UTCNOW, return_value=now):
            assert sensor.native_value == datetime(2026, 10, 28, 10, 0, tzinfo=UTC)

    def test_connected_since_stable_across_polls(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Poll jitter across a minute boundary doesn't change the state."""
        desc = INTERFACE_SENSORS[3]
        sensor = RutOSConnectedSinceSensor(mock_coordinator, desc, "wan1")
        iface = next(
            i for i in mock_coordinator.data.wan_interfaces if i["name"] == "wan1"
        )
        start = datetime(2026, 10, 28, 12, 1, 0, tzinfo=UTC)
        with patch(_DT_UTCNOW, return_value=start):
            assert sensor.native_value == datetime(2026, 10, 28, 10, 1, tzinfo=UTC)
        # 30 s later the router reports 32 s more uptime: the computed connect
        # time slips back 2 s to 10:00:58, across a minute boundary.
        iface["uptime"] = 7232
        with patch(_DT_UTCNOW, return_value=start.replace(second=30)):
            assert sensor.native_value == datetime(2026, 10, 28, 10, 1, tzinfo=UTC)

    def test_connected_since_moves_on_reconnect(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """A reset uptime yields a new connected-since time."""
        desc = INTERFACE_SENSORS[3]
        sensor = RutOSConnectedSinceSensor(mock_coordinator, desc, "wan1")
        iface = next(
            i for i in mock_coordinator.data.wan_interfaces if i["name"] == "wan1"
        )
        now = datetime(2026, 10, 28, 12, 0, 0, tzinfo=UTC)
        with patch(_DT_UTCNOW, return_value=now):
            assert sensor.native_value == datetime(2026, 10, 28, 10, 0, tzinfo=UTC)
            iface["uptime"] = 300
            assert sensor.native_value == datetime(2026, 10, 28, 11, 55, tzinfo=UTC)

    def test_connected_since_none_when_down_or_zero(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Down interfaces and zero uptime report no timestamp."""
        desc = INTERFACE_SENSORS[3]
        sensor = RutOSConnectedSinceSensor(mock_coordinator, desc, "wan1")
        iface = next(
            i for i in mock_coordinator.data.wan_interfaces if i["name"] == "wan1"
        )
        iface["uptime"] = 0
        assert sensor.native_value is None
        iface["uptime"] = 7200
        iface["status"] = "down"
        assert sensor.native_value is None
        missing = RutOSConnectedSinceSensor(mock_coordinator, desc, "nonexistent")
        assert missing.native_value is None

    def test_protocol_disabled_by_default(self):
        """Issue #52: static protocol sensor starts disabled."""
        desc = next(d for d in INTERFACE_SENSORS if d.key == "proto")
        assert desc.entity_registry_enabled_default is False

    def test_unique_id_format(self, mock_coordinator: RutOSDataUpdateCoordinator):
        """Test unique_id follows {serial}_{interface}_{key} pattern."""
        desc = INTERFACE_SENSORS[0]
        sensor = RutOSSensorEntity(mock_coordinator, desc, "wan1")
        assert sensor.unique_id == "1234567890_wan1_status"

    def test_label_overrides_placeholder_keeps_unique_id(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Issue #18: router GUI label drives display; UCI id drives unique_id."""
        desc = INTERFACE_SENSORS[0]
        sensor = RutOSSensorEntity(mock_coordinator, desc, "wan2", "wifi1")
        assert sensor.unique_id == "1234567890_wan2_status"
        assert sensor.translation_placeholders == {"interface": "wifi1"}

    def test_label_defaults_to_interface_name(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """When no label is passed, placeholder falls back to UCI id."""
        desc = INTERFACE_SENSORS[0]
        sensor = RutOSSensorEntity(mock_coordinator, desc, "wan1")
        assert sensor.translation_placeholders == {"interface": "wan1"}

    def test_device_info(self, mock_coordinator: RutOSDataUpdateCoordinator):
        """Test device_info contains correct identifiers and manufacturer."""
        desc = INTERFACE_SENSORS[0]
        sensor = RutOSSensorEntity(mock_coordinator, desc, "wan1")
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

    def test_proto_sensor_value(self, mock_coordinator: RutOSDataUpdateCoordinator):
        """Test protocol sensor returns the proto field."""
        desc = INTERFACE_SENSORS[2]  # proto
        sensor = RutOSSensorEntity(mock_coordinator, desc, "wan1")
        assert sensor.native_value == "dhcp"

        sensor_mob = RutOSSensorEntity(mock_coordinator, desc, "mob1s1a1")
        assert sensor_mob.native_value == "qmi"


class TestRutOSActiveWANSensor:
    """Tests for the active WAN sensor."""

    def test_active_wan_returns_label_when_configured(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Test returns human-readable label for the active interface."""
        labels = {"mob1s1a1": "Cellular", "wan1": "Starlink"}
        sensor = RutOSActiveWANSensor(mock_coordinator, labels)
        assert sensor.native_value == "Cellular"

    def test_active_wan_returns_name_without_label(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Test returns raw interface name when no label is configured."""
        sensor = RutOSActiveWANSensor(mock_coordinator, {})
        assert sensor.native_value == "mob1s1a1"

    def test_active_wan_none_when_all_down(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Test returns None when all interfaces are down."""
        for iface in mock_coordinator.data.wan_interfaces:
            iface["status"] = "down"

        sensor = RutOSActiveWANSensor(mock_coordinator, {})
        assert sensor.native_value is None

    def test_link_up_but_mwan_offline_falls_through(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Issue #43: primary keeps its link but mwan3 has failed over."""
        mock_coordinator.data.failover_status = {
            "mob1s1a1": {"status": "offline", "up": True},
            "mob1s2a1": {"status": "online", "up": True},
            "wan1": {"status": "standby", "up": True},
        }
        labels = {"mob1s1a1": "Starlink", "mob1s2a1": "5G/LTE"}
        sensor = RutOSActiveWANSensor(mock_coordinator, labels)
        assert sensor.native_value == "5G/LTE"

    def test_follows_member_metric_not_list_order(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """mwan3 member metric sets priority, not use_member list order.

        Mirrors the live router: use_member lists mob1s1a1 first, but
        wan1_member_mwan has the lowest metric.
        """
        metrics = {"wan1": "1", "mob1s1a1": "2", "mob1s2a1": "3", "wan2": "4"}
        for member in mock_coordinator.data.failover_chain["members"]:
            member["metric"] = metrics[member["network_id"]]
        mock_coordinator.data.failover_status = {
            "mob1s1a1": {"status": "online", "up": True},
            "wan1": {"status": "online", "up": True},
        }
        sensor = RutOSActiveWANSensor(mock_coordinator, {})
        assert sensor.native_value == "wan1"

    def test_notracking_member_counts_when_link_up(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """mwan3 treats untracked interfaces as online while the link is up."""
        mock_coordinator.data.failover_status = {
            "mob1s1a1": {"status": "notracking", "up": False},
            "mob1s2a1": {"status": "notracking", "up": True},
        }
        sensor = RutOSActiveWANSensor(mock_coordinator, {})
        assert sensor.native_value == "mob1s2a1"

    def test_uses_router_label_for_mwan_member(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Without a configured label, fall back to the router's GUI label."""
        mock_coordinator.data.failover_status = {
            "wan2": {"status": "online", "up": True},
        }
        sensor = RutOSActiveWANSensor(mock_coordinator, {})
        assert sensor.native_value == "wifi1"

    def test_none_when_no_member_online(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """No mwan3 member online means no active WAN, even with links up."""
        mock_coordinator.data.failover_status = {
            "mob1s1a1": {"status": "offline", "up": True},
            "wan1": {"status": "offline", "up": True},
        }
        sensor = RutOSActiveWANSensor(mock_coordinator, {})
        assert sensor.native_value is None

    def test_balance_mode_keeps_list_order(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Equal metrics (load balance) fall back to use_member order."""
        for member in mock_coordinator.data.failover_chain["members"]:
            member["metric"] = "1"
        mock_coordinator.data.failover_status = {
            "mob1s2a1": {"status": "online", "up": True},
            "wan1": {"status": "online", "up": True},
        }
        sensor = RutOSActiveWANSensor(mock_coordinator, {})
        assert sensor.native_value == "mob1s2a1"

    def test_falls_back_to_link_state_without_policy(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """No resolvable failover policy: use the first link-up interface."""
        mock_coordinator.data.failover_status = {
            "wan1": {"status": "online", "up": True},
        }
        mock_coordinator.data.failover_chain = {
            "policy_id": None,
            "mode": "failover",
            "members": [],
        }
        sensor = RutOSActiveWANSensor(mock_coordinator, {})
        assert sensor.native_value == "mob1s1a1"

    def test_unique_id(self, mock_coordinator: RutOSDataUpdateCoordinator):
        """Test unique_id is {serial}_active_wan."""
        sensor = RutOSActiveWANSensor(mock_coordinator, {})
        assert sensor.unique_id == "1234567890_active_wan"


class TestRutOSGPSSensorEntity:
    """Tests for GPS sensor entities."""

    def test_latitude_sensor_value(self, mock_coordinator: RutOSDataUpdateCoordinator):
        """Test GPS latitude sensor returns latitude from GPS data."""
        desc = GPS_SENSORS[0]  # latitude
        sensor = RutOSGPSSensorEntity(mock_coordinator, desc)
        assert sensor.native_value == 37.7749

    def test_longitude_sensor_value(self, mock_coordinator: RutOSDataUpdateCoordinator):
        """Test GPS longitude sensor returns longitude from GPS data."""
        desc = GPS_SENSORS[1]  # longitude
        sensor = RutOSGPSSensorEntity(mock_coordinator, desc)
        assert sensor.native_value == -122.4194

    def test_speed_sensor_value(self, mock_coordinator: RutOSDataUpdateCoordinator):
        """Test GPS speed sensor returns speed from GPS data."""
        desc = GPS_SENSORS[2]  # speed
        sensor = RutOSGPSSensorEntity(mock_coordinator, desc)
        assert sensor.native_value == 65

    def test_altitude_sensor_value(self, mock_coordinator: RutOSDataUpdateCoordinator):
        """Test GPS altitude sensor returns altitude from GPS data."""
        desc = GPS_SENSORS[3]  # altitude
        sensor = RutOSGPSSensorEntity(mock_coordinator, desc)
        assert sensor.native_value == 20

    def test_satellites_sensor_value(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Test GPS satellites sensor returns count."""
        desc = GPS_SENSORS[4]  # satellites
        sensor = RutOSGPSSensorEntity(mock_coordinator, desc)
        assert sensor.native_value == 12

    def test_heading_sensor_value(self, mock_coordinator: RutOSDataUpdateCoordinator):
        """Test GPS heading sensor returns angle."""
        desc = GPS_SENSORS[5]  # heading
        sensor = RutOSGPSSensorEntity(mock_coordinator, desc)
        assert sensor.native_value == 180

    def test_fix_status_sensor_value(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Test GPS fix status sensor returns fix type."""
        desc = GPS_SENSORS[6]  # fix_status
        sensor = RutOSGPSSensorEntity(mock_coordinator, desc)
        assert sensor.native_value == "3D"

    def test_no_gps_returns_none(self, mock_coordinator: RutOSDataUpdateCoordinator):
        """Test GPS sensor returns None when no GPS data."""
        mock_coordinator.data.gps_position = None
        desc = GPS_SENSORS[0]
        sensor = RutOSGPSSensorEntity(mock_coordinator, desc)
        assert sensor.native_value is None

    def test_accuracy_sensor_value(self, mock_coordinator: RutOSDataUpdateCoordinator):
        """Test GPS accuracy sensor returns accuracy from GPS data."""
        desc = GPS_SENSORS[7]  # accuracy
        sensor = RutOSGPSSensorEntity(mock_coordinator, desc)
        assert sensor.native_value == 5

    def test_rounds_router_string_values(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Issue #51: the router sends strings; noise below the step is dropped."""
        mock_coordinator.data.gps_position.update(
            {"speed": "1.4", "altitude": "141.7", "accuracy": "0.6"}
        )
        values = {
            d.key: RutOSGPSSensorEntity(mock_coordinator, d).native_value
            for d in GPS_SENSORS
        }
        assert values["gps_speed"] == 1
        assert values["gps_altitude"] == 140
        assert values["gps_accuracy"] == 1

    def test_rounding_handles_missing_and_garbage(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Unparseable readings become None rather than raising."""
        mock_coordinator.data.gps_position.update({"speed": None, "altitude": "n/a"})
        speed = next(d for d in GPS_SENSORS if d.key == "gps_speed")
        altitude = next(d for d in GPS_SENSORS if d.key == "gps_altitude")
        assert RutOSGPSSensorEntity(mock_coordinator, speed).native_value is None
        assert RutOSGPSSensorEntity(mock_coordinator, altitude).native_value is None

    def test_coordinates_have_no_state_class(self):
        """Issue #52: no long-term statistics for latitude/longitude."""
        for key in ("gps_latitude", "gps_longitude"):
            desc = next(d for d in GPS_SENSORS if d.key == key)
            assert desc.state_class is None

    def test_noisy_gps_sensors_disabled_by_default(self):
        """Issue #52: troubleshooting-only GPS sensors start disabled."""
        disabled = {
            d.key for d in GPS_SENSORS if d.entity_registry_enabled_default is False
        }
        assert disabled == {"gps_satellites", "gps_accuracy", "gps_heading"}

    def test_unique_id_format(self, mock_coordinator: RutOSDataUpdateCoordinator):
        """Test unique_id follows {serial}_{key} pattern."""
        desc = GPS_SENSORS[0]
        sensor = RutOSGPSSensorEntity(mock_coordinator, desc)
        assert sensor.unique_id == "1234567890_gps_latitude"


class TestRutOSDataLimitSensor:
    """Tests for data limit sensor entities."""

    def test_data_used_value(self, mock_coordinator: RutOSDataUpdateCoordinator):
        """Test data used sensor returns bytes used."""
        desc = DATA_LIMIT_SENSORS[0]  # data_used
        sensor = RutOSDataLimitSensor(mock_coordinator, desc, "limit1")
        assert sensor.native_value == 2_500_000_000

    def test_data_limit_value(self, mock_coordinator: RutOSDataUpdateCoordinator):
        """Test data limit sensor returns limit in bytes."""
        desc = DATA_LIMIT_SENSORS[1]  # data_limit
        sensor = RutOSDataLimitSensor(mock_coordinator, desc, "limit1")
        assert sensor.native_value == 5_000_000_000

    def test_data_usage_percent(self, mock_coordinator: RutOSDataUpdateCoordinator):
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

    def test_unique_id_format(self, mock_coordinator: RutOSDataUpdateCoordinator):
        """Test unique_id follows {serial}_{limit}_{key} pattern."""
        desc = DATA_LIMIT_SENSORS[0]
        sensor = RutOSDataLimitSensor(mock_coordinator, desc, "limit1")
        assert sensor.unique_id == "1234567890_limit1_data_used"


class TestRutOSModemSignalSensor:
    """Tests for modem signal sensor entities."""

    def test_rssi_value(self, mock_coordinator: RutOSDataUpdateCoordinator):
        """Test RSSI sensor returns signal strength."""
        desc = _signal_desc("rssi")
        sensor = RutOSModemSignalSensor(mock_coordinator, desc, "modem1")
        assert sensor.native_value == -65

    def test_rsrp_value(self, mock_coordinator: RutOSDataUpdateCoordinator):
        """Test RSRP sensor returns reference signal power."""
        desc = _signal_desc("rsrp")
        sensor = RutOSModemSignalSensor(mock_coordinator, desc, "modem1")
        assert sensor.native_value == -95

    def test_rsrq_value(self, mock_coordinator: RutOSDataUpdateCoordinator):
        """Test RSRQ sensor returns reference signal quality."""
        desc = _signal_desc("rsrq")
        sensor = RutOSModemSignalSensor(mock_coordinator, desc, "modem1")
        assert sensor.native_value == -10

    def test_sinr_value(self, mock_coordinator: RutOSDataUpdateCoordinator):
        """Test SINR sensor returns signal-to-noise ratio."""
        desc = _signal_desc("sinr")
        sensor = RutOSModemSignalSensor(mock_coordinator, desc, "modem1")
        assert sensor.native_value == 12

    def test_raw_signal_sensors_disabled_by_default(self):
        """Issue #52: raw RF metrics start disabled; signal quality stays on."""
        disabled = {
            d.key
            for d in MODEM_SIGNAL_SENSORS
            if d.entity_registry_enabled_default is False
        }
        assert disabled == {"rssi", "rsrp", "rsrq", "sinr"}

    def test_carriers_attribute_not_recorded(self):
        """Issue #51: per-carrier metrics stay out of the recorder."""
        assert "carriers" in RutOSModemSignalSensor._unrecorded_attributes
        assert "primary_band" not in RutOSModemSignalSensor._unrecorded_attributes

    def test_signal_quality_value(self, mock_coordinator: RutOSDataUpdateCoordinator):
        """Test signal quality sensor returns the router's percentage."""
        desc = _signal_desc("signal_quality")
        sensor = RutOSModemSignalSensor(mock_coordinator, desc, "modem1")
        assert sensor.native_value == 71
        assert sensor.native_unit_of_measurement == "%"

    def test_network_type_value(self, mock_coordinator: RutOSDataUpdateCoordinator):
        """Test network type sensor returns LTE/5G etc."""
        desc = _signal_desc("network_type")
        sensor = RutOSModemSignalSensor(mock_coordinator, desc, "modem1")
        assert sensor.native_value == "LTE"

    def test_band_value(self, mock_coordinator: RutOSDataUpdateCoordinator):
        """Test band sensor returns band identifier."""
        desc = _signal_desc("band")
        sensor = RutOSModemSignalSensor(mock_coordinator, desc, "modem1")
        assert sensor.native_value == "B7"

    def test_missing_modem_returns_none(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Test returns None when modem not found."""
        desc = MODEM_SIGNAL_SENSORS[0]
        sensor = RutOSModemSignalSensor(mock_coordinator, desc, "nonexistent")
        assert sensor.native_value is None

    def test_unique_id_format(self, mock_coordinator: RutOSDataUpdateCoordinator):
        """Test unique_id follows {serial}_{modem}_{key} pattern."""
        desc = MODEM_SIGNAL_SENSORS[0]
        sensor = RutOSModemSignalSensor(mock_coordinator, desc, "modem1")
        assert sensor.unique_id == "1234567890_modem1_rssi"


class TestRutOSModemStatusSensor:
    """Tests for modem status (operator) sensor entities."""

    def test_operator_value(self, mock_coordinator: RutOSDataUpdateCoordinator):
        """Test operator sensor returns carrier name."""
        desc = MODEM_STATUS_SENSORS[0]  # operator
        sensor = RutOSModemStatusSensor(mock_coordinator, desc, "modem1")
        assert sensor.native_value == "T-Mobile"

    def test_missing_modem_returns_none(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Test returns None when modem not found."""
        desc = MODEM_STATUS_SENSORS[0]
        sensor = RutOSModemStatusSensor(mock_coordinator, desc, "nonexistent")
        assert sensor.native_value is None

    def test_unique_id_format(self, mock_coordinator: RutOSDataUpdateCoordinator):
        """Test unique_id follows {serial}_{modem}_{key} pattern."""
        desc = MODEM_STATUS_SENSORS[0]
        sensor = RutOSModemStatusSensor(mock_coordinator, desc, "modem1")
        assert sensor.unique_id == "1234567890_modem1_operator"


class TestModemSensorNaming:
    """Tests for single-vs-multi modem label selection (issue #26)."""

    def test_signal_single_modem_no_placeholder(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Single modem: use base translation key with no placeholder."""
        desc = _signal_desc("rssi")
        sensor = RutOSModemSignalSensor(mock_coordinator, desc, "modem1")
        assert sensor.translation_key == "modem_rssi"
        assert not sensor.translation_placeholders

    def test_signal_multi_modem_uses_multi_key(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Multi modem: use _multi translation key with {modem} placeholder."""
        mock_coordinator.data.modems = [{"id": "2-1"}, {"id": "3-1"}]
        desc = MODEM_SIGNAL_SENSORS[0]
        sensor = RutOSModemSignalSensor(mock_coordinator, desc, "2-1")
        assert sensor.translation_key == "modem_rssi_multi"
        assert sensor.translation_placeholders == {"modem": "2-1"}
        assert sensor.unique_id == "1234567890_2-1_rssi"

    def test_status_single_modem_no_placeholder(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Single modem: operator sensor uses base key with no placeholder."""
        desc = MODEM_STATUS_SENSORS[0]  # operator
        sensor = RutOSModemStatusSensor(mock_coordinator, desc, "modem1")
        assert sensor.translation_key == "modem_operator"
        assert not sensor.translation_placeholders

    def test_status_multi_modem_uses_multi_key(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Multi modem: operator sensor uses _multi key with placeholder."""
        mock_coordinator.data.modems = [{"id": "2-1"}, {"id": "3-1"}]
        desc = MODEM_STATUS_SENSORS[0]
        sensor = RutOSModemStatusSensor(mock_coordinator, desc, "2-1")
        assert sensor.translation_key == "modem_operator_multi"
        assert sensor.translation_placeholders == {"modem": "2-1"}


class TestFormatBands:
    """Pure unit tests for the band-list formatter."""

    def test_empty_carriers_returns_fallback(self):
        assert _format_bands([], "B7") == "B7"
        assert _format_bands([], None) is None

    def test_single_lte_carrier(self):
        carriers = [{"band": "LTE B7", "primary": True}]
        assert _format_bands(carriers, None) == "LTE 7 (P)"

    def test_nsa_3ca_lte_plus_2x_n78(self):
        """5G-NSA with 3CA LTE (PCell B7) + intra-band 2x N78 NR."""
        carriers = [
            {"band": "LTE B7", "primary": True},
            {"band": "LTE B2", "primary": False},
            {"band": "LTE B66", "primary": False},
            {"band": "5G N78", "primary": False},
            {"band": "5G N78", "primary": False},
        ]
        assert _format_bands(carriers, None) == "LTE 7 (P), 2, 66 + 5G 78×2"

    def test_unparseable_band_is_skipped(self):
        carriers = [
            {"band": "LTE B7", "primary": True},
            {"band": "garbage", "primary": False},
            {"band": None, "primary": False},
        ]
        assert _format_bands(carriers, None) == "LTE 7 (P)"

    def test_all_unparseable_falls_back(self):
        carriers = [{"band": "garbage"}]
        assert _format_bands(carriers, "B7") == "B7"


class TestRutOSBandsSensor:
    """Tests for the carrier-aggregation bands sensor."""

    def test_native_value_with_carriers(
        self,
        mock_coordinator: RutOSDataUpdateCoordinator,
        mock_modem_signal_nsa_ca,
    ):
        mock_coordinator.data.modem_signal = mock_modem_signal_nsa_ca
        sensor = RutOSModemSignalSensor(mock_coordinator, _bands_desc(), "modem1")
        assert sensor.native_value == "LTE 7 (P), 2, 66 + 5G 78×2"

    def test_native_value_without_carriers_falls_back(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Non-CA modem: sensor falls back to the top-level band string."""
        sensor = RutOSModemSignalSensor(mock_coordinator, _bands_desc(), "modem1")
        assert sensor.native_value == "B7"

    def test_extra_state_attributes(
        self,
        mock_coordinator: RutOSDataUpdateCoordinator,
        mock_modem_signal_nsa_ca,
    ):
        mock_coordinator.data.modem_signal = mock_modem_signal_nsa_ca
        sensor = RutOSModemSignalSensor(mock_coordinator, _bands_desc(), "modem1")
        attrs = sensor.extra_state_attributes
        assert attrs is not None
        assert attrs["primary_band"] == "LTE B7"
        assert len(attrs["carriers"]) == 5
        assert attrs["carriers"][0]["band"] == "LTE B7"

    def test_legacy_band_sensor_has_no_attributes(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Sensors without attributes_fn should not expose extras."""
        sensor = RutOSModemSignalSensor(mock_coordinator, _band_desc(), "modem1")
        assert sensor.extra_state_attributes is None

    def test_missing_modem_returns_none(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        sensor = RutOSModemSignalSensor(mock_coordinator, _bands_desc(), "nope")
        assert sensor.native_value is None
        assert sensor.extra_state_attributes is None
