"""DataUpdateCoordinator for VanMoof.

Owns the BLE lifecycle. Each cycle opens a short-lived, authenticated session
to the bike, reads state, and disconnects. Home Assistant's Bluetooth stack
transparently routes the connection through the local adapter or whichever
ESPHome proxy can currently reach the bike.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import logging
from typing import TypeVar

from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection
from pymoof.clients.sx3 import LockState, SX3Client

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_KEY, CONF_USER_KEY_ID, DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

_T = TypeVar("_T")

type VanMoofConfigEntry = ConfigEntry[VanMoofCoordinator]


@dataclass
class VanMoofData:
    """Snapshot of bike state from one poll."""

    battery: int
    distance_km: float
    speed_kmh: int
    lock_state: LockState


class VanMoofCoordinator(DataUpdateCoordinator[VanMoofData]):
    """Connects to the bike over BLE, authenticates, and polls state."""

    def __init__(self, hass: HomeAssistant, entry: VanMoofConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.entry = entry
        self.address: str = entry.data[CONF_ADDRESS]
        self._key: str = entry.data[CONF_KEY]
        self._user_key_id: int = entry.data[CONF_USER_KEY_ID]

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

        client = await establish_connection(
            BleakClientWithServiceCache, ble_device, self.address
        )
        try:
            sx3 = SX3Client(client, self._key, self._user_key_id)
            # NOTE: pymoof's authenticate() returns silently even on failure.
            # The first authenticated read below is what actually surfaces a
            # bad key (as a BleakError).
            await sx3.authenticate()
            return await action(sx3)
        except BleakError as err:
            raise UpdateFailed(f"BLE error talking to the bike: {err}") from err
        finally:
            await client.disconnect()

    async def _read_all(self, sx3: SX3Client) -> VanMoofData:
        return VanMoofData(
            battery=await sx3.get_battery_level(),
            distance_km=await sx3.get_distance_travelled(),
            speed_kmh=await sx3.get_speed(),
            lock_state=await sx3.get_lock_state(),
        )

    async def async_set_lock(self, *, locked: bool) -> None:
        """Set lock state, then refresh so the lock entity reflects reality."""
        # Verified against pymoof 0.0.6 source:
        # LockState.UNLOCKED = 0x00, LOCKED = 0x01, AWAITING_UNLOCK = 0x02.
        target = LockState.LOCKED if locked else LockState.UNLOCKED
        await self._with_client(lambda sx3: sx3.set_lock_state(target))
        await self.async_request_refresh()
