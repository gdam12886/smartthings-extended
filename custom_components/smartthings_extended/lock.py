"""Child-lock controls only when the appliance advertises an enabled control."""

from homeassistant.components.lock import LockEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from pysmartthings import Attribute, Capability, Command

from . import ExtendedConfigEntry
from .appliances import appliance_components, enabled
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
            ApplianceChildLock(coordinator, device_id, component)
            for device_id, component in appliance_components(coordinator)
            if enabled(coordinator, device_id, component, Capability.SAMSUNG_CE_KIDS_LOCK_CONTROL)
        )


class ApplianceChildLock(ApplianceEntity, LockEntity):
    def __init__(self, coordinator: HoodCoordinator, device_id: str, component: str) -> None:
        super().__init__(
            coordinator,
            device_id,
            component,
            "child_lock_control",
            Capability.SAMSUNG_CE_KIDS_LOCK_CONTROL,
        )

    @property
    def is_locked(self) -> bool | None:
        value = self.attribute_value(Attribute.LOCK_STATE)
        return value == "locked" if value in ("locked", "unlocked") else None

    async def async_lock(self, **kwargs) -> None:
        await self.execute(Command.LOCK)

    async def async_unlock(self, **kwargs) -> None:
        await self.execute(Command.UNLOCK)
