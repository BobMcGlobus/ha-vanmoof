"""Select platform for VanMoof: assist level, light mode, bell tone."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import VanMoofConfigEntry, VanMoofCoordinator
from .entity import VanMoofEntity
from .pymoof_vendor.clients.sx3 import BellTone

# Light mode raw value <-> option. This mapping is a best guess and should be
# confirmed against the bike (select each, watch the light).
LIGHT_MODES: dict[str, int] = {"off": 0, "auto": 1, "on": 2}
LIGHT_MODES_REV = {v: k for k, v in LIGHT_MODES.items()}

BELL_TONES: dict[str, BellTone] = {
    "bell": BellTone.BELL,
    "boat": BellTone.BOAT,
    "party": BellTone.PARTY,
}
BELL_TONES_REV = {tone.value: name for name, tone in BELL_TONES.items()}

# 0 = off, 1..4 = assist levels.
ASSIST_LEVELS = [str(i) for i in range(5)]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VanMoofConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the VanMoof selects."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            VanMoofAssistSelect(coordinator),
            VanMoofLightSelect(coordinator),
            VanMoofBellToneSelect(coordinator),
        ]
    )


class VanMoofAssistSelect(VanMoofEntity, SelectEntity):
    """Power-assist level (0 = off, 1-4)."""

    _attr_translation_key = "assist_level"
    _attr_options = ASSIST_LEVELS

    def __init__(self, coordinator: VanMoofCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_assist_level"

    @property
    def current_option(self) -> str | None:
        if (data := self.coordinator.data) is None or data.assist_level is None:
            return None
        option = str(data.assist_level)
        return option if option in self._attr_options else None

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_assist(int(option))


class VanMoofLightSelect(VanMoofEntity, SelectEntity):
    """Light mode (off / auto / on)."""

    _attr_translation_key = "light"
    _attr_options = list(LIGHT_MODES)

    def __init__(self, coordinator: VanMoofCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_light"

    @property
    def current_option(self) -> str | None:
        if (data := self.coordinator.data) is None or data.light_mode is None:
            return None
        return LIGHT_MODES_REV.get(data.light_mode)

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_light_mode(LIGHT_MODES[option])


class VanMoofBellToneSelect(VanMoofEntity, SelectEntity):
    """Which tone the bell plays."""

    _attr_translation_key = "bell_tone"
    _attr_options = list(BELL_TONES)

    def __init__(self, coordinator: VanMoofCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_bell_tone"

    @property
    def current_option(self) -> str | None:
        if (data := self.coordinator.data) is None or data.bell_tone is None:
            return None
        return BELL_TONES_REV.get(data.bell_tone)

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_bell_tone(BELL_TONES[option])
