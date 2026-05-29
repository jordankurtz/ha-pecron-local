from __future__ import annotations

DOMAIN = "pecron_local"

PLATFORMS = ["sensor", "switch", "select"]

CONF_AUTH_KEY = "auth_key"
CONF_MAC = "mac"
CONF_POLL_INTERVAL = "poll_interval"
CONF_PREFERRED_TRANSPORT = "preferred_transport"
CONF_REGION = "region"
CONF_DEVICE_KEY = "device_key"
CONF_PRODUCT_KEY = "product_key"

DEFAULT_POLL_INTERVAL = 30
DEFAULT_PORT = 6607
TRANSPORT_TCP = "tcp"
TRANSPORT_BLE = "ble"
