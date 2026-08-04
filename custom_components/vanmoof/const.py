"""Constants for the VanMoof integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "vanmoof"

# CONF_ADDRESS is imported from homeassistant.const where needed.
CONF_KEY = "key"
CONF_USER_KEY_ID = "user_key_id"
# Stored from the cloud account at setup (the BLE FRAME_NUMBER read returns
# "Invalid Handle" on some firmware, so we don't rely on it).
CONF_FRAME_NUMBER = "frame_number"
CONF_MODEL = "model"

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.LOCK,
    Platform.SELECT,
    Platform.SENSOR,
]

# S3/X3 (SX3) advertise this BikeInfo GATT service UUID. It's what pymoof's own
# discover_bike scans for, and what the manifest bluetooth matcher uses. Kept in
# sync with the "service_uuid" in manifest.json (JSON can't import this).
SX3_SERVICE_UUID = "6acc5540-e631-4069-944d-b8ca7598ad50"

# Poll cadence. Each poll opens a short-lived BLE session (connect -> auth ->
# read -> disconnect), which keeps the phone app usable and is easy on the bike
# battery. Configurable per bike via the options flow (minutes).
DEFAULT_SCAN_INTERVAL_MINUTES = 5
MIN_SCAN_INTERVAL_MINUTES = 1
MAX_SCAN_INTERVAL_MINUTES = 180

# Polling and presence pull in opposite directions: while we hold a connection to
# read the battery, the bike stops advertising, which can make the "In range"
# sensor flap. This option picks which side to favour.
CONF_PRIORITY = "priority"
PRIORITY_BATTERY = "battery"
PRIORITY_PRESENCE = "presence"
DEFAULT_PRIORITY = PRIORITY_BATTERY
PRIORITIES = [PRIORITY_BATTERY, PRIORITY_PRESENCE]

# How long the bike may stop advertising before "In range" turns off. Longer
# hides brief dropouts (smooth presence, slower departure detection).
PRESENCE_GRACE_SECONDS = {
    PRIORITY_BATTERY: 300,
    PRIORITY_PRESENCE: 0,
}
