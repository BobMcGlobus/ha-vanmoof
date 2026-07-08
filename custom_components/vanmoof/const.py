"""Constants for the VanMoof integration."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "vanmoof"

# CONF_ADDRESS is imported from homeassistant.const where needed.
CONF_KEY = "key"
CONF_USER_KEY_ID = "user_key_id"

PLATFORMS: list[Platform] = [Platform.LOCK, Platform.SENSOR]

# S3/X3 (SX3) advertise this BikeInfo GATT service UUID. It's what pymoof's own
# discover_bike scans for, and what the manifest bluetooth matcher uses. Kept in
# sync with the "service_uuid" in manifest.json (JSON can't import this).
SX3_SERVICE_UUID = "6acc5540-e631-4069-944d-b8ca7598ad50"

# The bike stays connectable, so poll every few minutes. Each poll opens a
# short-lived BLE session (connect -> authenticate -> read -> disconnect),
# which keeps the phone app usable and doesn't drain the bike battery.
SCAN_INTERVAL = timedelta(minutes=5)
