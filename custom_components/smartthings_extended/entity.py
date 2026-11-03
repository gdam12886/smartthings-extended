"""Shared entities and attribute handling for the selected hood features."""

from __future__ import annotations

from typing import Any

from homeassistant.const import UnitOfTime
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util.unit_conversion import DurationConverter
from pysmartthings import Attribute, Capability

from .const import DOMAIN
from .coordinator import HoodCoordinator

TIMER_UNITS = {"hour": UnitOfTime.HOURS, "min": UnitOfTime.MINUTES, "sec": UnitOfTime.SECONDS}


class HoodEntity(CoordinatorEntity[HoodCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: HoodCoordinator, device_id: str, key: str) -> None:
        super().__init__(coordinator)
        self.device_id = device_id
        self._attr_unique_id = f"{device_id}_hood_{key}"
        device = coordinator.data[device_id]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)}, name=device.name, manufacturer=device.manufacturer
        )

    @property
    def available(self) -> bool:
        if (
            not super().available
            or not self.coordinator.source_available
            or not self.coordinator.data[self.device_id].online
        ):
            return False
        status = self.coordinator.data[self.device_id].status
        return (
            Capability.SAMSUNG_CE_CONNECTION_STATE not in status
            or self.attribute_value(
                Capability.SAMSUNG_CE_CONNECTION_STATE, Attribute.CONNECTION_STATE
            )
            == "connected"
        )

    def attribute_value(self, capability: Capability, attribute: Attribute) -> Any:
        return self.coordinator.value(self.device_id, capability, attribute)

    def timer_minutes(self, attribute: Attribute) -> float | None:
        status = (
            self.coordinator.data[self.device_id]
            .status.get(Capability.SAMSUNG_CE_COUNT_DOWN_TIMER, {})
            .get(attribute)
        )
        if status is None or status.value is None or not isinstance(status.value, (int, float)):
            return None
        unit = TIMER_UNITS.get(status.unit or "min")
        return (
            DurationConverter.convert(status.value, unit, UnitOfTime.MINUTES)
            if unit is not None
            else None
        )
