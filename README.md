# RutOS Home Assistant Integration

[![Validate](https://github.com/crbn60/ha-rutos-integration/actions/workflows/validate.yml/badge.svg)](https://github.com/crbn60/ha-rutos-integration/actions/workflows/validate.yml)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

A Home Assistant custom integration for Teltonika devices running RutOS.
Provides WAN interface management, internet connectivity monitoring, failover
control, GPS tracking, cellular monitoring, and SMS notifications.

## Supported Devices

- Teltonika RUTM50 (5G router)
- Other Teltonika devices running RutOS 7.x with API v1.13+

## Features

### Major features

- **WAN failover control** — Per-interface status, IP address, protocol, and
  uptime sensors; switches to enable or disable each interface; and a
  `Failover priority` select (plus a `rutos.set_failover_order` service) to
  switch between priority orderings with a single tap
- **Internet connectivity monitoring** — Binary sensor reflecting the router's
  own connectivity check, ideal for triggering failover automations and alerts
- **GPS tracking** — Latitude, longitude, speed, altitude, heading, satellites,
  accuracy, and fix status sensors, with optional automatic updates to the Home
  Assistant home location for mobile installations (RVs, boats, etc.)
- **Cellular monitoring** — RSSI, RSRP, RSRQ, SINR, network type, band,
  operator, and roaming status for each modem
- **Data usage tracking** — Data used, data limit, and usage percentage for each
  configured data limit, plus a button to reset usage counters
- **SMS notifications** — Configure recipients as subentries to create one
  `notify.*` entity per recipient; send SMS from automations through any modem
  on the router

### Other features

- **Active WAN interface sensor** — Shows which WAN interface currently carries
  traffic
- **Modem reboot button** — Reboot individual modems without rebooting the
  entire device
- **Dual-SIM support** — `Active SIM` sensor and `Switch SIM` button for modems
  with two SIM slots

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Go to **Integrations** > **Custom repositories**
3. Add `https://github.com/crbn60/ha-rutos-integration` as an **Integration**
4. Search for "RutOS" and install it
5. Restart Home Assistant

### Manual

1. Copy the `custom_components/rutos` directory to your Home Assistant
   `config/custom_components/` directory
2. Restart Home Assistant

## Configuration

### Initial Setup

1. Go to **Settings** > **Devices & services** > **Add integration**
2. Search for "RutOS"
3. Enter:
   - **Host** — IP address or hostname of your router (e.g., `192.168.1.1`)
   - **Username** — Router admin username (default: `admin`)
   - **Password** — Router admin password

### Failover Priority

The integration includes a **Failover priority** select entity that lets you
switch between WAN failover orderings with a single tap. To set it up:

1. Go to **Settings** > **Devices & services** > **RutOS** > **Configure**
2. **Step 1 — General settings:** Toggle the home location GPS option and click
   **Submit**
3. **Step 2 — Failover groups:** The integration queries your router's failover
   members and displays one text field per interface. Type a label for each
   interface (e.g., "Cellular", "Starlink", "WiFi"). Interfaces that share the
   same label are grouped and reordered together.
4. Click **Submit** — the integration reloads and a **Failover priority** select
   entity appears with all permutations of your labels as options (e.g.,
   "Cellular, Starlink, WiFi" vs "Starlink, Cellular, WiFi").

To change labels later, repeat the same Configure flow.

### SMS Recipients

Add one recipient per person or phone number you want to text from automations.
Each recipient becomes its own `notify.*` entity.

1. Go to **Settings** > **Devices & services** > **RutOS**
2. Click **Add SMS recipient** under the integration
3. Enter:
   - **Name** — Display name used as part of the notify entity name
   - **Phone number** — Full E.164 format (e.g., `+15551234567`)
   - **Modem** — Which modem to send through (required when the router has more
     than one modem)
4. Use the resulting `notify.sms_*` entity from any automation via
   **Notifications: Send a notification**

To edit or remove a recipient, use the **Configure** / **Delete** controls on
the subentry.

## Services

### `rutos.set_failover_order`

Reorder WAN interface failover priority.

```yaml
service: rutos.set_failover_order
data:
  interfaces:
    - wan1
    - mob1s1a1
    - mob1s2a1
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
| `{modem} active SIM`     | Currently active SIM slot (dual-SIM modems) | —    |
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

### Select

| Entity              | Description                                    |
| ------------------- | ---------------------------------------------- |
| `Failover priority` | Switch between WAN failover priority orderings |

### Buttons

| Entity               | Description                               |
| -------------------- | ----------------------------------------- |
| `Clear data usage`   | Reset data usage counters                 |
| `Reboot {modem}`     | Reboot an individual modem                |
| `Switch SIM {modem}` | Toggle the active SIM on a dual-SIM modem |

### Notify

| Entity            | Description                                        |
| ----------------- | -------------------------------------------------- |
| `SMS {recipient}` | Sends an SMS to a configured recipient via a modem |

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
