"""Cooktop and multi-cavity oven behavior through real HA entity platforms."""

from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import call

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pysmartthings import Attribute, Capability, Command, Status
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smartthings_extended.const import CONF_DEVICES, CONF_FEATURES, CONF_TIMER_MAX
from custom_components.smartthings_extended.native import supported_devices

from .conftest import DEVICE_ID, OVEN_ID, FakeAccount, mock_client
from .test_integration import FAN, setup

POWER = "switch.cooktop_power"
OVEN_STOP = "button.oven_stop_oven"
CAVITY_STOP = "button.oven_cavity_2_stop_oven"
INACTIVE_STOP = "button.oven_cavity_3_stop_oven"
MODE = "select.oven_oven_mode_control"
SAMSUNG_MODE = "select.oven_samsung_oven_mode_control"
OVEN_START = "button.oven_start_oven"


def oven_push(account: FakeAccount, capability, attribute, value, component="main") -> None:
    account.push(capability, attribute, value, component, device_id=OVEN_ID)


async def test_appliance_discovery(appliance_account: FakeAccount) -> None:
    assert supported_devices(appliance_account.entry) == {DEVICE_ID: "Cooktop", OVEN_ID: "Oven"}
    # Advertising oven capabilities is sufficient even if native status is filtered.
    full = appliance_account.entry.runtime_data.devices[OVEN_ID]
    full.status = {}
    assert OVEN_ID in supported_devices(appliance_account.entry)
    unsupported = replace(full.device, device_id="other", components={})
    appliance_account.entry.runtime_data.devices["other"] = SimpleNamespace(
        device=unsupported, status={}
    )
    assert "other" not in supported_devices(appliance_account.entry)


async def test_cooktop_features(
    hass: HomeAssistant, appliance_account: FakeAccount, appliance_entry: MockConfigEntry
) -> None:
    await setup(hass, appliance_entry)
    assert hass.states.get(POWER).state == "off"
    assert hass.states.get("sensor.cooktop_operating_state").state == "ready"
    assert hass.states.get("binary_sensor.cooktop_cooking").state == "off"
    assert hass.states.get("binary_sensor.cooktop_child_lock").state == "unknown"
    assert hass.states.get("sensor.cooktop_child_lock_state").state == "unknown"
    assert hass.states.get("lock.cooktop_child_lock_control") is None
    assert hass.states.get("sensor.cooktop_power") is None
    assert hass.states.get("sensor.cooktop_energy") is None
    assert hass.states.get("sensor.cooktop_software_versions").attributes["versions"]
    assert hass.states.get("binary_sensor.cooktop_software_update_available").state == "off"
    assert hass.states.get("sensor.cooktop_software_update_progress").state == "unknown"
    registry = dr.async_get(hass)
    device = registry.async_get_device_by_identifier(
        ("smartthings_extended", DEVICE_ID), appliance_entry.entry_id
    )
    assert device.model == "NV9300K-/AA3"
    assert appliance_account.client.get_device_status.call_args_list == [
        call(DEVICE_ID),
        call(OVEN_ID),
    ]
    appliance_account.client.create_subscription.assert_not_called()


async def test_power_routes_to_main(
    hass: HomeAssistant, appliance_account: FakeAccount, appliance_entry: MockConfigEntry
) -> None:
    await setup(hass, appliance_entry)
    for service, command in (("turn_on", Command.ON), ("turn_off", Command.OFF)):
        await hass.services.async_call("switch", service, {ATTR_ENTITY_ID: POWER}, blocking=True)
        assert appliance_account.client.execute_device_command.call_args == call(
            DEVICE_ID, Capability.SWITCH, command, "main"
        )
    appliance_account.push(Capability.SWITCH, Attribute.SWITCH, "on", "main")
    assert hass.states.get(POWER).state == "on"
    assert hass.states.get(FAN).state == "off"
    appliance_account.push(
        Capability.CUSTOM_COOKTOP_OPERATING_STATE, Attribute.COOKTOP_OPERATING_STATE, "run", "main"
    )
    assert hass.states.get("binary_sensor.cooktop_cooking").state == "on"
    appliance_account.push(
        Capability.SAMSUNG_CE_CONNECTION_STATE, Attribute.CONNECTION_STATE, "disconnected"
    )
    assert hass.states.get(FAN).state == "unavailable"
    assert hass.states.get(POWER).state == "on"


async def test_oven_components(
    hass: HomeAssistant, appliance_account: FakeAccount, appliance_entry: MockConfigEntry
) -> None:
    await setup(hass, appliance_entry)
    for prefix in ("oven", "oven_cavity_2", "oven_cavity_3"):
        assert hass.states.get(f"sensor.{prefix}_oven_machine_state").state == "ready"
        progress = hass.states.get(f"sensor.{prefix}_oven_progress")
        assert progress.state == "1"
        assert progress.attributes["unit_of_measurement"] == "%"
        operation_time = hass.states.get(f"sensor.{prefix}_oven_operation_time")
        assert operation_time.state == "0"
        assert "unit_of_measurement" not in operation_time.attributes
        assert (
            hass.states.get(f"sensor.{prefix}_oven_completion_time").state
            == "2026-01-01T12:00:00+00:00"
        )
    assert hass.states.get("sensor.oven_oven_mode").state == "Others"
    assert hass.states.get("sensor.oven_samsung_oven_mode").state == "NoOperation"
    assert hass.states.get("binary_sensor.oven_door").state == "off"
    assert hass.states.get(INACTIVE_STOP).state == "unavailable"
    assert not hass.states.async_entity_ids("select")
    assert hass.states.get(OVEN_START) is None
    assert not hass.states.async_entity_ids("climate")
    oven_device = dr.async_get(hass).async_get_device_by_identifier(
        ("smartthings_extended", OVEN_ID), appliance_entry.entry_id
    )
    assert oven_device.model == "Test oven"


async def test_cavity_updates_are_isolated(
    hass: HomeAssistant, appliance_account: FakeAccount, appliance_entry: MockConfigEntry
) -> None:
    await setup(hass, appliance_entry)
    oven_push(
        appliance_account,
        Capability.OVEN_OPERATING_STATE,
        Attribute.MACHINE_STATE,
        "running",
        "cavity-02",
    )
    oven_push(
        appliance_account,
        Capability.SAMSUNG_CE_DOOR_STATE,
        Attribute.DOOR_STATE,
        "open",
        "cavity-02",
    )
    assert hass.states.get("sensor.oven_cavity_2_oven_machine_state").state == "running"
    assert hass.states.get("sensor.oven_oven_machine_state").state == "ready"
    assert hass.states.get("sensor.oven_cavity_3_oven_machine_state").state == "ready"
    assert hass.states.get("binary_sensor.oven_cavity_2_door").state == "on"
    assert hass.states.get("binary_sensor.oven_door").state == "off"


@pytest.mark.parametrize(
    ("entity_id", "component"), [(OVEN_STOP, "main"), (CAVITY_STOP, "cavity-02")]
)
async def test_oven_stop_routing(
    hass: HomeAssistant,
    appliance_account: FakeAccount,
    appliance_entry: MockConfigEntry,
    entity_id,
    component,
) -> None:
    await setup(hass, appliance_entry)
    await hass.services.async_call("button", "press", {ATTR_ENTITY_ID: entity_id}, blocking=True)
    appliance_account.client.execute_device_command.assert_awaited_once_with(
        OVEN_ID, Capability.OVEN_OPERATING_STATE, Command.STOP, component
    )


async def test_inactive_cavity_control(
    hass: HomeAssistant, appliance_account: FakeAccount, appliance_entry: MockConfigEntry
) -> None:
    await setup(hass, appliance_entry)
    await hass.services.async_call(
        "button", "press", {ATTR_ENTITY_ID: INACTIVE_STOP}, blocking=True
    )
    appliance_account.client.execute_device_command.assert_not_called()
    oven_push(
        appliance_account,
        Capability.CUSTOM_OVEN_CAVITY_STATUS,
        Attribute.OVEN_CAVITY_STATUS,
        "on",
        "cavity-03",
    )
    assert hass.states.get(INACTIVE_STOP).state != "unavailable"
    await hass.services.async_call(
        "button", "press", {ATTR_ENTITY_ID: INACTIVE_STOP}, blocking=True
    )
    appliance_account.client.execute_device_command.assert_awaited_once_with(
        OVEN_ID, Capability.OVEN_OPERATING_STATE, Command.STOP, "cavity-03"
    )


async def test_reported_modes_and_start_appear_dynamically(
    hass: HomeAssistant, appliance_account: FakeAccount, appliance_entry: MockConfigEntry
) -> None:
    await setup(hass, appliance_entry)
    oven_push(
        appliance_account, Capability.OVEN_MODE, Attribute.SUPPORTED_OVEN_MODES, ["Bake", "Broil"]
    )
    oven_push(
        appliance_account,
        Capability.SAMSUNG_CE_OVEN_MODE,
        Attribute.SUPPORTED_OVEN_MODES,
        ["AirFry", "Bake"],
    )
    oven_push(
        appliance_account,
        Capability.OVEN_OPERATING_STATE,
        Attribute.SUPPORTED_MACHINE_STATES,
        ["ready", "running"],
    )
    await hass.async_block_till_done()
    assert hass.states.get(MODE).attributes["options"] == ["Bake", "Broil"]
    assert hass.states.get(SAMSUNG_MODE).attributes["options"] == ["AirFry", "Bake"]
    assert hass.states.get(OVEN_START) is None  # Current "Others" is not a reported supported mode.
    oven_push(appliance_account, Capability.OVEN_MODE, Attribute.OVEN_MODE, "Bake")
    await hass.async_block_till_done()
    assert hass.states.get(OVEN_START) is not None
    await hass.services.async_call(
        "select", "select_option", {ATTR_ENTITY_ID: MODE, "option": "Broil"}, blocking=True
    )
    assert appliance_account.client.execute_device_command.call_args == call(
        OVEN_ID, Capability.OVEN_MODE, Command.SET_OVEN_MODE, "main", argument="Broil"
    )
    await hass.services.async_call(
        "select", "select_option", {ATTR_ENTITY_ID: SAMSUNG_MODE, "option": "AirFry"}, blocking=True
    )
    assert appliance_account.client.execute_device_command.call_args == call(
        OVEN_ID, Capability.SAMSUNG_CE_OVEN_MODE, Command.SET_OVEN_MODE, "main", argument="AirFry"
    )
    await hass.services.async_call("button", "press", {ATTR_ENTITY_ID: OVEN_START}, blocking=True)
    assert appliance_account.client.execute_device_command.call_args == call(
        OVEN_ID, Capability.OVEN_OPERATING_STATE, Command.START, "main", argument=["Bake"]
    )
    count = appliance_account.client.execute_device_command.await_count
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "select",
            "select_option",
            {ATTR_ENTITY_ID: MODE, "option": "ConvectionBake"},
            blocking=True,
        )
    assert appliance_account.client.execute_device_command.await_count == count
    oven_push(appliance_account, Capability.OVEN_MODE, Attribute.SUPPORTED_OVEN_MODES, None)
    assert hass.states.get(MODE).state == "unavailable"
    assert hass.states.get(OVEN_START).state == "unavailable"


async def test_remote_control_restriction(
    hass: HomeAssistant,
    appliance_account: FakeAccount,
    appliance_entry: MockConfigEntry,
    oven_status: dict,
) -> None:
    remote = {Attribute.REMOTE_CONTROL_ENABLED: Status(value="true")}
    oven_status["main"][Capability.REMOTE_CONTROL_STATUS] = remote
    oven_status["main"][Capability.OVEN_MODE][Attribute.SUPPORTED_OVEN_MODES].value = ["Bake"]
    oven_status["main"][Capability.OVEN_MODE][Attribute.OVEN_MODE].value = "Bake"
    oven_status["main"][Capability.OVEN_OPERATING_STATE][
        Attribute.SUPPORTED_MACHINE_STATES
    ].value = ["running"]
    appliance_account.raw["main"][Capability.REMOTE_CONTROL_STATUS] = deepcopy(remote)
    await setup(hass, appliance_entry)
    oven_push(
        appliance_account,
        Capability.REMOTE_CONTROL_STATUS,
        Attribute.REMOTE_CONTROL_ENABLED,
        "false",
    )
    appliance_account.push(
        Capability.REMOTE_CONTROL_STATUS, Attribute.REMOTE_CONTROL_ENABLED, "false", "main"
    )
    assert hass.states.get(MODE).state == "unavailable"
    assert hass.states.get(OVEN_START).state == "unavailable"
    with pytest.raises(ServiceValidationError, match="Remote control is disabled"):
        await hass.services.async_call("switch", "turn_on", {ATTR_ENTITY_ID: POWER}, blocking=True)
    await hass.services.async_call("switch", "turn_off", {ATTR_ENTITY_ID: POWER}, blocking=True)
    await hass.services.async_call("button", "press", {ATTR_ENTITY_ID: OVEN_STOP}, blocking=True)
    assert appliance_account.client.execute_device_command.await_count == 2


async def test_disabled_capability_update(
    hass: HomeAssistant, appliance_account: FakeAccount, appliance_entry: MockConfigEntry
) -> None:
    await setup(hass, appliance_entry)
    appliance_account.push(
        Capability.CUSTOM_DISABLED_CAPABILITIES, Attribute.DISABLED_CAPABILITIES, ["switch"], "main"
    )
    assert hass.states.get(POWER).state == "unavailable"
    assert hass.states.get("binary_sensor.cooktop_power_status").state == "unavailable"
    assert hass.states.get("sensor.cooktop_operating_state").state == "ready"


async def test_enabled_child_lock_control(
    hass: HomeAssistant, appliance_account: FakeAccount, appliance_entry: MockConfigEntry
) -> None:
    appliance_account.raw["main"][Capability.CUSTOM_DISABLED_CAPABILITIES][
        Attribute.DISABLED_CAPABILITIES
    ].value = []
    await setup(hass, appliance_entry)
    lock = "lock.cooktop_child_lock_control"
    assert hass.states.get(lock).state == "unlocked"
    for service, command in (("lock", Command.LOCK), ("unlock", Command.UNLOCK)):
        await hass.services.async_call("lock", service, {ATTR_ENTITY_ID: lock}, blocking=True)
        assert appliance_account.client.execute_device_command.call_args == call(
            DEVICE_ID, Capability.SAMSUNG_CE_KIDS_LOCK_CONTROL, command, "main"
        )
    appliance_account.push(
        Capability.SAMSUNG_CE_KIDS_LOCK_CONTROL, Attribute.LOCK_STATE, "locked", "main"
    )
    assert hass.states.get(lock).state == "locked"


async def test_meters_only_when_reported(
    hass: HomeAssistant, appliance_account: FakeAccount, appliance_entry: MockConfigEntry
) -> None:
    main = appliance_account.raw["main"]
    main[Capability.POWER_METER] = {Attribute.POWER: Status(value=120, unit="W")}
    main[Capability.ENERGY_METER] = {Attribute.ENERGY: Status(value=5.2, unit="kWh")}
    await setup(hass, appliance_entry)
    assert hass.states.get("sensor.cooktop_power").state == "120"
    assert hass.states.get("sensor.cooktop_power").attributes["unit_of_measurement"] == "W"
    assert hass.states.get("sensor.cooktop_energy").state == "5.2"
    appliance_account.push(Capability.ENERGY_METER, Attribute.ENERGY, None, "main")
    assert hass.states.get("sensor.cooktop_energy").state == "unknown"


@pytest.mark.parametrize("value", [None, "invalid date", "2026-01-01T12:00:00"])
async def test_invalid_completion_time(
    hass: HomeAssistant, appliance_account: FakeAccount, appliance_entry: MockConfigEntry, value
) -> None:
    await setup(hass, appliance_entry)
    oven_push(appliance_account, Capability.OVEN_OPERATING_STATE, Attribute.COMPLETION_TIME, value)
    assert hass.states.get("sensor.oven_oven_completion_time").state == "unknown"


@pytest.mark.parametrize("value", [None, [None, 7, ""]])
async def test_unusable_support_data_has_no_start_or_mode_control(
    hass: HomeAssistant,
    appliance_account: FakeAccount,
    appliance_entry: MockConfigEntry,
    oven_status: dict,
    value,
) -> None:
    oven_status["main"][Capability.OVEN_MODE][Attribute.SUPPORTED_OVEN_MODES].value = value
    oven_status["main"][Capability.OVEN_MODE][Attribute.OVEN_MODE].value = None
    oven_status["main"][Capability.OVEN_OPERATING_STATE][
        Attribute.SUPPORTED_MACHINE_STATES
    ].value = ["running"]
    await setup(hass, appliance_entry)
    assert hass.states.get(MODE) is None
    assert hass.states.get(OVEN_START) is None


@pytest.mark.parametrize("disabled", ["ovenMode", "ovenOperatingState"])
async def test_disabled_capability_blocks_start_discovery(
    hass: HomeAssistant,
    appliance_account: FakeAccount,
    appliance_entry: MockConfigEntry,
    oven_status: dict,
    disabled,
) -> None:
    main = oven_status["main"]
    main[Capability.OVEN_MODE][Attribute.SUPPORTED_OVEN_MODES].value = ["Bake"]
    main[Capability.OVEN_MODE][Attribute.OVEN_MODE].value = "Bake"
    main[Capability.OVEN_OPERATING_STATE][Attribute.SUPPORTED_MACHINE_STATES].value = ["running"]
    main[Capability.CUSTOM_DISABLED_CAPABILITIES][Attribute.DISABLED_CAPABILITIES].value = [
        disabled
    ]
    await setup(hass, appliance_entry)
    assert hass.states.get(OVEN_START) is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [(True, "on"), ("True", "on"), (False, "off"), ("false", "off"), (None, "unknown")],
)
async def test_software_update_boolean_values(
    hass: HomeAssistant,
    appliance_account: FakeAccount,
    appliance_entry: MockConfigEntry,
    value,
    expected,
) -> None:
    await setup(hass, appliance_entry)
    appliance_account.push(
        Capability.SAMSUNG_CE_SOFTWARE_UPDATE, Attribute.NEW_VERSION_AVAILABLE, value, "main"
    )
    assert hass.states.get("binary_sensor.cooktop_software_update_available").state == expected


@pytest.mark.parametrize(
    ("value", "expected"), [("2026-01-02", "2026-01-02"), (None, "unknown"), ("invalid", "unknown")]
)
async def test_software_last_update_date(
    hass: HomeAssistant,
    appliance_account: FakeAccount,
    appliance_entry: MockConfigEntry,
    value,
    expected,
) -> None:
    await setup(hass, appliance_entry)
    appliance_account.push(
        Capability.SAMSUNG_CE_SOFTWARE_UPDATE, Attribute.LAST_UPDATED_DATE, value, "main"
    )
    assert hass.states.get("sensor.cooktop_software_last_updated").state == expected


async def test_refresh_command(
    hass: HomeAssistant, appliance_account: FakeAccount, appliance_entry: MockConfigEntry
) -> None:
    await setup(hass, appliance_entry)
    appliance_account.raw["main"][Capability.SWITCH][Attribute.SWITCH].value = "on"
    await hass.services.async_call(
        "button", "press", {ATTR_ENTITY_ID: "button.cooktop_refresh_status"}, blocking=True
    )
    appliance_account.client.execute_device_command.assert_awaited_once_with(
        DEVICE_ID, Capability.REFRESH, Command.REFRESH, "main"
    )
    assert appliance_account.client.get_device_status.await_count == 4
    assert hass.states.get(POWER).state == "on"


async def test_options_select_both_then_remove_oven(
    hass: HomeAssistant, appliance_account: FakeAccount, extended_entry: MockConfigEntry
) -> None:
    await setup(hass, extended_entry)
    settings = {
        CONF_DEVICES: [DEVICE_ID, OVEN_ID],
        CONF_FEATURES: ["appliance", "fan"],
        CONF_TIMER_MAX: 60,
    }
    result = await hass.config_entries.options.async_init(extended_entry.entry_id)
    await hass.config_entries.options.async_configure(result["flow_id"], settings)
    await hass.async_block_till_done()
    assert hass.states.get(OVEN_STOP) is not None
    assert hass.states.get(POWER) is not None
    result = await hass.config_entries.options.async_init(extended_entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"], {**settings, CONF_DEVICES: [DEVICE_ID]}
    )
    await hass.async_block_till_done()
    assert er.async_get(hass).async_get(OVEN_STOP) is None
    assert er.async_get(hass).async_get(POWER) is not None
    assert OVEN_ID in appliance_account.entry.runtime_data.devices


async def test_native_reconnect_all_components(
    hass: HomeAssistant,
    appliance_account: FakeAccount,
    appliance_entry: MockConfigEntry,
    oven_status: dict,
) -> None:
    await setup(hass, appliance_entry)
    before = set(hass.states.async_entity_ids())
    count = len(appliance_account.listeners)
    appliance_account.entry._async_set_state(hass, ConfigEntryState.UNLOAD_IN_PROGRESS, None)
    assert hass.states.get(OVEN_STOP).state == "unavailable"
    assert not appliance_account.listeners
    client, listeners, health = mock_client(appliance_account.raw)
    client.get_device_status.side_effect = lambda device_id: deepcopy(
        oven_status if device_id == OVEN_ID else appliance_account.raw
    )
    appliance_account.entry.runtime_data = SimpleNamespace(
        client=client, devices=appliance_account.entry.runtime_data.devices
    )
    appliance_account.entry._async_set_state(hass, ConfigEntryState.LOADED, None)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(listeners) == count
    assert len(health) == 2
    assert set(hass.states.async_entity_ids()) == before
    assert hass.states.get(CAVITY_STOP).state != "unavailable"
    await hass.services.async_call("button", "press", {ATTR_ENTITY_ID: CAVITY_STOP}, blocking=True)
    client.execute_device_command.assert_awaited_once_with(
        OVEN_ID, Capability.OVEN_OPERATING_STATE, Command.STOP, "cavity-02"
    )
    assert await hass.config_entries.async_unload(appliance_entry.entry_id)
    assert not listeners
    assert not health
