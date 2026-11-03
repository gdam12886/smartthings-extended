"""Appliance commands, oven clock synchronization, and hood timer buttons."""

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util
from pysmartthings import Attribute, Capability, Command

from . import ExtendedConfigEntry
from .appliances import appliance_components, can_start, cavity_active, enabled, supports_clock_sync
from .coordinator import HoodCoordinator
from .entity import ApplianceEntity, HoodEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ExtendedConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    runtime = entry.runtime_data
    if "appliance" in runtime.features:
        coordinator = runtime.coordinator
        known: set[tuple[str, str, Command]] = set()

        @callback
        def discover() -> None:
            entities: list[ButtonEntity] = []
            for device_id, component in appliance_components(coordinator):
                for capability, command in (
                    (Capability.OVEN_OPERATING_STATE, Command.STOP),
                    (Capability.OVEN_OPERATING_STATE, Command.START),
                    (Capability.REFRESH, Command.REFRESH),
                ):
                    key = (device_id, component, command)
                    if (
                        key not in known
                        and enabled(coordinator, device_id, component, capability)
                        and (
                            command is not Command.START
                            or can_start(coordinator, device_id, component)
                        )
                    ):
                        entities.append(
                            ApplianceButton(coordinator, device_id, component, capability, command)
                        )
                        known.add(key)
            for device_id in coordinator.data:
                key = (device_id, "main", Command.EXECUTE)
                if key not in known and supports_clock_sync(coordinator, device_id):
                    entities.append(OvenClockSync(coordinator, device_id))
                    known.add(key)
            async_add_entities(entities)

        discover()
        entry.async_on_unload(coordinator.async_add_listener(discover))
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


class OvenClockSync(ApplianceEntity, ButtonEntity):
    """Send the current HA local wall-clock time to Samsung's oven clock resource."""

    _attr_icon = "mdi:clock-check-outline"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: HoodCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "main", "sync_clock", Capability.EXECUTE)

    @property
    def available(self) -> bool:
        return super().available and supports_clock_sync(self.coordinator, self.device_id)

    async def async_press(self) -> None:
        if not supports_clock_sync(self.coordinator, self.device_id):
            raise ServiceValidationError("Clock synchronization is unavailable on this appliance")
        # Samsung expects local wall time, without a UTC offset or fractional seconds.
        local_time = dt_util.now().strftime("%Y-%m-%dT%H:%M:%S")
        await self.execute(
            Command.EXECUTE,
            ["/configuration/vs/0", {"x.com.samsung.da.currentTime": local_time}],
        )


class ApplianceButton(ApplianceEntity, ButtonEntity):
    def __init__(
        self,
        coordinator: HoodCoordinator,
        device_id: str,
        component: str,
        capability: Capability,
        command: Command,
    ) -> None:
        key = "refresh" if command is Command.REFRESH else f"oven_{command.value}"
        super().__init__(coordinator, device_id, component, key, capability)
        self.command = command
        self._attr_icon = {
            Command.REFRESH: "mdi:refresh",
            Command.STOP: "mdi:stop",
            Command.START: "mdi:play",
        }[command]

    @property
    def available(self) -> bool:
        return (
            super().available
            and (
                self.command is Command.REFRESH
                or cavity_active(self.coordinator, self.device_id, self.component)
            )
            and (
                self.command is not Command.START
                or can_start(self.coordinator, self.device_id, self.component)
            )
        )

    async def async_press(self) -> None:
        if self.command is Command.START:
            if not can_start(self.coordinator, self.device_id, self.component):
                raise ServiceValidationError(
                    "This oven component has not reported usable remote-start support"
                )
            await self.execute(
                Command.START, [self.attribute_value(Attribute.OVEN_MODE, Capability.OVEN_MODE)]
            )
        else:
            await self.execute(self.command)
            if self.command is Command.REFRESH:
                await self.coordinator.async_request_refresh()
