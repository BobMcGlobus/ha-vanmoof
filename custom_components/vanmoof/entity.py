"""Base entity for VanMoof."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import VanMoofCoordinator


class VanMoofEntity(CoordinatorEntity[VanMoofCoordinator]):
    """Common device info + availability for all VanMoof entities.

    ``available`` is handled by CoordinatorEntity: when a poll fails (bike out
    of range), all entities go unavailable automatically.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator: VanMoofCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            connections={(CONNECTION_BLUETOOTH, coordinator.address)},
            identifiers={(DOMAIN, coordinator.address)},
            manufacturer="VanMoof",
            model=coordinator.model or "S3 / X3",
            # Use the entry title so multiple bikes get distinct device names
            # (e.g. "ES3-F88A", "Fahrrad Lol") instead of all being "VanMoof".
            name=coordinator.entry.title,
            serial_number=coordinator.frame_number,
            sw_version=(
                coordinator.data.bike_firmware if coordinator.data else None
            ),
        )
