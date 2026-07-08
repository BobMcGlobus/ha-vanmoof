"""Binary sensor platform for VanMoof: passive in-range presence."""

from __future__ import annotations

from homeassistant.components import bluetooth
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.components.bluetooth import (
    BluetoothCallbackMatcher,
    BluetoothChange,
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import VanMoofConfigEntry, VanMoofCoordinator
from .entity import VanMoofEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VanMoofConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the VanMoof binary sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            VanMoofInRange(coordinator),
            VanMoofProblem(coordinator),
            VanMoofCharging(coordinator),
        ]
    )


class VanMoofInRange(BinarySensorEntity):
    """Is the bike advertising nearby right now?

    Independent of the poll coordinator: it listens passively to BLE
    advertisements from any adapter or ESPHome proxy (``connectable=False``), so
    it flips off shortly after the bike leaves range — useful for arrival and,
    more importantly, departure / theft detection. It stays available even when
    a poll fails, and never opens a connection itself.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "in_range"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_should_poll = False

    def __init__(self, coordinator: VanMoofCoordinator) -> None:
        self._address = coordinator.address
        self._attr_unique_id = f"{coordinator.address}_in_range"
        self._attr_device_info = DeviceInfo(
            connections={(CONNECTION_BLUETOOTH, coordinator.address)},
            identifiers={(DOMAIN, coordinator.address)},
        )

    async def async_added_to_hass(self) -> None:
        """Seed current state and subscribe to advertisement / unavailable events."""
        self._attr_is_on = bluetooth.async_address_present(
            self.hass, self._address, connectable=False
        )
        self.async_on_remove(
            bluetooth.async_register_callback(
                self.hass,
                self._async_seen,
                BluetoothCallbackMatcher(
                    address=self._address, connectable=False
                ),
                BluetoothScanningMode.PASSIVE,
            )
        )
        self.async_on_remove(
            bluetooth.async_track_unavailable(
                self.hass,
                self._async_unavailable,
                self._address,
                connectable=False,
            )
        )

    @callback
    def _async_seen(
        self, service_info: BluetoothServiceInfoBleak, change: BluetoothChange
    ) -> None:
        if self._attr_is_on is not True:
            self._attr_is_on = True
            self.async_write_ha_state()

    @callback
    def _async_unavailable(self, service_info: BluetoothServiceInfoBleak) -> None:
        if self._attr_is_on is not False:
            self._attr_is_on = False
            self.async_write_ha_state()


class VanMoofProblem(VanMoofEntity, BinarySensorEntity):
    """On when the bike reports a non-zero error field."""

    _attr_translation_key = "problem"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: VanMoofCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_problem"

    @property
    def is_on(self) -> bool | None:
        if (data := self.coordinator.data) is None:
            return None
        return data.has_error


class VanMoofCharging(VanMoofEntity, BinarySensorEntity):
    """On while the main battery is charging (MOTOR_BATTERY_STATE != 0)."""

    _attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING

    def __init__(self, coordinator: VanMoofCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_charging"

    @property
    def is_on(self) -> bool | None:
        if (data := self.coordinator.data) is None:
            return None
        return data.charging
