"""Constants for the RutOS integration."""

DOMAIN = "rutos"

DEFAULT_USERNAME = "admin"
DEFAULT_SCAN_INTERVAL = 30

API_PATH = "/api"

SESSION_REFRESH_MARGIN = 30  # Refresh 30s before expiry
REQUEST_TIMEOUT = 15  # Seconds per HTTP request, including login
# The router's API stalls requests when ~10+ arrive at once; 4 is reliable.
MAX_CONCURRENT_REQUESTS = 4

SERVICE_SET_FAILOVER_ORDER = "set_failover_order"
ATTR_INTERFACES = "interfaces"

CONF_UPDATE_HOME_LOCATION = "update_home_location"
ISSUE_HOME_ZONE_OVERRIDDEN = "home_zone_overridden"
CONF_FAILOVER_GROUPS = "failover_groups"

SUBENTRY_TYPE_RECIPIENT = "recipient"
CONF_PHONE_NUMBER = "phone_number"
CONF_MODEM = "modem"
