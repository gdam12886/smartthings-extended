"""Profiles for user-facing cooktop and oven capabilities."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import EntityCategory
from pysmartthings import Attribute, Capability

from .coordinator import HoodCoordinator


@dataclass(frozen=True)
class SensorProfile:
    key: str
    name: str
    capability: Capability
    attribute: Attribute
    device_class: SensorDeviceClass | None = None
    state_class: SensorStateClass | None = None
    diagnostic: bool = False


SENSORS = (
    SensorProfile(
        "operating_state",
        "Operating state",
        Capability.CUSTOM_COOKTOP_OPERATING_STATE,
        Attribute.COOKTOP_OPERATING_STATE,
    ),
    SensorProfile("oven_mode", "Oven mode", Capability.OVEN_MODE, Attribute.OVEN_MODE),
    SensorProfile(
        "samsung_oven_mode",
        "Samsung oven mode",
        Capability.SAMSUNG_CE_OVEN_MODE,
        Attribute.OVEN_MODE,
    ),
    SensorProfile(
        "oven_machine_state",
        "Oven machine state",
        Capability.OVEN_OPERATING_STATE,
        Attribute.MACHINE_STATE,
    ),
    SensorProfile(
        "oven_job_state",
        "Oven job state",
        Capability.OVEN_OPERATING_STATE,
        Attribute.OVEN_JOB_STATE,
    ),
    SensorProfile(
        "oven_completion_time",
        "Oven completion time",
        Capability.OVEN_OPERATING_STATE,
        Attribute.COMPLETION_TIME,
        SensorDeviceClass.TIMESTAMP,
    ),
    SensorProfile(
        "oven_progress", "Oven progress", Capability.OVEN_OPERATING_STATE, Attribute.PROGRESS
    ),
    SensorProfile(
        "oven_operation_time",
        "Oven operation time",
        Capability.OVEN_OPERATING_STATE,
        Attribute.OPERATION_TIME,
    ),
    SensorProfile(
        "power",
        "Power",
        Capability.POWER_METER,
        Attribute.POWER,
        SensorDeviceClass.POWER,
        SensorStateClass.MEASUREMENT,
    ),
    SensorProfile(
        "energy",
        "Energy",
        Capability.ENERGY_METER,
        Attribute.ENERGY,
        SensorDeviceClass.ENERGY,
        SensorStateClass.TOTAL_INCREASING,
    ),
    SensorProfile(
        "software_versions",
        "Software versions",
        Capability.SAMSUNG_CE_SOFTWARE_VERSION,
        Attribute.VERSIONS,
        diagnostic=True,
    ),
    SensorProfile(
        "child_lock_state",
        "Child lock state",
        Capability.SAMSUNG_CE_KIDS_LOCK,
        Attribute.LOCK_STATE,
    ),
    SensorProfile(
        "software_update_state",
        "Software update state",
        Capability.SAMSUNG_CE_SOFTWARE_UPDATE,
        Attribute.OPERATING_STATE,
        diagnostic=True,
    ),
    SensorProfile(
        "software_update_progress",
        "Software update progress",
        Capability.SAMSUNG_CE_SOFTWARE_UPDATE,
        Attribute.PROGRESS,
        diagnostic=True,
    ),
    SensorProfile(
        "software_last_updated",
        "Software last updated",
        Capability.SAMSUNG_CE_SOFTWARE_UPDATE,
        Attribute.LAST_UPDATED_DATE,
        SensorDeviceClass.DATE,
        diagnostic=True,
    ),
    SensorProfile(
        "driver_version",
        "Driver version",
        Capability.SAMSUNG_CE_DRIVER_VERSION,
        Attribute.VERSION_NUMBER,
        diagnostic=True,
    ),
)


@dataclass(frozen=True)
class BinaryProfile:
    key: str
    name: str
    capability: Capability
    attribute: Attribute
    on_value: str | bool
    off_value: str | bool
    device_class: BinarySensorDeviceClass | None = None
    diagnostic: bool = False


BINARY_SENSORS = (
    BinaryProfile(
        "power_status",
        "Power status",
        Capability.SWITCH,
        Attribute.SWITCH,
        "on",
        "off",
        BinarySensorDeviceClass.POWER,
    ),
    BinaryProfile(
        "cooking",
        "Cooking",
        Capability.CUSTOM_COOKTOP_OPERATING_STATE,
        Attribute.COOKTOP_OPERATING_STATE,
        "run",
        "ready",
        BinarySensorDeviceClass.RUNNING,
    ),
    BinaryProfile(
        "child_lock",
        "Child lock",
        Capability.SAMSUNG_CE_KIDS_LOCK,
        Attribute.LOCK_STATE,
        "locked",
        "unlocked",
    ),
    BinaryProfile(
        "door",
        "Door",
        Capability.SAMSUNG_CE_DOOR_STATE,
        Attribute.DOOR_STATE,
        "open",
        "closed",
        BinarySensorDeviceClass.DOOR,
    ),
    BinaryProfile(
        "cavity_active",
        "Cavity active",
        Capability.CUSTOM_OVEN_CAVITY_STATUS,
        Attribute.OVEN_CAVITY_STATUS,
        "on",
        "off",
        BinarySensorDeviceClass.RUNNING,
    ),
    BinaryProfile(
        "software_update_available",
        "Software update available",
        Capability.SAMSUNG_CE_SOFTWARE_UPDATE,
        Attribute.NEW_VERSION_AVAILABLE,
        True,
        False,
        BinarySensorDeviceClass.UPDATE,
        diagnostic=True,
    ),
)


def enabled(
    coordinator: HoodCoordinator, device_id: str, component: str, capability: Capability
) -> bool:
    """Honor disabled appliance capabilities; hood exceptions stay in the hood profile."""
    status = coordinator.data[device_id].components.get(component, {})
    disabled = status.get(Capability.CUSTOM_DISABLED_CAPABILITIES, {}).get(
        Attribute.DISABLED_CAPABILITIES
    )
    disabled_values = disabled.value if disabled is not None else None
    return capability in status and not (
        isinstance(disabled_values, list) and capability in disabled_values
    )


def appliance_components(coordinator: HoodCoordinator) -> Iterator[tuple[str, str]]:
    for device_id, device in coordinator.data.items():
        for component in device.components:
            if component != "hood":
                yield device_id, component


def component_label(component: str) -> str:
    if component.startswith("cavity-") and component.split("-")[-1].isdigit():
        return f"Cavity {int(component.split('-')[-1])}"
    return component.replace("-", " ").replace("_", " ").capitalize()


def category(diagnostic: bool) -> EntityCategory | None:
    return EntityCategory.DIAGNOSTIC if diagnostic else None


def remote_control_permitted(coordinator: HoodCoordinator, device_id: str, component: str) -> bool:
    """Honor an appliance's reported remote-control restriction."""
    components = coordinator.data[device_id].components
    remote = components.get(component, {}).get(Capability.REMOTE_CONTROL_STATUS)
    if remote is None:
        remote = components.get("main", {}).get(Capability.REMOTE_CONTROL_STATUS)
    if remote is None:
        return True
    value = remote.get(Attribute.REMOTE_CONTROL_ENABLED)
    return value is not None and (
        value.value is True or isinstance(value.value, str) and value.value.lower() == "true"
    )


def cavity_active(coordinator: HoodCoordinator, device_id: str, component: str) -> bool:
    status = coordinator.data[device_id].components[component]
    cavity = status.get(Capability.CUSTOM_OVEN_CAVITY_STATUS, {}).get(Attribute.OVEN_CAVITY_STATUS)
    return cavity is None or cavity.value == "on"


def oven_modes(
    coordinator: HoodCoordinator, device_id: str, component: str, capability: Capability
) -> list[str]:
    """Use only usable mode names explicitly reported by the component."""
    values = coordinator.value(
        device_id, capability, Attribute.SUPPORTED_OVEN_MODES, component=component
    )
    return (
        list(dict.fromkeys(value for value in values if isinstance(value, str) and value))
        if isinstance(values, list)
        else []
    )


def can_start(coordinator: HoodCoordinator, device_id: str, component: str) -> bool:
    """Do not infer remote-start support from the global capability definition."""
    states = coordinator.value(
        device_id,
        Capability.OVEN_OPERATING_STATE,
        Attribute.SUPPORTED_MACHINE_STATES,
        component=component,
    )
    mode = coordinator.value(
        device_id, Capability.OVEN_MODE, Attribute.OVEN_MODE, component=component
    )
    return (
        enabled(coordinator, device_id, component, Capability.OVEN_OPERATING_STATE)
        and enabled(coordinator, device_id, component, Capability.OVEN_MODE)
        and isinstance(states, list)
        and "running" in states
        and mode in oven_modes(coordinator, device_id, component, Capability.OVEN_MODE)
        and cavity_active(coordinator, device_id, component)
        and remote_control_permitted(coordinator, device_id, component)
    )
