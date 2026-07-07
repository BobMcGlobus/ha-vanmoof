"""Constants for the VanMoof integration."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "vanmoof"

# CONF_ADDRESS is imported from homeassistant.const where needed.
CONF_KEY = "key"
CONF_USER_KEY_ID = "user_key_id"

PLATFORMS: list[Platform] = [Platform.LOCK, Platform.SENSOR]

# The bike stays connectable, so poll every few minutes. Each poll opens a
# short-lived BLE session (connect -> authenticate -> read -> disconnect),
# which keeps the phone app usable and doesn't drain the bike battery.
SCAN_INTERVAL = timedelta(minutes=5)
