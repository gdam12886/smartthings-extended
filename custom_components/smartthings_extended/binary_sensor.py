"""Report the connection between the cooktop and its hood."""

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
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
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        HoodConnection(coordinator, device_id)
        for device_id, device in coordinator.data.items()
        if Capability.SAMSUNG_CE_CONNECTION_STATE in device.status
    )


class HoodConnection(HoodEntity, BinarySensorEntity):
    _attr_translation_key = "hood_connection"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: HoodCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "connection")

    @property
    def available(self) -> bool:
        return (
            self.coordinator.last_update_success
            and self.coordinator.source_available
            and self.coordinator.data[self.device_id].online
        )

    @property
    def is_on(self) -> bool | None:
        state = self.attribute_value(
            Capability.SAMSUNG_CE_CONNECTION_STATE, Attribute.CONNECTION_STATE
        )
        return state == "connected" if state in ("connected", "disconnected") else None
