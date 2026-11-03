"""Exercise real Home Assistant setup, commands, push events, and lifecycle."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import call

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pysmartthings import (
    Attribute,
    Capability,
    Command,
    DeviceHealthEvent,
    SmartThingsConnectionError,
)
from pysmartthings.models import HealthStatus
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smartthings_extended.const import CONF_FEATURES

from .conftest import DEVICE_ID, FakeAccount, mock_client

FAN = "fan.cooktop_hood_fan"
LIGHT = "light.cooktop_hood_light"
DURATION = "number.cooktop_hood_timer_duration"
REMAINING = "sensor.cooktop_hood_timer_remaining"
STATUS = "sensor.cooktop_hood_timer_status"
START = "button.cooktop_start_hood_timer"
CANCEL = "button.cooktop_cancel_hood_timer"
CONNECTION = "binary_sensor.cooktop_hood_connection"


async def setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED


async def test_setup(
    hass: HomeAssistant, account: FakeAccount, extended_entry: MockConfigEntry
) -> None:
    filtered = deepcopy(account.entry.runtime_data.devices[DEVICE_ID].status)
    await setup(hass, extended_entry)
    for entity_id in (FAN, LIGHT, DURATION, REMAINING, STATUS, START, CANCEL, CONNECTION):
        assert hass.states.get(entity_id) is not None
        assert er.async_get(hass).async_get(entity_id).platform == "smartthings_extended"
    account.client.get_device_status.assert_awaited_once_with(DEVICE_ID)
    account.client.create_subscription.assert_not_called()
    assert account.entry.runtime_data.devices[DEVICE_ID].status == filtered
    assert hass.states.get(FAN).attributes["percentage_step"] == 20
    assert hass.states.get(FAN).attributes["percentage"] == 0
    assert hass.states.get(LIGHT).state == "on"
    assert hass.states.get(DURATION).state == "10"


@pytest.mark.parametrize(("percentage", "speed"), [(20, 1), (40, 2), (60, 3), (80, 4), (100, 5)])
async def test_speeds(
    hass: HomeAssistant,
    account: FakeAccount,
    extended_entry: MockConfigEntry,
    percentage: int,
    speed: int,
) -> None:
    await setup(hass, extended_entry)
    await hass.services.async_call(
        "fan", "set_percentage", {ATTR_ENTITY_ID: FAN, "percentage": percentage}, blocking=True
    )
    assert account.client.execute_device_command.call_args_list == [
        call(DEVICE_ID, Capability.SWITCH, Command.ON, "hood"),
        call(
            DEVICE_ID,
            Capability.SAMSUNG_CE_HOOD_FAN_SPEED,
            Command.SET_HOOD_FAN_SPEED,
            "hood",
            argument=speed,
        ),
    ]
    account.push(Capability.SWITCH, Attribute.SWITCH, "on")
    account.push(Capability.SAMSUNG_CE_HOOD_FAN_SPEED, Attribute.HOOD_FAN_SPEED, speed)
    assert hass.states.get(FAN).attributes["percentage"] == percentage


async def test_zero_never_turns_on(
    hass: HomeAssistant, account: FakeAccount, extended_entry: MockConfigEntry
) -> None:
    await setup(hass, extended_entry)
    await hass.services.async_call(
        "fan", "set_percentage", {ATTR_ENTITY_ID: FAN, "percentage": 0}, blocking=True
    )
    account.client.execute_device_command.assert_awaited_once_with(
        DEVICE_ID, Capability.SWITCH, Command.OFF, "hood"
    )


async def test_turn_on_percentage(
    hass: HomeAssistant, account: FakeAccount, extended_entry: MockConfigEntry
) -> None:
    await setup(hass, extended_entry)
    await hass.services.async_call(
        "fan", "turn_on", {ATTR_ENTITY_ID: FAN, "percentage": 60}, blocking=True
    )
    assert account.client.execute_device_command.call_args_list[-1] == call(
        DEVICE_ID,
        Capability.SAMSUNG_CE_HOOD_FAN_SPEED,
        Command.SET_HOOD_FAN_SPEED,
        "hood",
        argument=3,
    )


@pytest.mark.parametrize(("action", "level"), [("turn_on", "high"), ("turn_off", "off")])
async def test_light_independent(
    hass: HomeAssistant,
    account: FakeAccount,
    extended_entry: MockConfigEntry,
    action: str,
    level: str,
) -> None:
    await setup(hass, extended_entry)
    await hass.services.async_call("light", action, {ATTR_ENTITY_ID: LIGHT}, blocking=True)
    account.client.execute_device_command.assert_awaited_once_with(
        DEVICE_ID, Capability.SAMSUNG_CE_LAMP, Command.SET_BRIGHTNESS_LEVEL, "hood", argument=level
    )


async def test_duration_and_timer(
    hass: HomeAssistant, account: FakeAccount, extended_entry: MockConfigEntry
) -> None:
    await setup(hass, extended_entry)
    await hass.services.async_call(
        "number", "set_value", {ATTR_ENTITY_ID: DURATION, "value": 5}, blocking=True
    )
    account.client.execute_device_command.assert_awaited_once_with(
        DEVICE_ID,
        Capability.SAMSUNG_CE_COUNT_DOWN_TIMER,
        Command.SET_START_VALUE,
        "hood",
        argument=[5, "min"],
    )
    account.push(Capability.SWITCH, Attribute.SWITCH, "on")
    account.push(Capability.SAMSUNG_CE_COUNT_DOWN_TIMER, Attribute.START_VALUE, 5)
    await hass.services.async_call("button", "press", {ATTR_ENTITY_ID: START}, blocking=True)
    assert account.client.execute_device_command.call_args_list[-1] == call(
        DEVICE_ID, Capability.SAMSUNG_CE_COUNT_DOWN_TIMER, Command.START, "hood"
    )
    account.push(Capability.SAMSUNG_CE_COUNT_DOWN_TIMER, Attribute.STATUS, "running")
    account.push(Capability.SAMSUNG_CE_COUNT_DOWN_TIMER, Attribute.CURRENT_VALUE, 4)
    assert hass.states.get(STATUS).state == "running"
    assert float(hass.states.get(REMAINING).state) == 4
    await hass.services.async_call("button", "press", {ATTR_ENTITY_ID: CANCEL}, blocking=True)
    assert account.client.execute_device_command.call_args_list[-1] == call(
        DEVICE_ID, Capability.SAMSUNG_CE_COUNT_DOWN_TIMER, Command.CANCEL, "hood"
    )


async def test_start_requires_fan(
    hass: HomeAssistant, account: FakeAccount, extended_entry: MockConfigEntry
) -> None:
    await setup(hass, extended_entry)
    with pytest.raises(ServiceValidationError, match="Turn on"):
        await hass.services.async_call("button", "press", {ATTR_ENTITY_ID: START}, blocking=True)
    account.client.execute_device_command.assert_not_called()


@pytest.mark.parametrize("entity_id", [FAN, LIGHT, DURATION, REMAINING, STATUS, START, CANCEL])
async def test_hood_disconnect(
    hass: HomeAssistant, account: FakeAccount, extended_entry: MockConfigEntry, entity_id: str
) -> None:
    await setup(hass, extended_entry)
    account.push(Capability.SAMSUNG_CE_CONNECTION_STATE, Attribute.CONNECTION_STATE, "disconnected")
    assert hass.states.get(entity_id).state == "unavailable"
    assert hass.states.get(CONNECTION).state == "off"
    account.push(Capability.SAMSUNG_CE_CONNECTION_STATE, Attribute.CONNECTION_STATE, "connected")
    assert hass.states.get(entity_id).state != "unavailable"


@pytest.mark.parametrize(
    ("entity_id", "attribute"),
    [
        (DURATION, Attribute.START_VALUE),
        (REMAINING, Attribute.CURRENT_VALUE),
        (STATUS, Attribute.STATUS),
    ],
)
async def test_null_timer(
    hass: HomeAssistant,
    account: FakeAccount,
    extended_entry: MockConfigEntry,
    entity_id: str,
    attribute: Attribute,
) -> None:
    await setup(hass, extended_entry)
    account.push(Capability.SAMSUNG_CE_COUNT_DOWN_TIMER, attribute, None)
    assert hass.states.get(entity_id).state == "unknown"


@pytest.mark.parametrize(
    ("unit", "value", "expected_argument"),
    [("min", 10, 5), ("hour", 0.5, 5 / 60), ("sec", 120, 300)],
)
async def test_units(
    hass: HomeAssistant,
    account: FakeAccount,
    extended_entry: MockConfigEntry,
    unit: str,
    value: float,
    expected_argument: float,
) -> None:
    status = account.raw["hood"][Capability.SAMSUNG_CE_COUNT_DOWN_TIMER][Attribute.START_VALUE]
    status.unit = unit
    status.value = value
    await setup(hass, extended_entry)
    await hass.services.async_call(
        "number", "set_value", {ATTR_ENTITY_ID: DURATION, "value": 5}, blocking=True
    )
    args = account.client.execute_device_command.call_args.kwargs["argument"]
    assert args[0] == pytest.approx(expected_argument)
    assert args[1] == unit


async def test_selected_features(
    hass: HomeAssistant, account: FakeAccount, extended_entry: MockConfigEntry
) -> None:
    hass.config_entries.async_update_entry(extended_entry, options={CONF_FEATURES: ["light"]})
    await setup(hass, extended_entry)
    assert hass.states.get(LIGHT) is not None
    assert hass.states.get(FAN) is None
    assert hass.states.get(DURATION) is None


async def test_native_reload(
    hass: HomeAssistant, account: FakeAccount, extended_entry: MockConfigEntry
) -> None:
    await setup(hass, extended_entry)
    original_count = len(account.listeners)
    account.entry._async_set_state(hass, ConfigEntryState.UNLOAD_IN_PROGRESS, None)
    assert not account.listeners
    assert not account.health_listeners
    assert hass.states.get(FAN).state == "unavailable"
    new_client, listeners, health = mock_client(account.raw)
    previous = account.entry.runtime_data
    account.entry.runtime_data = SimpleNamespace(client=new_client, devices=previous.devices)
    account.entry._async_set_state(hass, ConfigEntryState.LOADED, None)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(listeners) == original_count
    assert len(health) == 1
    assert hass.states.get(FAN).state == "off"
    assert extended_entry.runtime_data.coordinator.client is new_client
    await hass.services.async_call("light", "turn_off", {ATTR_ENTITY_ID: LIGHT}, blocking=True)
    new_client.execute_device_command.assert_awaited_once_with(
        DEVICE_ID, Capability.SAMSUNG_CE_LAMP, Command.SET_BRIGHTNESS_LEVEL, "hood", argument="off"
    )
    account.client.execute_device_command.assert_not_called()


async def test_unload_cleans_listeners(
    hass: HomeAssistant, account: FakeAccount, extended_entry: MockConfigEntry
) -> None:
    await setup(hass, extended_entry)
    assert await hass.config_entries.async_unload(extended_entry.entry_id)
    await hass.async_block_till_done()
    assert not account.listeners
    assert not account.health_listeners
    assert not account.entry._on_state_change


async def test_native_not_ready(
    hass: HomeAssistant, account: FakeAccount, extended_entry: MockConfigEntry
) -> None:
    account.entry._async_set_state(hass, ConfigEntryState.SETUP_RETRY, None)
    assert not await hass.config_entries.async_setup(extended_entry.entry_id)
    assert extended_entry.state is ConfigEntryState.SETUP_RETRY
    account.client.get_device_status.assert_not_called()


async def test_command_error(
    hass: HomeAssistant, account: FakeAccount, extended_entry: MockConfigEntry
) -> None:
    await setup(hass, extended_entry)
    account.client.execute_device_command.side_effect = SmartThingsConnectionError(
        "network failure"
    )
    with pytest.raises(HomeAssistantError, match="could not complete"):
        await hass.services.async_call("light", "turn_off", {ATTR_ENTITY_ID: LIGHT}, blocking=True)


async def test_health(
    hass: HomeAssistant, account: FakeAccount, extended_entry: MockConfigEntry
) -> None:
    await setup(hass, extended_entry)
    for _, callback in account.health_listeners:
        callback(
            DeviceHealthEvent(
                device_id=DEVICE_ID, location_id="location", status=HealthStatus.OFFLINE
            )
        )
    assert hass.states.get(FAN).state == "unavailable"


async def test_diagnostics(
    hass: HomeAssistant, account: FakeAccount, extended_entry: MockConfigEntry
) -> None:
    from custom_components.smartthings_extended.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    await setup(hass, extended_entry)
    result = await async_get_config_entry_diagnostics(hass, extended_entry)
    assert DEVICE_ID not in str(result)
    assert "token" not in str(result)
    assert result["native_connection_available"]


async def test_reload_network_retry(
    hass: HomeAssistant, account: FakeAccount, extended_entry: MockConfigEntry, freezer
) -> None:
    """Recover when the replacement native client initially cannot read status."""
    from datetime import timedelta

    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    await setup(hass, extended_entry)
    account.entry._async_set_state(hass, ConfigEntryState.UNLOAD_IN_PROGRESS, None)
    client, listeners, _ = mock_client(account.raw)
    client.get_device_status.side_effect = [
        SmartThingsConnectionError("temporary"),
        deepcopy(account.raw),
    ]
    account.entry.runtime_data = SimpleNamespace(
        client=client, devices=account.entry.runtime_data.devices
    )
    account.entry._async_set_state(hass, ConfigEntryState.LOADED, None)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(FAN).state == "unavailable"
    assert not listeners
    freezer.tick(timedelta(seconds=31))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(FAN).state == "off"
    assert listeners
    assert client.get_device_status.await_count == 2


async def test_fresh_health_overrides_native_snapshot(
    hass: HomeAssistant, account: FakeAccount, extended_entry: MockConfigEntry
) -> None:
    """The native runtime's initial health can be stale after later events."""
    account.entry.runtime_data.devices[DEVICE_ID].online = False
    await setup(hass, extended_entry)
    assert hass.states.get(FAN).state == "off"
    account.client.get_device_health.assert_awaited_once_with(DEVICE_ID)


async def test_initial_device_offline(
    hass: HomeAssistant, account: FakeAccount, extended_entry: MockConfigEntry
) -> None:
    account.client.get_device_health.return_value = SimpleNamespace(state=HealthStatus.OFFLINE)
    await setup(hass, extended_entry)
    assert hass.states.get(FAN).state == "unavailable"
