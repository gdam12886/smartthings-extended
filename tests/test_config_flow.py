"""Select a native account and additional capabilities through the UI."""

from copy import deepcopy

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smartthings_extended.const import (
    CONF_DEVICES,
    CONF_FEATURES,
    CONF_SOURCE,
    CONF_TIMER_MAX,
    DOMAIN,
)

from .conftest import DEVICE_ID, FakeAccount


async def test_no_native_account(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "native_required"


async def test_flow(hass: HomeAssistant, account: FakeAccount) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SOURCE: account.entry.entry_id}
    )
    assert result["step_id"] == "devices"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_DEVICES: [DEVICE_ID], CONF_FEATURES: ["light", "fan", "timer"], CONF_TIMER_MAX: 60},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_SOURCE: account.entry.entry_id,
        CONF_DEVICES: [DEVICE_ID],
        CONF_FEATURES: ["light", "fan", "timer"],
        CONF_TIMER_MAX: 60,
    }
    await hass.async_block_till_done()


async def test_duplicate(
    hass: HomeAssistant, account: FakeAccount, extended_entry: MockConfigEntry
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SOURCE: account.entry.entry_id}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_no_devices(hass: HomeAssistant, account: FakeAccount) -> None:
    account.entry.runtime_data.devices = {}
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SOURCE: account.entry.entry_id}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_supported_devices"


async def test_empty_selection(hass: HomeAssistant, account: FakeAccount) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SOURCE: account.entry.entry_id}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICES: [], CONF_FEATURES: ["fan"], CONF_TIMER_MAX: 60}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_selection"}


async def test_options(
    hass: HomeAssistant, account: FakeAccount, extended_entry: MockConfigEntry
) -> None:
    assert await hass.config_entries.async_setup(extended_entry.entry_id)
    await hass.async_block_till_done()
    before = deepcopy(account.entry.runtime_data.devices[DEVICE_ID].status)
    result = await hass.config_entries.options.async_init(extended_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_DEVICES: [DEVICE_ID], CONF_FEATURES: ["light"], CONF_TIMER_MAX: 30}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert extended_entry.runtime_data.features == ["light"]
    assert extended_entry.runtime_data.timer_max == 30
    assert account.entry.runtime_data.devices[DEVICE_ID].status == before


async def test_options_remove_deselected_controls(
    hass: HomeAssistant, account: FakeAccount, extended_entry: MockConfigEntry
) -> None:
    assert await hass.config_entries.async_setup(extended_entry.entry_id)
    await hass.async_block_till_done()
    native_devices = set(account.entry.runtime_data.devices)
    result = await hass.config_entries.options.async_init(extended_entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_DEVICES: [DEVICE_ID], CONF_FEATURES: ["light"], CONF_TIMER_MAX: 60}
    )
    await hass.async_block_till_done()
    assert er.async_get(hass).async_get("fan.cooktop_hood_fan") is None
    assert hass.states.get("light.cooktop_hood_light") is not None
    assert set(account.entry.runtime_data.devices) == native_devices
