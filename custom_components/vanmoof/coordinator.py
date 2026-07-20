"""DataUpdateCoordinator for VanMoof.

Owns the BLE lifecycle. Each cycle opens a short-lived, authenticated session
to the bike, reads state, and disconnects. Home Assistant's Bluetooth stack
transparently routes the connection through the local adapter or whichever
ESPHome proxy can currently reach the bike.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import contextlib
from dataclasses import dataclass
from datetime import datetime, timedelta
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
from homeassistant.util import dt as dt_util

from .const import (
    CONF_FRAME_NUMBER,
    CONF_KEY,
    CONF_MODEL,
    CONF_USER_KEY_ID,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
)
from .pymoof_vendor.clients.sx3 import BellTone, LockState, Sound, SX3Client

# Escalate to a reauth flow only after this many consecutive failures that
# happen *after* a successful connection AND before the entry has ever polled
# successfully. Set high so a flaky connection at setup (incomplete GATT
# discovery, proxy contention) doesn't get mistaken for a bad key; a genuinely
# wrong key keeps failing and still surfaces eventually.
_AUTH_FAILURE_THRESHOLD = 5

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
    gear: int | None = None
    assist_level: int | None = None
    light_mode: int | None = None
    bell_tone: int | None = None


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
        # Once a poll has ever succeeded, the key is proven correct, so later
        # post-connect failures are transient (never a bad key) and must NOT
        # trigger reauth. Reauth stays reserved for a genuinely wrong key at
        # setup (before any success).
        self._had_success = False
        # When the last poll succeeded; sensors use it to keep showing a stale
        # value for a bounded window (e.g. battery/gear for 2h) before going
        # unavailable.
        self.last_success_time: datetime | None = None
        # The bike accepts only one BLE connection at a time, and both the poll
        # and one-off writes (lock, bell, selects, Refresh) open a session. This
        # lock serialises them so we never open two connections at once (which
        # the bike rejects with GATT "Unlikely error" / 133).
        self._lock = asyncio.Lock()

    async def _async_update_data(self) -> VanMoofData:
        data = await self._with_client(self._read_all)
        self._had_success = True
        self.last_success_time = dt_util.utcnow()
        return data

    async def _with_client(
        self, action: Callable[[SX3Client], Awaitable[_T]]
    ) -> _T:
        """Serialise BLE sessions so only one connection is ever open."""
        async with self._lock:
            return await self._locked_with_client(action)

    async def _locked_with_client(
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
            # A stale cached GATT table (e.g. after the bike's smart module
            # reboots) makes reads fail persistently with "Unlikely error"
            # (ATT 0x0E) that a normal retry — or the Refresh button — can't fix,
            # because HA caches the services on disk. Drop the cache so the next
            # connect rediscovers the services.
            with contextlib.suppress(Exception):
                await client.clear_cache()
            # Failure *after* a successful connect. Usually a wrong key, but
            # could be a one-off glitch, so only escalate to reauth once it
            # keeps happening.
            self._post_connect_failures += 1
            # Only a bike that has NEVER polled successfully can have a bad key;
            # once proven, treat everything as transient (avoids false "auth
            # expired" prompts from momentary BLE glitches).
            if (
                not self._had_success
                and self._post_connect_failures >= _AUTH_FAILURE_THRESHOLD
            ):
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
        distance_km = await sx3.get_distance_travelled()
        speed_kmh = await sx3.get_speed()
        lock_state = await sx3.get_lock_state()
        # Optional reads: best-effort, never fail the poll (some characteristics
        # return "Invalid Handle" on certain firmware).
        module_battery = await self._try_read(sx3.get_module_battery_level)
        bike_firmware = await self._try_read(sx3.get_bike_firmware_version)
        errors = await self._try_read(sx3.get_errors)
        charging = await self._try_read(sx3.get_motor_battery_state)
        gear = await self._try_read(sx3.get_gear)
        assist_level = await self._try_read(sx3.get_assist_level)
        light_mode = await self._try_read(sx3.get_light_mode_value)
        bell_tone = await self._try_read(sx3.get_bell_tone)
        # Battery last, with a re-read guard: the S3 reports a placeholder 100 %
        # for the first moment after waking, before the BMS reports the real SoC.
        # Reading it after the round-trips above, then re-reading if it's 100,
        # avoids a spurious 100 % on (re)connect. get_battery_level() reads the
        # motor/main battery.
        battery = await sx3.get_battery_level()
        if battery >= 100:
            await asyncio.sleep(2)
            battery = await sx3.get_battery_level()
        return VanMoofData(
            battery=battery,
            distance_km=distance_km,
            speed_kmh=speed_kmh,
            lock_state=lock_state,
            frame_number=self.frame_number,
            module_battery=module_battery,
            bike_firmware=bike_firmware,
            has_error=bool(errors and any(errors)),
            charging=bool(charging) if charging is not None else None,
            gear=gear,
            assist_level=assist_level,
            light_mode=light_mode,
            bell_tone=bell_tone,
        )

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

    async def async_ring_bell(self) -> None:
        """Ring the bell / horn once (opens a short-lived session to do it)."""
        await self._with_client(lambda sx3: sx3.play_sound(Sound.HORN_1))

    async def async_set_assist(self, level: int) -> None:
        await self._with_client(lambda sx3: sx3.set_power_level(level))
        await self.async_request_refresh()

    async def async_set_light_mode(self, mode: int) -> None:
        await self._with_client(lambda sx3: sx3.set_light_mode(mode))
        await self.async_request_refresh()

    async def async_set_bell_tone(self, tone: BellTone) -> None:
        await self._with_client(lambda sx3: sx3.set_bell_tone(tone))
        await self.async_request_refresh()
