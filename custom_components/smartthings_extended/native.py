"""Isolate the native integration interface used by the extension."""

from __future__ import annotations

from typing import Any, Protocol, cast

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from pysmartthings import Device, SmartThings

from .const import HOOD, NATIVE_DOMAIN


class NativeDevice(Protocol):
    """The native device fields consumed by the extension."""

    device: Device
    status: dict[str, Any]
    online: bool


class NativeData(Protocol):
    """The native runtime fields consumed by the extension."""

    client: SmartThings
    devices: dict[str, NativeDevice]


def source_entry(hass: HomeAssistant, entry_id: str) -> ConfigEntry | None:
    """Find the selected native SmartThings account."""
    entry = hass.config_entries.async_get_entry(entry_id)
    return entry if entry is not None and entry.domain == NATIVE_DOMAIN else None


def native_data(entry: ConfigEntry) -> NativeData | None:
    """Return a compatible, loaded native runtime without copying credentials."""
    if entry.state is not ConfigEntryState.LOADED:
        return None
    data = getattr(entry, "runtime_data", None)
    if (
        data is None
        or not hasattr(data, "client")
        or not isinstance(getattr(data, "devices", None), dict)
    ):
        return None
    return cast(NativeData, data)


def supported_devices(entry: ConfigEntry) -> dict[str, str]:
    """Offer cooktops, ovens, ranges, and devices with a hood component."""
    if (data := native_data(entry)) is None:
        return {}
    return {
        device_id: full.device.label or full.device.name or device_id
        for device_id, full in data.devices.items()
        if HOOD in full.device.components
        or HOOD in full.status
        or any(
            capability in full.status.get("main", {})
            for capability in (
                "custom.cooktopOperatingState",
                "ovenMode",
                "ovenOperatingState",
                "samsungce.ovenMode",
            )
        )
        or any(
            str(capability)
            in (
                "custom.cooktopOperatingState",
                "ovenMode",
                "ovenOperatingState",
                "samsungce.ovenMode",
            )
            for component in full.device.components.values()
            for capability in component.capabilities
        )
    }
