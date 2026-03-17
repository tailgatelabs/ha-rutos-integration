# RutOS Home Assistant Integration

[![Validate](https://github.com/crbn60/ha-rutos-integration/actions/workflows/validate.yml/badge.svg)](https://github.com/crbn60/ha-rutos-integration/actions/workflows/validate.yml)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

A Home Assistant custom integration for Teltonika devices running RutOS.
Provides WAN interface management, internet connectivity monitoring, and
failover control.

## Supported Devices

- Teltonika RUTM50 (5G router)
- Other Teltonika devices running RutOS 7.x with API v1.13+

## Features

- **WAN Interface Sensors** — Status, IP address, protocol, and uptime for each
  WAN interface
- **Active WAN Sensor** — Shows which WAN interface is currently active
- **Internet Connectivity** — Binary sensor reflecting the router's own
  connectivity check
- **WAN Interface Switches** — Enable/disable individual WAN interfaces
- **Failover Ordering** — Service call to reorder WAN interface failover
  priority
- **GPS Tracking** — Sensors for speed, altitude, heading, satellites, accuracy,
  and fix status, with optional automatic updates to the Home Assistant home
  location
- **Data Usage** — Data used, data limit, and usage percentage for each
  configured data limit, plus a button to reset usage counters
- **Cellular Signal** — RSSI, RSRP, RSRQ, SINR, network type, and band for each
  modem
- **Mobile Operator** — Current carrier name for each modem (e.g., "Bell",
  "T-Mobile")
- **Modem Roaming** — Binary sensor indicating whether each modem is roaming
- **Modem Reboot** — Button to reboot individual modems without rebooting the
  entire device

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Go to **Integrations** > **Custom repositories**
3. Add `https://github.com/tailgatelabs/ha-rutos-integration` as an
   **Integration**
4. Search for "RutOS" and install it
5. Restart Home Assistant

### Manual

1. Copy the `custom_components/rutos` directory to your Home Assistant
   `config/custom_components/` directory
2. Restart Home Assistant

## Configuration

1. Go to **Settings** > **Devices & services** > **Add integration**
2. Search for "RutOS"
3. Enter:
   - **Host** — IP address or hostname of your router (e.g., `192.168.1.1`)
   - **Username** — Router admin username (default: `admin`)
   - **Password** — Router admin password

## Services

### `rutos.set_failover_order`

Reorder WAN interface failover priority.

```yaml
service: rutos.set_failover_order
data:
  interfaces:
    - wan
    - mob1s1a1
    - mob2s1a1
```

The first interface in the list gets the highest priority.

## GPS & Home Location

The integration fetches GPS data from the router's `/gps/position/status`
endpoint every 30 seconds. Eight GPS sensors are created automatically:

| Sensor         | Description                  |
| -------------- | ---------------------------- |
| GPS Latitude   | Current latitude (°)         |
| GPS Longitude  | Current longitude (°)        |
| GPS Speed      | Current speed (km/h)         |
| GPS Altitude   | Altitude above sea level (m) |
| GPS Heading    | Direction of travel (°)      |
| GPS Satellites | Number of visible satellites |
| GPS Fix Status | Fix type (e.g., "2D", "3D")  |
| GPS Accuracy   | Position accuracy (m)        |

### Home Location Updates

When enabled (the default), the integration automatically updates your Home
Assistant home zone coordinates using the router's GPS position. This is useful
for mobile installations (RVs, boats, etc.) where "home" moves with you.

To toggle this setting: go to **Settings** > **Devices & services** >
**RutOS** > **Configure** and check or uncheck **Update Home Assistant home
location from GPS**.

### Verifying GPS Data

1. **Check that the router has a GPS fix.** Open the router's web UI and confirm
   GPS status shows a valid fix (2D or 3D). The router needs a clear view of the
   sky for satellite reception.
2. **Inspect the GPS sensors in Home Assistant.** Go to **Developer Tools** >
   **States** and filter for `sensor.rutos_gps_`. Confirm the sensors show
   numeric values (not `unknown` or `unavailable`). If they show `unknown`, the
   router is not returning GPS data — verify the GPS antenna is connected and
   the router has a fix.
3. **Verify home location is updating.** Go to **Settings** > **Home Zone** (or
   **Developer Tools** > **States** and search for `zone.home`). The latitude
   and longitude should match the values from the GPS speed/altitude sensors'
   device page. After the next 30-second polling cycle, the home zone
   coordinates should reflect the router's GPS position.
4. **Check the integration log.** If GPS data is not appearing, enable debug
   logging by adding the following to `configuration.yaml` and restarting:
   ```yaml
   logger:
     logs:
       custom_components.rutos: debug
   ```
   Look for GPS-related log entries under **Settings** > **System** > **Logs**.

## Entities Reference

### Sensors

| Entity                   | Description                                 | Unit |
| ------------------------ | ------------------------------------------- | ---- |
| `{interface} status`     | WAN interface status (up/down)              | —    |
| `{interface} IP address` | WAN interface IPv4 address                  | —    |
| `{interface} protocol`   | WAN interface protocol (dhcp, wwan, static) | —    |
| `{interface} uptime`     | WAN interface uptime                        | s    |
| `Active WAN interface`   | Name of the currently active WAN interface  | —    |
| `{modem} RSSI`           | Received Signal Strength Indicator          | dBm  |
| `{modem} RSRP`           | Reference Signal Received Power             | dBm  |
| `{modem} RSRQ`           | Reference Signal Received Quality           | dB   |
| `{modem} SINR`           | Signal-to-Interference-plus-Noise Ratio     | dB   |
| `{modem} network type`   | Network technology (LTE, 5G, etc.)          | —    |
| `{modem} band`           | Operating frequency band                    | —    |
| `{modem} operator`       | Mobile network operator name                | —    |
| `{limit} data used`      | Total data consumed                         | B    |
| `{limit} data limit`     | Configured data cap                         | B    |
| `{limit} data usage`     | Usage as percentage of limit                | %    |

### Binary Sensors

| Entity                  | Description                            |
| ----------------------- | -------------------------------------- |
| `Internet connectivity` | Whether the router has internet access |
| `{modem} roaming`       | Whether the modem is currently roaming |

### Switches

| Entity                | Description                       |
| --------------------- | --------------------------------- |
| `{interface} enabled` | Enable or disable a WAN interface |

### Buttons

| Entity             | Description                |
| ------------------ | -------------------------- |
| `Clear data usage` | Reset data usage counters  |
| `Reboot {modem}`   | Reboot an individual modem |

## Automation Examples

### Starlink Failover

This automation uses the **internet connectivity** binary sensor to detect when
the router's primary connection has been down for 2 minutes, then automatically
powers on a Starlink dish as a backup and sends a push notification.

```yaml
alias: Starlink Failover
description: >-
  Turn on Starlink power if internet connectivity has been down for 120 seconds,
  and send a notification
mode: single
triggers:
  - entity_id: binary_sensor.router_internet_connectivity
    to: "off"
    for:
      seconds: 120
    trigger: state
conditions:
  - condition: state
    entity_id: switch.starlink_power
    state: "off"
actions:
  - target:
      entity_id: switch.starlink_power
    action: switch.turn_on
  - action: notify.mobile_app_phone
    data:
      title: Starlink Failover
      message: >-
        Internet down for 2 minutes. Starlink power has been turned on.
      data:
        push:
          interruption-level: time-sensitive
```

### Data Usage Alert

Send a notification when cellular data usage exceeds 80%.

```yaml
alias: Data Usage Warning
triggers:
  - entity_id: sensor.router_mob1s1a1_data_usage
    above: 80
    trigger: numeric_state
actions:
  - action: notify.mobile_app_phone
    data:
      title: Data Usage Warning
      message: >-
        Cellular data usage is at {{ states('sensor.router_mob1s1a1_data_usage')
        }}%
```

### Reorder Failover on WAN Change

Automatically adjust failover priority when the active WAN interface changes.

```yaml
alias: Reorder Failover on WAN Change
triggers:
  - entity_id: sensor.router_active_wan_interface
    trigger: state
conditions:
  - condition: state
    entity_id: sensor.router_active_wan_interface
    state: wan1
actions:
  - action: rutos.set_failover_order
    data:
      interfaces:
        - wan1
        - mob1s1a1
        - wan3
```

## Requirements

- RutOS 7.x firmware with API version 1.13+
- JSON-RPC API access enabled on the router
- Home Assistant 2024.8.0 or newer

## License

MIT License - see [LICENSE](LICENSE) for details.
