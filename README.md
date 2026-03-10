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
- **GPS Tracking** — Device tracker with real-time location on the HA map, plus
  sensors for speed, altitude, heading, satellites, and fix status
- **Data Usage** — Data used, data limit, and usage percentage for each
  configured data limit, plus a button to reset usage counters
- **Cellular Signal** — RSSI, RSRP, RSRQ, SINR, network type, and band for each
  modem
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

## Requirements

- RutOS 7.x firmware with API version 1.13+
- JSON-RPC API access enabled on the router
- Home Assistant 2024.8.0 or newer

## License

MIT License - see [LICENSE](LICENSE) for details.
