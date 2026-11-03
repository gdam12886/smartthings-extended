"""Set the hood's native countdown duration."""

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util.unit_conversion import DurationConverter
from pysmartthings import Attribute, Capability, Command

from . import ExtendedConfigEntry
from .coordinator import HoodCoordinator
from .entity import TIMER_UNITS, HoodEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ExtendedConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    runtime = entry.runtime_data
    if "timer" in runtime.features:
        async_add_entities(
            HoodTimerDuration(runtime.coordinator, device_id, runtime.timer_max)
            for device_id, device in runtime.coordinator.data.items()
            if Capability.SAMSUNG_CE_COUNT_DOWN_TIMER in device.status
        )


class HoodTimerDuration(HoodEntity, NumberEntity):
    _attr_translation_key = "hood_timer_duration"
    _attr_native_min_value = 1
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:timer-cog-outline"

    def __init__(self, coordinator: HoodCoordinator, device_id: str, maximum: int) -> None:
        super().__init__(coordinator, device_id, "timer_duration")
        self._attr_native_max_value = maximum

    @property
    def native_value(self) -> float | None:
        return self.timer_minutes(Attribute.START_VALUE)

    async def async_set_native_value(self, value: float) -> None:
        status = self.coordinator.data[self.device_id].status[
            Capability.SAMSUNG_CE_COUNT_DOWN_TIMER
        ][Attribute.START_VALUE]
        raw_unit = status.unit or "min"
        if raw_unit not in TIMER_UNITS:
            raise ServiceValidationError("The hood reported an unsupported timer unit")
        native_value = DurationConverter.convert(value, UnitOfTime.MINUTES, TIMER_UNITS[raw_unit])
        await self.coordinator.command(
            self.device_id,
            Capability.SAMSUNG_CE_COUNT_DOWN_TIMER,
            Command.SET_START_VALUE,
            [native_value, raw_unit],
        )
