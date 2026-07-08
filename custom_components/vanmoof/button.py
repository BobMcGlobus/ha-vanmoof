"""Button platform for VanMoof."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import VanMoofConfigEntry, VanMoofCoordinator
from .entity import VanMoofEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VanMoofConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the VanMoof buttons."""
    coordinator = entry.runtime_data
    async_add_entities(
        [VanMoofRefreshButton(coordinator), VanMoofBellButton(coordinator)]
    )


class VanMoofRefreshButton(VanMoofEntity, ButtonEntity):
    """Force an immediate poll (connect -> read) instead of waiting."""

    _attr_translation_key = "refresh"

    def __init__(self, coordinator: VanMoofCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_refresh"

    @property
    def available(self) -> bool:
        # Stay pressable even when the bike is currently unavailable, so the user
        # can trigger a fresh connection attempt on demand.
        return True

    async def async_press(self) -> None:
        await self.coordinator.async_request_refresh()


class VanMoofBellButton(VanMoofEntity, ButtonEntity):
    """Ring the bell / horn. Note: opens a BLE session, so there's a few
    seconds' delay — fine for locating the bike, not for traffic."""

    _attr_translation_key = "bell"

    def __init__(self, coordinator: VanMoofCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_bell"

    async def async_press(self) -> None:
        await self.coordinator.async_ring_bell()
