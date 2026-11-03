"""Display the actual countdown status and remaining time."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from pysmartthings import Attribute, Capability

from . import ExtendedConfigEntry
from .coordinator import HoodCoordinator
from .entity import HoodEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ExtendedConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    runtime = entry.runtime_data
    if "timer" in runtime.features:
        async_add_entities(
            entity(runtime.coordinator, device_id)
            for device_id, device in runtime.coordinator.data.items()
            if Capability.SAMSUNG_CE_COUNT_DOWN_TIMER in device.status
            for entity in (HoodTimerStatus, HoodTimerRemaining)
        )


class HoodTimerStatus(HoodEntity, SensorEntity):
    _attr_translation_key = "hood_timer_status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["idle", "running", "paused"]
    _attr_icon = "mdi:timer-outline"

    def __init__(self, coordinator: HoodCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "timer_status")

    @property
    def native_value(self) -> str | None:
        value = self.attribute_value(Capability.SAMSUNG_CE_COUNT_DOWN_TIMER, Attribute.STATUS)
        return value if value in self._attr_options else None


class HoodTimerRemaining(HoodEntity, SensorEntity):
    _attr_translation_key = "hood_timer_remaining"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_icon = "mdi:timer-sand"

    def __init__(self, coordinator: HoodCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "timer_remaining")

    @property
    def native_value(self) -> float | None:
        return self.timer_minutes(Attribute.CURRENT_VALUE)
