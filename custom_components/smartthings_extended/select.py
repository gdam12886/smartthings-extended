"""Offer only oven modes explicitly reported by the selected component."""

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from pysmartthings import Attribute, Capability, Command

from . import ExtendedConfigEntry
from .appliances import (
    appliance_components,
    cavity_active,
    enabled,
    oven_modes,
    remote_control_permitted,
)
from .coordinator import HoodCoordinator
from .entity import ApplianceEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ExtendedConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    if "appliance" not in entry.runtime_data.features:
        return
    coordinator = entry.runtime_data.coordinator
    known: set[tuple[str, str, Capability]] = set()

    @callback
    def discover() -> None:
        entities = []
        for device_id, component in appliance_components(coordinator):
            for capability in (Capability.SAMSUNG_CE_OVEN_MODE, Capability.OVEN_MODE):
                key = (device_id, component, capability)
                if (
                    key not in known
                    and enabled(coordinator, device_id, component, capability)
                    and oven_modes(coordinator, device_id, component, capability)
                ):
                    entities.append(OvenMode(coordinator, device_id, component, capability))
                    known.add(key)
        async_add_entities(entities)

    discover()
    entry.async_on_unload(coordinator.async_add_listener(discover))


class OvenMode(ApplianceEntity, SelectEntity):
    def __init__(
        self, coordinator: HoodCoordinator, device_id: str, component: str, capability: Capability
    ) -> None:
        key = (
            "samsung_oven_mode_control"
            if capability is Capability.SAMSUNG_CE_OVEN_MODE
            else "oven_mode_control"
        )
        super().__init__(coordinator, device_id, component, key, capability)

    @property
    def options(self) -> list[str]:
        return oven_modes(self.coordinator, self.device_id, self.component, self.capability)

    @property
    def available(self) -> bool:
        return (
            super().available
            and bool(self.options)
            and cavity_active(self.coordinator, self.device_id, self.component)
            and remote_control_permitted(self.coordinator, self.device_id, self.component)
        )

    @property
    def current_option(self) -> str | None:
        value = self.attribute_value(Attribute.OVEN_MODE)
        return value if value in self.options else None

    async def async_select_option(self, option: str) -> None:
        if option not in self.options:
            raise ServiceValidationError(
                "This oven component has not reported support for that mode"
            )
        await self.execute(Command.SET_OVEN_MODE, option)
