"""DataUpdateCoordinator for VanMoof.

Owns the BLE lifecycle. Each cycle opens a short-lived, authenticated session
to the bike, reads state, and disconnects. Home Assistant's Bluetooth stack
transparently routes the connection through the local adapter or whichever
ESPHome proxy can currently reach the bike.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import TypeVar

from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_FRAME_NUMBER,
    CONF_KEY,
    CONF_MODEL,
    CONF_USER_KEY_ID,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
)
from .pymoof_vendor.clients.sx3 import LockState, SX3Client

# Escalate to a reauth flow only after this many consecutive failures that
# happen *after* a successful connection (a genuine bad key keeps failing; a
# one-off BLE glitch shouldn't nag the user to re-authenticate).
_AUTH_FAILURE_THRESHOLD = 2

_LOGGER = logging.getLogger(__name__)

_T = TypeVar("_T")

type VanMoofConfigEntry = ConfigEntry[VanMoofCoordinator]


@dataclass
class VanMoofData:
    """Snapshot of bike state from one poll.

    Core fields always come from a successful poll. The rest are best-effort:
    some characteristics (e.g. FRAME_NUMBER on certain firmware) return
    "Invalid Handle", so a failing optional read must not fail the whole poll.
    """

    battery: int
    distance_km: float
    speed_kmh: int
    lock_state: LockState
    frame_number: str | None = None
    module_battery: int | None = None
    bike_firmware: str | None = None
    has_error: bool = False
    charging: bool | None = None


class VanMoofCoordinator(DataUpdateCoordinator[VanMoofData]):
    """Connects to the bike over BLE, authenticates, and polls state."""

    def __init__(self, hass: HomeAssistant, entry: VanMoofConfigEntry) -> None:
        minutes = entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES
        )
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=minutes),
        )
        self.entry = entry
        self.address: str = entry.data[CONF_ADDRESS]
        self._key: str = entry.data[CONF_KEY]
        self._user_key_id: int = entry.data[CONF_USER_KEY_ID]
        # From the cloud account at setup; the BLE read is unreliable.
        self.frame_number: str | None = entry.data.get(CONF_FRAME_NUMBER)
        self.model: str | None = entry.data.get(CONF_MODEL)
        self._post_connect_failures = 0

    async def _async_update_data(self) -> VanMoofData:
        return await self._with_client(self._read_all)

    async def _with_client(
        self, action: Callable[[SX3Client], Awaitable[_T]]
    ) -> _T:
        """Open a session, authenticate, run ``action``, always disconnect."""
        ble_device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if ble_device is None:
            # Not seen advertising right now (out of range / deep sleep).
            # Raising UpdateFailed marks entities unavailable and retries next
            # interval; at setup it becomes ConfigEntryNotReady.
            raise UpdateFailed(
                f"VanMoof {self.address} is not advertising / out of range"
            )

        try:
            client = await establish_connection(
                BleakClientWithServiceCache, ble_device, self.address
            )
        except BleakError as err:
            # Couldn't even connect: transient (out of range / busy). Retry next
            # cycle; don't count it against authentication.
            raise UpdateFailed(f"couldn't connect to the bike: {err}") from err

        try:
            sx3 = SX3Client(client, self._key, self._user_key_id)
            # pymoof's authenticate() returns silently even on a bad key; the
            # first authenticated read below is what actually surfaces it.
            await sx3.authenticate()
            result = await action(sx3)
        except BleakError as err:
            # Failure *after* a successful connect. Usually a wrong key, but
            # could be a one-off glitch, so only escalate to reauth once it
            # keeps happening.
            self._post_connect_failures += 1
            if self._post_connect_failures >= _AUTH_FAILURE_THRESHOLD:
                raise ConfigEntryAuthFailed(
                    f"authentication failed (check the encryption key): {err}"
                ) from err
            raise UpdateFailed(f"BLE error after connecting: {err}") from err
        else:
            self._post_connect_failures = 0
            return result
        finally:
            await client.disconnect()

    async def _read_all(self, sx3: SX3Client) -> VanMoofData:
        # Core reads define success; if these fail it's a real error (surfaced
        # by _with_client as UpdateFailed / reauth).
        # NOTE: get_battery_level() reads the motor/main battery.
        data = VanMoofData(
            battery=await sx3.get_battery_level(),
            distance_km=await sx3.get_distance_travelled(),
            speed_kmh=await sx3.get_speed(),
            lock_state=await sx3.get_lock_state(),
        )
        # Frame number comes from the cloud account (BLE read is unreliable).
        data.frame_number = self.frame_number
        # Optional reads: best-effort, never fail the poll (some characteristics
        # return "Invalid Handle" on certain firmware).
        data.module_battery = await self._try_read(sx3.get_module_battery_level)
        data.bike_firmware = await self._try_read(sx3.get_bike_firmware_version)
        errors = await self._try_read(sx3.get_errors)
        data.has_error = bool(errors and any(errors))
        charging = await self._try_read(sx3.get_motor_battery_state)
        data.charging = bool(charging) if charging is not None else None
        return data

    async def _try_read(
        self, read: Callable[[], Awaitable[_T]]
    ) -> _T | None:
        """Run an optional read; swallow failures so one bad characteristic
        doesn't fail the whole poll."""
        try:
            return await read()
        except Exception as err:  # noqa: BLE001 - optional, best-effort
            _LOGGER.debug("optional read %s failed: %s", read.__name__, err)
            return None

    async def async_set_lock(self, *, locked: bool) -> None:
        """Set lock state, then refresh so the lock entity reflects reality."""
        # Verified against pymoof 0.0.6 source:
        # LockState.UNLOCKED = 0x00, LOCKED = 0x01, AWAITING_UNLOCK = 0x02.
        target = LockState.LOCKED if locked else LockState.UNLOCKED
        await self._with_client(lambda sx3: sx3.set_lock_state(target))
        await self.async_request_refresh()
