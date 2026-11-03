"""Extend appliances through the native SmartThings connection."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_DEVICES,
    CONF_FEATURES,
    CONF_SOURCE,
    CONF_TIMER_MAX,
    DEFAULT_TIMER_MAX,
    ENTITY_KEYS,
    FEATURES,
)
from .coordinator import HoodCoordinator
from .native import native_data, source_entry

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.LIGHT,
    Platform.FAN,
    Platform.NUMBER,
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.SELECT,
    Platform.LOCK,
]


@dataclass
class RuntimeData:
    coordinator: HoodCoordinator
    features: list[str]
    timer_max: int


type ExtendedConfigEntry = ConfigEntry[RuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: ExtendedConfigEntry) -> bool:
    source_id = entry.data[CONF_SOURCE]
    if (source := source_entry(hass, source_id)) is None:
        raise ConfigEntryError("The selected native SmartThings account no longer exists")
    if native_data(source) is None:
        raise ConfigEntryNotReady("The native SmartThings account is not ready")
    settings = {**entry.data, **entry.options}
    coordinator = HoodCoordinator(hass, entry, source_id, settings[CONF_DEVICES])
    entry.async_on_unload(coordinator.close)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = RuntimeData(
        coordinator,
        settings.get(CONF_FEATURES, list(FEATURES)),
        settings.get(CONF_TIMER_MAX, DEFAULT_TIMER_MAX),
    )
    # Only remove this extension's entities explicitly deselected in its options.
    keys = {"connection"} | {
        key for feature in entry.runtime_data.features for key in ENTITY_KEYS.get(feature, ())
    }
    active = {f"{device_id}_hood_{key}" for device_id in settings[CONF_DEVICES] for key in keys}
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        appliance_selected = "appliance" in entry.runtime_data.features and any(
            entity.unique_id.startswith(f"{device_id}_")
            and not entity.unique_id.startswith(f"{device_id}_hood_")
            for device_id in settings[CONF_DEVICES]
        )
        if entity.unique_id not in active and not appliance_selected:
            registry.async_remove(entity.entity_id)
    entry.async_on_unload(source.async_on_state_change(coordinator.source_changed))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ExtendedConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
