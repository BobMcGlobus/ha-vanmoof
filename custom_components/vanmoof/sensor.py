"""Sensor platform for VanMoof."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

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

from .coordinator import VanMoofConfigEntry, VanMoofCoordinator, VanMoofData
from .entity import VanMoofEntity


@dataclass(frozen=True, kw_only=True)
class VanMoofSensorDescription(SensorEntityDescription):
    """Describes a VanMoof sensor."""

    value_fn: Callable[[VanMoofData], StateType]


SENSORS: tuple[VanMoofSensorDescription, ...] = (
    VanMoofSensorDescription(
        key="battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.battery,
    ),
    VanMoofSensorDescription(
        key="distance",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: data.distance_km,
    ),
    VanMoofSensorDescription(
        key="speed",
        device_class=SensorDeviceClass.SPEED,
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.speed_kmh,
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
    def native_value(self) -> StateType:
        return self.entity_description.value_fn(self.coordinator.data)
