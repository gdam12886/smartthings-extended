"""Share the native SmartThings session and subscribe to appliance events."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from pysmartthings import (
    Attribute,
    Capability,
    Command,
    ComponentStatus,
    DeviceEvent,
    DeviceHealthEvent,
    SmartThings,
    SmartThingsError,
    Status,
)
from pysmartthings.models import HealthStatus

from .const import HOOD, NAME
from .native import native_data, source_entry

_LOGGER = logging.getLogger(__name__)


@dataclass
class HoodDevice:
    """Own a raw snapshot so native capability filtering cannot hide controls."""

    components: dict[str, ComponentStatus]
    online: bool
    name: str
    manufacturer: str | None
    model: str | None = None

    @property
    def status(self) -> ComponentStatus:
        """Keep the original hood entity interface and IDs stable."""
        return self.components.get(HOOD, {})


class HoodCoordinator(DataUpdateCoordinator[dict[str, HoodDevice]]):
    """Read once per connection, then consume the native client's push stream."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, source_id: str, device_ids: list[str]
    ) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=NAME, update_interval=None)
        self.entry = entry
        self.source_id = source_id
        self.device_ids = device_ids
        self.client: SmartThings | None = None
        self._subscriptions: list[Callable[[], None]] = []
        self._retry: Callable[[], None] | None = None
        self._recover_task: asyncio.Task | None = None
        self._closed = False

    @staticmethod
    def _model(components: dict[str, ComponentStatus]) -> str | None:
        main = components.get("main", {})
        model = main.get(Capability.SAMSUNG_CE_KITCHEN_DEVICE_IDENTIFICATION, {}).get(
            Attribute.MODEL_CODE
        )
        return model.value if model is not None and isinstance(model.value, str) else None

    @property
    def source_available(self) -> bool:
        """Never use an old client after the native integration unloads."""
        source = source_entry(self.hass, self.source_id)
        data = native_data(source) if source is not None else None
        return not self._closed and data is not None and self.client is data.client

    async def _async_update_data(self) -> dict[str, HoodDevice]:
        source = source_entry(self.hass, self.source_id)
        native = native_data(source) if source is not None else None
        if source is None or native is None:
            raise UpdateFailed("The native SmartThings account is not ready")
        client = native.client
        devices: dict[str, HoodDevice] = {}
        try:
            for device_id in self.device_ids:
                if device_id not in native.devices:
                    raise UpdateFailed(
                        "A selected device was removed; update the integration options"
                    )
                status = await client.get_device_status(device_id)
                health = await client.get_device_health(device_id)
                metadata = native.devices[device_id].device
                ocf = metadata.ocf
                devices[device_id] = HoodDevice(
                    deepcopy(status),
                    health.state == HealthStatus.ONLINE,
                    metadata.label or metadata.name or "Appliance",
                    ocf.manufacturer_name if ocf is not None else metadata.device_manufacturer_code,
                    self._model(status),
                )
        except SmartThingsError as err:
            raise UpdateFailed(
                "Unable to read the selected appliances through SmartThings"
            ) from err
        # A reload can complete while an old client's request is still running.
        if (
            source.state is not ConfigEntryState.LOADED
            or native_data(source) is not native
            or self._closed
        ):
            raise UpdateFailed("The native SmartThings connection changed")
        if self.client is not client:
            self._disconnect()
            self.client = client
            for device_id, device in devices.items():
                for component, capabilities in device.components.items():
                    for capability in capabilities:
                        self._subscriptions.append(
                            client.add_device_capability_event_listener(
                                device_id, component, capability, self._event
                            )
                        )
                self._subscriptions.append(
                    client.add_device_availability_event_listener(device_id, self._health)
                )
        return devices

    @callback
    def _event(self, event: DeviceEvent) -> None:
        if not self.source_available or event.device_id not in self.data:
            return
        device = self.data[event.device_id]
        component = device.components.get(event.component_id, {})
        if event.capability not in component:
            return
        previous = component[event.capability].get(event.attribute)
        component[event.capability][event.attribute] = Status(
            value=event.value, unit=previous.unit if previous else None, data=event.data
        )
        self.async_set_updated_data(self.data)

    @callback
    def _health(self, event: DeviceHealthEvent) -> None:
        if not self.source_available or event.device_id not in self.data:
            return
        self.data[event.device_id].online = event.status != HealthStatus.OFFLINE
        self.async_set_updated_data(self.data)

    @callback
    def source_changed(self) -> None:
        """Detach immediately on unload and recover with the replacement client."""
        if self._closed:
            return
        source = source_entry(self.hass, self.source_id)
        if source is None or native_data(source) is None:
            self._disconnect()
            self._cancel_retry()
            self.async_set_updated_data(self.data)
            return
        if not self.source_available:
            self._schedule_recovery()

    @callback
    def _schedule_recovery(self) -> None:
        if self._closed or (self._recover_task is not None and not self._recover_task.done()):
            return
        self._cancel_retry()
        self._recover_task = self.entry.async_create_background_task(
            self.hass, self._recover(), "smartthings_extended_reconnect"
        )

    async def _recover(self) -> None:
        await self.async_refresh()
        if not self.last_update_success and not self._closed:
            source = source_entry(self.hass, self.source_id)
            if source is not None and native_data(source) is not None:
                self._retry = async_call_later(self.hass, 30, self._retry_recovery)

    @callback
    def _retry_recovery(self, _now: Any) -> None:
        self._retry = None
        self._schedule_recovery()

    @callback
    def _cancel_retry(self) -> None:
        if self._retry is not None:
            self._retry()
            self._retry = None

    @callback
    def _disconnect(self) -> None:
        for unsubscribe in self._subscriptions:
            unsubscribe()
        self._subscriptions.clear()
        self.client = None

    @callback
    def close(self) -> None:
        self._closed = True
        self._cancel_retry()
        self._disconnect()

    async def command(
        self,
        device_id: str,
        capability: Capability,
        command: Command,
        argument: Any = None,
        *,
        component: str = HOOD,
    ) -> None:
        if not self.source_available or self.client is None:
            raise HomeAssistantError("The native SmartThings connection is unavailable")
        try:
            kwargs = {"argument": argument} if argument is not None else {}
            await self.client.execute_device_command(
                device_id, capability, command, component, **kwargs
            )
        except SmartThingsError as err:
            raise HomeAssistantError(
                "SmartThings could not complete the appliance command"
            ) from err

    def value(
        self, device_id: str, capability: Capability, attribute: Attribute, *, component: str = HOOD
    ) -> Any:
        status = (
            self.data[device_id].components.get(component, {}).get(capability, {}).get(attribute)
        )
        return status.value if status is not None else None
