"""The VanMoof integration."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from .const import PLATFORMS
from .coordinator import VanMoofConfigEntry, VanMoofCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: VanMoofConfigEntry) -> bool:
    """Set up VanMoof from a config entry."""
    coordinator = VanMoofCoordinator(hass, entry)
    # Raises ConfigEntryNotReady (and retries setup) if the bike is unreachable.
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # Apply a changed poll interval (options flow) by reloading the entry.
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: VanMoofConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(
    hass: HomeAssistant, entry: VanMoofConfigEntry
) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)
