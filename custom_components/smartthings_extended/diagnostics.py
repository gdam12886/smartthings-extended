"""Provide bounded diagnostics without tokens or device identifiers."""

from homeassistant.core import HomeAssistant

from . import ExtendedConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ExtendedConfigEntry
) -> dict:
    runtime = entry.runtime_data
    return {
        "features": runtime.features,
        "timer_max_minutes": runtime.timer_max,
        "native_connection_available": runtime.coordinator.source_available,
        "devices": [
            {
                "online": device.online,
                "capabilities": [str(capability) for capability in device.status],
            }
            for device in runtime.coordinator.data.values()
        ],
    }
