"""Report the connection between the cooktop and its hood."""

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from pysmartthings import Attribute, Capability

from . import ExtendedConfigEntry
from .appliances import BINARY_SENSORS, BinaryProfile, appliance_components, category, enabled
from .coordinator import HoodCoordinator
from .entity import ApplianceEntity, HoodEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ExtendedConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    if "appliance" in entry.runtime_data.features:
        async_add_entities(
            ApplianceBinarySensor(coordinator, device_id, component, profile)
            for device_id, component in appliance_components(coordinator)
            for profile in BINARY_SENSORS
            if enabled(coordinator, device_id, component, profile.capability)
        )
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


class ApplianceBinarySensor(ApplianceEntity, BinarySensorEntity):
    def __init__(
        self, coordinator: HoodCoordinator, device_id: str, component: str, profile: BinaryProfile
    ) -> None:
        super().__init__(coordinator, device_id, component, profile.key, profile.capability)
        self.profile = profile
        self._attr_device_class = profile.device_class
        self._attr_entity_category = category(profile.diagnostic)

    @property
    def is_on(self) -> bool | None:
        value = self.attribute_value(self.profile.attribute)
        if value is None:
            return None
        # pysmartthings may deserialize JSON booleans as strings in Status.value.
        if isinstance(self.profile.on_value, bool) and isinstance(value, str):
            if value.lower() not in ("true", "false"):
                return None
            value = value.lower() == "true"
        if value == self.profile.on_value:
            return True
        if value == self.profile.off_value:
            return False
        return None
