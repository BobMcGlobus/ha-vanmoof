"""Lock platform for VanMoof."""

from __future__ import annotations

from typing import Any

from pymoof.clients.sx3 import LockState

from homeassistant.components.lock import LockEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import VanMoofConfigEntry, VanMoofCoordinator
from .entity import VanMoofEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VanMoofConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the VanMoof lock from a config entry."""
    async_add_entities([VanMoofLock(entry.runtime_data)])


class VanMoofLock(VanMoofEntity, LockEntity):
    """The bike's digital lock."""

    # The lock is the primary feature of the device, so it takes the device name.
    _attr_name = None

    def __init__(self, coordinator: VanMoofCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_lock"

    @property
    def is_locked(self) -> bool | None:
        if (data := self.coordinator.data) is None:
            return None
        # AWAITING_UNLOCK (0x02) reports as not-locked; only 0x01 is locked.
        return data.lock_state == LockState.LOCKED

    async def async_lock(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_lock(locked=True)

    async def async_unlock(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_lock(locked=False)
