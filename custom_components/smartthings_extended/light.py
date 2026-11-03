"""Control the lamp independently of the hood fan's switch."""

from typing import Any

from homeassistant.components.light import ColorMode, LightEntity
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
    if "light" in runtime.features:
        async_add_entities(
            HoodLight(runtime.coordinator, device_id)
            for device_id, device in runtime.coordinator.data.items()
            if Capability.SAMSUNG_CE_LAMP in device.status
        )


class HoodLight(HoodEntity, LightEntity):
    _attr_translation_key = "hood_light"
    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}

    def __init__(self, coordinator: HoodCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "light")

    @property
    def is_on(self) -> bool | None:
        level = self.attribute_value(Capability.SAMSUNG_CE_LAMP, Attribute.BRIGHTNESS_LEVEL)
        return level != "off" if level is not None else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        levels = (
            self.attribute_value(Capability.SAMSUNG_CE_LAMP, Attribute.SUPPORTED_BRIGHTNESS_LEVEL)
            or []
        )
        on_levels = [level for level in levels if level != "off"]
        if not on_levels:
            raise ServiceValidationError("The hood has not reported supported lamp settings")
        await self.coordinator.command(
            self.device_id,
            Capability.SAMSUNG_CE_LAMP,
            Command.SET_BRIGHTNESS_LEVEL,
            "high" if "high" in on_levels else on_levels[-1],
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.command(
            self.device_id, Capability.SAMSUNG_CE_LAMP, Command.SET_BRIGHTNESS_LEVEL, "off"
        )
