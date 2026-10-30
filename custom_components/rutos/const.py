"""Constants for the RutOS integration."""

DOMAIN = "rutos"

DEFAULT_USERNAME = "admin"
DEFAULT_SCAN_INTERVAL = 30

API_PATH = "/api"

REQUEST_TIMEOUT = 15  # Seconds per HTTP request, including login
# Overlapping requests can wedge the router's web server until it is restarted
# (#47), and running them in parallel saves only about a second per poll.
MAX_CONCURRENT_REQUESTS = 1
# Seconds between polls after 1, 2, and 3+ consecutive connection failures.
CONNECTION_BACKOFF_INTERVALS = (60, 120, 300)

SERVICE_SET_FAILOVER_ORDER = "set_failover_order"
ATTR_INTERFACES = "interfaces"

CONF_UPDATE_HOME_LOCATION = "update_home_location"
ISSUE_HOME_ZONE_OVERRIDDEN = "home_zone_overridden"
CONF_FAILOVER_GROUPS = "failover_groups"

SUBENTRY_TYPE_RECIPIENT = "recipient"
CONF_PHONE_NUMBER = "phone_number"
CONF_MODEM = "modem"
