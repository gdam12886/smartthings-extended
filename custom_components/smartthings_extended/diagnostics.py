"""Report capability coverage without device names, IDs, or account credentials."""

from homeassistant.core import HomeAssistant
from pysmartthings import Attribute, Capability

from . import ExtendedConfigEntry
from .appliances import can_start


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
                "components": {
                    component: {
                        "capabilities": [str(capability) for capability in status],
                        "disabled_capabilities": disabled.value
                        if (
                            disabled := status.get(Capability.CUSTOM_DISABLED_CAPABILITIES, {}).get(
                                Attribute.DISABLED_CAPABILITIES
                            )
                        )
                        else [],
                        "reported_oven_modes": bool(
                            status.get(Capability.OVEN_MODE, {}).get(Attribute.SUPPORTED_OVEN_MODES)
                            and status[Capability.OVEN_MODE][Attribute.SUPPORTED_OVEN_MODES].value
                        ),
                        "remote_start_ready": can_start(runtime.coordinator, device_id, component)
                        if Capability.OVEN_OPERATING_STATE in status
                        else False,
                    }
                    for component, status in device.components.items()
                },
            }
            for device_id, device in runtime.coordinator.data.items()
        ],
    }
