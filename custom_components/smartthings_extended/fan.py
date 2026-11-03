"""Fan controls for a hood connected through a Samsung cooktop."""

from __future__ import annotations

from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util.percentage import (
    ordered_list_item_to_percentage,
    percentage_to_ordered_list_item,
)
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
    if "fan" in runtime.features:
        async_add_entities(
            HoodFan(runtime.coordinator, device_id)
            for device_id, device in runtime.coordinator.data.items()
            if Capability.SAMSUNG_CE_HOOD_FAN_SPEED in device.status
            and Capability.SWITCH in device.status
        )


class HoodFan(HoodEntity, FanEntity):
    _attr_translation_key = "hood_fan"
    _attr_supported_features = (
        FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF | FanEntityFeature.SET_SPEED
    )

    def __init__(self, coordinator: HoodCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "fan")

    @property
    def speeds(self) -> list[int]:
        supported = (
            self.attribute_value(
                Capability.SAMSUNG_CE_HOOD_FAN_SPEED, Attribute.SUPPORTED_HOOD_FAN_SPEED
            )
            or []
        )
        return [speed for speed in supported if isinstance(speed, int) and speed > 0]

    @property
    def available(self) -> bool:
        return (
            super().available
            and bool(self.speeds)
            and self.attribute_value(Capability.SWITCH, Attribute.SWITCH) in ("on", "off")
        )

    @property
    def speed_count(self) -> int:
        return len(self.speeds)

    @property
    def is_on(self) -> bool | None:
        switch = self.attribute_value(Capability.SWITCH, Attribute.SWITCH)
        return switch == "on" if switch in ("on", "off") else None

    @property
    def percentage(self) -> int | None:
        if self.is_on is False:
            return 0
        speed = self.attribute_value(Capability.SAMSUNG_CE_HOOD_FAN_SPEED, Attribute.HOOD_FAN_SPEED)
        if speed == 0:
            return 0
        return ordered_list_item_to_percentage(self.speeds, speed) if speed in self.speeds else None

    async def async_set_percentage(self, percentage: int) -> None:
        if percentage == 0:
            await self.async_turn_off()
            return
        if not self.speeds:
            raise ServiceValidationError("The hood has not reported its supported fan speeds")
        if not self.is_on:
            await self.coordinator.command(self.device_id, Capability.SWITCH, Command.ON)
        await self.coordinator.command(
            self.device_id,
            Capability.SAMSUNG_CE_HOOD_FAN_SPEED,
            Command.SET_HOOD_FAN_SPEED,
            percentage_to_ordered_list_item(self.speeds, percentage),
        )

    async def async_turn_on(
        self, percentage: int | None = None, preset_mode: str | None = None, **kwargs: Any
    ) -> None:
        if percentage is not None:
            await self.async_set_percentage(percentage)
        else:
            await self.coordinator.command(self.device_id, Capability.SWITCH, Command.ON)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.command(self.device_id, Capability.SWITCH, Command.OFF)
