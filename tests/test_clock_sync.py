"""Clock command format, local time/DST, and appropriate device selection."""

from dataclasses import replace

import pytest
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pysmartthings import Attribute, Capability, Command, SmartThingsConnectionError, Status
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smartthings_extended.const import CONF_FEATURES

from .conftest import OVEN_ID, FakeAccount
from .test_integration import setup

CLOCK = "button.oven_sync_clock"


@pytest.mark.parametrize(
    ("zone", "instant", "expected"),
    [
        ("America/New_York", "2026-01-15T12:34:56.123456+00:00", "2026-01-15T07:34:56"),
        ("America/New_York", "2026-07-15T12:34:56+00:00", "2026-07-15T08:34:56"),
        ("Asia/Kathmandu", "2026-01-15T12:34:56+00:00", "2026-01-15T18:19:56"),
        ("Etc/UTC", "2026-01-15T12:34:56+00:00", "2026-01-15T12:34:56"),
    ],
)
async def test_sync_current_local_time(
    hass: HomeAssistant,
    appliance_account: FakeAccount,
    appliance_entry: MockConfigEntry,
    freezer,
    zone: str,
    instant: str,
    expected: str,
) -> None:
    await hass.config.async_set_time_zone(zone)
    await setup(hass, appliance_entry)
    # Installation never changes the clock. Each press computes a fresh local time.
    appliance_account.client.execute_device_command.assert_not_called()
    freezer.move_to(instant)
    await hass.services.async_call("button", "press", {ATTR_ENTITY_ID: CLOCK}, blocking=True)
    appliance_account.client.execute_device_command.assert_awaited_once_with(
        OVEN_ID,
        Capability.EXECUTE,
        Command.EXECUTE,
        "main",
        argument=["/configuration/vs/0", {"x.com.samsung.da.currentTime": expected}],
    )
    assert [e for e in hass.states.async_entity_ids("button") if e.endswith("sync_clock")] == [
        CLOCK
    ]


@pytest.mark.parametrize("reason", ["no_execute", "disabled_execute", "non_samsung", "hood_only"])
async def test_unsupported_devices_do_not_get_clock_button(
    hass: HomeAssistant,
    appliance_account: FakeAccount,
    appliance_entry: MockConfigEntry,
    oven_status: dict,
    reason: str,
) -> None:
    if reason == "no_execute":
        del oven_status["main"][Capability.EXECUTE]
    elif reason == "disabled_execute":
        oven_status["main"][Capability.CUSTOM_DISABLED_CAPABILITIES][
            Attribute.DISABLED_CAPABILITIES
        ].value = ["execute"]
    elif reason == "non_samsung":
        full = appliance_account.entry.runtime_data.devices[OVEN_ID]
        full.device = replace(full.device, ocf=None, device_manufacturer_code="Other")
    else:
        hass.config_entries.async_update_entry(
            appliance_entry, options={CONF_FEATURES: ["fan", "light", "timer"]}
        )
    await setup(hass, appliance_entry)
    assert hass.states.get(CLOCK) is None
    assert hass.states.get("button.cooktop_sync_clock") is None


async def test_clock_does_not_require_cooking_remote_control(
    hass: HomeAssistant,
    appliance_account: FakeAccount,
    appliance_entry: MockConfigEntry,
    oven_status: dict,
) -> None:
    oven_status["main"][Capability.REMOTE_CONTROL_STATUS] = {
        Attribute.REMOTE_CONTROL_ENABLED: Status(value="false")
    }
    await setup(hass, appliance_entry)
    assert hass.states.get(CLOCK).state != "unavailable"
    await hass.services.async_call("button", "press", {ATTR_ENTITY_ID: CLOCK}, blocking=True)
    assert appliance_account.client.execute_device_command.await_count == 1


async def test_execute_disabled_after_setup(
    hass: HomeAssistant, appliance_account: FakeAccount, appliance_entry: MockConfigEntry
) -> None:
    await setup(hass, appliance_entry)
    appliance_account.push(
        Capability.CUSTOM_DISABLED_CAPABILITIES,
        Attribute.DISABLED_CAPABILITIES,
        ["execute"],
        "main",
        device_id=OVEN_ID,
    )
    assert hass.states.get(CLOCK).state == "unavailable"
    await hass.services.async_call("button", "press", {ATTR_ENTITY_ID: CLOCK}, blocking=True)
    appliance_account.client.execute_device_command.assert_not_called()


async def test_clock_connection_error(
    hass: HomeAssistant, appliance_account: FakeAccount, appliance_entry: MockConfigEntry
) -> None:
    await setup(hass, appliance_entry)
    appliance_account.client.execute_device_command.side_effect = SmartThingsConnectionError(
        "offline"
    )
    with pytest.raises(HomeAssistantError, match="could not complete"):
        await hass.services.async_call("button", "press", {ATTR_ENTITY_ID: CLOCK}, blocking=True)
