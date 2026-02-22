"""Constants for the RutOS integration."""

DOMAIN = "rutos"

CONF_HOST = "host"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"

DEFAULT_USERNAME = "admin"
DEFAULT_SCAN_INTERVAL = 30

API_PATH = "/ubus"
API_JSONRPC_VERSION = "2.0"

SESSION_EXPIRY = 300  # 5 minutes
SESSION_REFRESH_MARGIN = 30  # Refresh 30s before expiry

SERVICE_SET_FAILOVER_ORDER = "set_failover_order"
ATTR_INTERFACES = "interfaces"
