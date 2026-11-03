"""A native account with realistic raw and filtered cooktop status."""

import json
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, create_autospec

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pysmartthings import (
    Attribute,
    Capability,
    Component,
    DeviceEvent,
    DeviceResponse,
    DeviceStatus,
    SmartThings,
)
from pysmartthings.models import HealthStatus
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smartthings_extended.const import (
    CONF_DEVICES,
    CONF_FEATURES,
    CONF_SOURCE,
    CONF_TIMER_MAX,
    DOMAIN,
    FEATURES,
)

DEVICE_ID = "5c202ad1-d112-d746-50b8-bd76a554b362"
OVEN_ID = "00000000-0000-4000-8000-000000000002"
FIXTURES = Path(__file__).parent / "fixtures"


@dataclass
class FakeAccount:
    entry: MockConfigEntry
    client: AsyncMock
    raw: dict
    listeners: list
    health_listeners: list

    def push(
        self,
        capability: Capability,
        attribute: Attribute,
        value,
        component: str = "hood",
        device_id: str = DEVICE_ID,
    ) -> None:
        event = DeviceEvent(
            "event", "location", "owner", device_id, component, capability, attribute, value
        )
        for watched_device, watched_component, watched_capability, callback in list(self.listeners):
            if (
                watched_device == device_id
                and watched_component == component
                and watched_capability == capability
            ):
                callback(event)


def mock_client(raw: dict) -> tuple[AsyncMock, list, list]:
    client = create_autospec(SmartThings, instance=True)
    client.get_device_status.side_effect = lambda device_id: deepcopy(raw)
    client.get_device_health.return_value = SimpleNamespace(state=HealthStatus.ONLINE)
    listeners: list = []
    health: list = []

    def add_listener(device_id, component, capability, callback) -> Callable:
        listener = (device_id, component, capability, callback)
        listeners.append(listener)
        return lambda: listeners.remove(listener)

    def add_health(device_id, callback) -> Callable:
        listener = (device_id, callback)
        health.append(listener)
        return lambda: health.remove(listener)

    client.add_device_capability_event_listener.side_effect = add_listener
    client.add_device_availability_event_listener.side_effect = add_health
    return client, listeners, health


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations) -> None:
    """Allow the local custom integration in the test Home Assistant instance."""


@pytest.fixture
def account(hass: HomeAssistant) -> FakeAccount:
    device_data = json.loads((FIXTURES / "cooktop_device.json").read_text())
    device_data["items"][0]["label"] = "Cooktop"
    device = DeviceResponse.from_json(json.dumps(device_data)).items[0]
    raw = DeviceStatus.from_json((FIXTURES / "cooktop_status.json").read_text()).components
    hood = raw["hood"]
    hood[Capability.SAMSUNG_CE_CONNECTION_STATE][Attribute.CONNECTION_STATE].value = "connected"
    hood[Capability.SAMSUNG_CE_HOOD_FAN_SPEED][Attribute.HOOD_FAN_SPEED].value = 1
    hood[Capability.SAMSUNG_CE_LAMP][Attribute.BRIGHTNESS_LEVEL].value = "high"
    hood[Capability.SWITCH][Attribute.SWITCH].value = "off"
    timer = hood[Capability.SAMSUNG_CE_COUNT_DOWN_TIMER]
    timer[Attribute.START_VALUE].value = 10
    timer[Attribute.START_VALUE].unit = "min"
    timer[Attribute.CURRENT_VALUE].value = 0
    timer[Attribute.CURRENT_VALUE].unit = "min"
    timer[Attribute.STATUS].value = "idle"
    client, listeners, health = mock_client(raw)
    filtered = deepcopy(raw)
    del filtered["hood"][Capability.SAMSUNG_CE_LAMP]
    del filtered["hood"][Capability.SAMSUNG_CE_HOOD_FAN_SPEED]
    entry = MockConfigEntry(
        domain="smartthings", title="Home", data={}, state=ConfigEntryState.LOADED
    )
    entry.runtime_data = SimpleNamespace(
        client=client,
        devices={DEVICE_ID: SimpleNamespace(device=device, status=filtered, online=True)},
    )
    entry.add_to_hass(hass)
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("smartthings", DEVICE_ID)},
        name="Cooktop",
        manufacturer="Samsung",
    )
    return FakeAccount(entry, client, raw, listeners, health)


@pytest.fixture
def extended_entry(account: FakeAccount, hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="SmartThings Extended (Home)",
        unique_id=account.entry.entry_id,
        data={
            CONF_SOURCE: account.entry.entry_id,
            CONF_DEVICES: [DEVICE_ID],
            CONF_FEATURES: list(FEATURES),
            CONF_TIMER_MAX: 60,
        },
        version=1,
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def oven_status() -> dict:
    """Synthetic three-component oven with unreported mode/start support."""
    cavity = {
        "ovenMode": {"ovenMode": {"value": "Others"}, "supportedOvenModes": {"value": None}},
        "samsungce.ovenMode": {
            "ovenMode": {"value": "NoOperation"},
            "supportedOvenModes": {"value": None},
        },
        "ovenOperatingState": {
            "machineState": {"value": "ready"},
            "ovenJobState": {"value": "ready"},
            "completionTime": {"value": "2026-01-01T12:00:00Z"},
            "progress": {"value": 1, "unit": "%"},
            "operationTime": {"value": 0},
            "supportedMachineStates": {"value": None},
        },
        "custom.disabledCapabilities": {"disabledCapabilities": {"value": []}},
    }
    components = {name: deepcopy(cavity) for name in ("main", "cavity-02", "cavity-03")}
    for name in ("main", "cavity-02"):
        components[name]["samsungce.doorState"] = {"doorState": {"value": "closed"}}
    components["cavity-03"]["custom.ovenCavityStatus"] = {"ovenCavityStatus": {"value": "off"}}
    components["main"].update(
        {
            "refresh": {},
            "samsungce.kidsLock": {"lockState": {"value": "unlocked"}},
            "samsungce.kitchenDeviceIdentification": {"modelCode": {"value": "Test oven"}},
            "samsungce.softwareUpdate": {
                "newVersionAvailable": {"value": False},
                "operatingState": {"value": None},
                "progress": {"value": None},
            },
        }
    )
    return DeviceStatus.from_dict({"components": components}).components


@pytest.fixture
def appliance_account(account: FakeAccount, oven_status: dict) -> FakeAccount:
    """Add an oven to the same native session without another cloud connection."""
    device = replace(
        account.entry.runtime_data.devices[DEVICE_ID].device,
        device_id=OVEN_ID,
        label="Oven",
        name="Oven",
        components={
            name: Component(name, list(status), "Oven") for name, status in oven_status.items()
        },
    )
    account.entry.runtime_data.devices[OVEN_ID] = SimpleNamespace(
        device=device, status=deepcopy(oven_status), online=True
    )
    account.raw["main"][Capability.SAMSUNG_CE_KIDS_LOCK][Attribute.LOCK_STATE].value = None
    snapshots = {DEVICE_ID: account.raw, OVEN_ID: oven_status}
    account.client.get_device_status.side_effect = lambda device_id: deepcopy(snapshots[device_id])
    return account


@pytest.fixture
def appliance_entry(
    hass: HomeAssistant, appliance_account: FakeAccount, extended_entry: MockConfigEntry
) -> MockConfigEntry:
    hass.config_entries.async_update_entry(
        extended_entry,
        data={**extended_entry.data, CONF_DEVICES: [DEVICE_ID, OVEN_ID]},
    )
    return extended_entry
