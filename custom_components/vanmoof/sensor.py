"""Sensor platform for VanMoof."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, PERCENTAGE, UnitOfLength, UnitOfSpeed
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.util import dt as dt_util

from .coordinator import VanMoofConfigEntry, VanMoofCoordinator, VanMoofData
from .entity import VanMoofEntity


@dataclass(frozen=True, kw_only=True)
class VanMoofSensorDescription(SensorEntityDescription):
    """Describes a VanMoof sensor."""

    value_fn: Callable[[VanMoofData], StateType]
    # How long to keep showing the last value when polls fail (bike out of range):
    #   None       -> follow the coordinator (unavailable on the first failed poll)
    #   "forever"  -> always keep the last value (static/monotonic data)
    #   timedelta  -> keep it for that long after the last successful poll
    retain: Literal["forever"] | timedelta | None = None


SENSORS: tuple[VanMoofSensorDescription, ...] = (
    VanMoofSensorDescription(
        key="battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.battery,
        retain=timedelta(hours=2),
    ),
    VanMoofSensorDescription(
        key="distance",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: data.distance_km,
        retain="forever",
    ),
    VanMoofSensorDescription(
        key="speed",
        device_class=SensorDeviceClass.SPEED,
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.speed_kmh,
    ),
    VanMoofSensorDescription(
        key="gear",
        translation_key="gear",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.gear,
        retain=timedelta(hours=2),
    ),
    VanMoofSensorDescription(
        key="module_battery",
        translation_key="module_battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.module_battery,
    ),
    VanMoofSensorDescription(
        key="frame_number",
        translation_key="frame_number",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.frame_number,
        retain="forever",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VanMoofConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up VanMoof sensors from a config entry."""
    coordinator = entry.runtime_data
    async_add_entities(
        VanMoofSensor(coordinator, description) for description in SENSORS
    )


class VanMoofSensor(VanMoofEntity, SensorEntity):
    """A VanMoof sensor backed by the coordinator snapshot."""

    entity_description: VanMoofSensorDescription

    def __init__(
        self,
        coordinator: VanMoofCoordinator,
        description: VanMoofSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.address}_{description.key}"

    @property
    def available(self) -> bool:
        retain = self.entity_description.retain
        # No retention: follow the coordinator (unavailable when a poll fails).
        if retain is None:
            return super().available
        if self.coordinator.data is None:
            return False
        # Fresh poll, or "forever": available.
        if super().available or retain == "forever":
            return True
        # Bounded window: keep the last value only for `retain` past last success.
        last = self.coordinator.last_success_time
        return last is not None and dt_util.utcnow() - last <= retain

    @property
    def native_value(self) -> StateType:
        if (data := self.coordinator.data) is None:
            return None
        return self.entity_description.value_fn(data)
