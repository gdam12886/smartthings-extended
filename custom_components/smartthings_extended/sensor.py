"""Display the actual countdown status and remaining time."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util
from pysmartthings import Attribute, Capability

from . import ExtendedConfigEntry
from .appliances import SENSORS, SensorProfile, appliance_components, category, enabled
from .coordinator import HoodCoordinator
from .entity import ApplianceEntity, HoodEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ExtendedConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    runtime = entry.runtime_data
    if "appliance" in runtime.features:
        async_add_entities(
            ApplianceSensor(runtime.coordinator, device_id, component, profile)
            for device_id, component in appliance_components(runtime.coordinator)
            for profile in SENSORS
            if enabled(runtime.coordinator, device_id, component, profile.capability)
        )
    if "timer" in runtime.features:
        async_add_entities(
            entity(runtime.coordinator, device_id)
            for device_id, device in runtime.coordinator.data.items()
            if Capability.SAMSUNG_CE_COUNT_DOWN_TIMER in device.status
            for entity in (HoodTimerStatus, HoodTimerRemaining)
        )


class HoodTimerStatus(HoodEntity, SensorEntity):
    _attr_translation_key = "hood_timer_status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["idle", "running", "paused"]
    _attr_icon = "mdi:timer-outline"

    def __init__(self, coordinator: HoodCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "timer_status")

    @property
    def native_value(self) -> str | None:
        value = self.attribute_value(Capability.SAMSUNG_CE_COUNT_DOWN_TIMER, Attribute.STATUS)
        return value if value in self._attr_options else None


class HoodTimerRemaining(HoodEntity, SensorEntity):
    _attr_translation_key = "hood_timer_remaining"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_icon = "mdi:timer-sand"

    def __init__(self, coordinator: HoodCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "timer_remaining")

    @property
    def native_value(self) -> float | None:
        return self.timer_minutes(Attribute.CURRENT_VALUE)


class ApplianceSensor(ApplianceEntity, SensorEntity):
    def __init__(
        self, coordinator: HoodCoordinator, device_id: str, component: str, profile: SensorProfile
    ) -> None:
        super().__init__(coordinator, device_id, component, profile.key, profile.capability)
        self.profile = profile
        self._attr_device_class = profile.device_class
        self._attr_state_class = profile.state_class
        self._attr_entity_category = category(profile.diagnostic)

    @property
    def native_value(self):
        value = self.attribute_value(self.profile.attribute)
        if self.profile.device_class is SensorDeviceClass.TIMESTAMP:
            parsed = dt_util.parse_datetime(value) if isinstance(value, str) else None
            return parsed if parsed is not None and parsed.tzinfo is not None else None
        if self.profile.device_class is SensorDeviceClass.DATE:
            return dt_util.parse_date(value) if isinstance(value, str) else None
        if self.profile.attribute is Attribute.VERSIONS:
            return (
                "; ".join(
                    f"{item.get('swType', item.get('id', ''))}: {item.get('versionNumber', '')}"
                    for item in value
                    if isinstance(item, dict)
                )[:255]
                if isinstance(value, list)
                else None
            )
        return value if isinstance(value, (str, int, float)) else None

    @property
    def native_unit_of_measurement(self) -> str | None:
        status = (
            self.coordinator.data[self.device_id]
            .components[self.component][self.capability]
            .get(self.profile.attribute)
        )
        # Operation time has no unit on some ovens; do not assume minutes or seconds.
        return status.unit if status is not None else None

    @property
    def extra_state_attributes(self):
        if self.profile.attribute is Attribute.VERSIONS:
            return {"versions": self.attribute_value(Attribute.VERSIONS)}
        return None
