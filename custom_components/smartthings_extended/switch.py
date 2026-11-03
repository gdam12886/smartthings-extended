"""Native appliance power controls."""

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from pysmartthings import Attribute, Capability, Command

from . import ExtendedConfigEntry
from .appliances import appliance_components, enabled, remote_control_permitted
from .coordinator import HoodCoordinator
from .entity import ApplianceEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ExtendedConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    if "appliance" in entry.runtime_data.features:
        coordinator = entry.runtime_data.coordinator
        async_add_entities(
            AppliancePower(coordinator, device_id, component)
            for device_id, component in appliance_components(coordinator)
            if enabled(coordinator, device_id, component, Capability.SWITCH)
        )


class AppliancePower(ApplianceEntity, SwitchEntity):
    def __init__(self, coordinator: HoodCoordinator, device_id: str, component: str) -> None:
        super().__init__(coordinator, device_id, component, "appliance_power", Capability.SWITCH)

    @property
    def is_on(self) -> bool | None:
        value = self.attribute_value(Attribute.SWITCH)
        return value == "on" if value in ("on", "off") else None

    async def async_turn_on(self, **kwargs) -> None:
        if not remote_control_permitted(self.coordinator, self.device_id, self.component):
            raise ServiceValidationError("Remote control is disabled on this appliance")
        await self.execute(Command.ON)

    async def async_turn_off(self, **kwargs) -> None:
        await self.execute(Command.OFF)
