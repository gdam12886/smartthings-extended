"""Start and cancel the native hood countdown."""

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from pysmartthings import Attribute, Capability, Command

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
            HoodTimerButton(runtime.coordinator, device_id, command)
            for device_id, device in runtime.coordinator.data.items()
            if Capability.SAMSUNG_CE_COUNT_DOWN_TIMER in device.status
            for command in (Command.START, Command.CANCEL)
        )


class HoodTimerButton(HoodEntity, ButtonEntity):
    def __init__(self, coordinator: HoodCoordinator, device_id: str, command: Command) -> None:
        super().__init__(coordinator, device_id, f"timer_{command.value}")
        self.command = command
        self._attr_translation_key = f"hood_timer_{command.value}"
        self._attr_icon = (
            "mdi:timer-play-outline" if command is Command.START else "mdi:timer-cancel-outline"
        )

    async def async_press(self) -> None:
        if self.command is Command.START:
            if self.attribute_value(Capability.SWITCH, Attribute.SWITCH) != "on":
                raise ServiceValidationError("Turn on the hood fan before starting its timer")
            duration = self.timer_minutes(Attribute.START_VALUE)
            if duration is None or duration <= 0:
                raise ServiceValidationError(
                    "Set a positive hood timer duration before starting it"
                )
        await self.coordinator.command(
            self.device_id, Capability.SAMSUNG_CE_COUNT_DOWN_TIMER, self.command
        )
