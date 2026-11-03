"""Select the native account, devices, and extra hood features."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_DEVICES,
    CONF_FEATURES,
    CONF_SOURCE,
    CONF_TIMER_MAX,
    DEFAULT_TIMER_MAX,
    DOMAIN,
    FEATURES,
    NAME,
    NATIVE_DOMAIN,
)
from .native import hood_devices, native_data, source_entry


def device_schema(devices: dict[str, str], values: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_DEVICES,
                default=[
                    device_id for device_id in values.get(CONF_DEVICES, []) if device_id in devices
                ],
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(value=key, label=label)
                        for key, label in devices.items()
                    ],
                    multiple=True,
                )
            ),
            vol.Required(
                CONF_FEATURES, default=values.get(CONF_FEATURES, list(FEATURES))
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=list(FEATURES), multiple=True, translation_key="features"
                )
            ),
            vol.Required(
                CONF_TIMER_MAX, default=values.get(CONF_TIMER_MAX, DEFAULT_TIMER_MAX)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1,
                    max=1440,
                    step=1,
                    mode=selector.NumberSelectorMode.BOX,
                    unit_of_measurement="min",
                )
            ),
        }
    )


def valid_selection(values: dict[str, Any], devices: dict[str, str]) -> bool:
    return (
        bool(values[CONF_DEVICES])
        and set(values[CONF_DEVICES]).issubset(devices)
        and bool(values[CONF_FEATURES])
        and set(values[CONF_FEATURES]).issubset(FEATURES)
    )


class SmartThingsExtendedFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> config_entries.OptionsFlow:
        return ExtendedOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entries = {
            entry.entry_id: entry
            for entry in self.hass.config_entries.async_entries(NATIVE_DOMAIN)
            if native_data(entry) is not None
        }
        if not entries:
            return self.async_abort(reason="native_required")
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input[CONF_SOURCE] not in entries:
                errors["base"] = "native_not_ready"
            else:
                self._source_id = user_input[CONF_SOURCE]
                await self.async_set_unique_id(self._source_id)
                self._abort_if_unique_id_configured()
                return await self.async_step_devices()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SOURCE, default=next(iter(entries))): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(value=entry_id, label=entry.title)
                                for entry_id, entry in entries.items()
                            ]
                        )
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_devices(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        source = source_entry(self.hass, self._source_id)
        if source is None or native_data(source) is None:
            return self.async_abort(reason="native_required")
        devices = hood_devices(source)
        if not devices:
            return self.async_abort(reason="no_supported_devices")
        errors: dict[str, str] = {}
        if user_input is not None:
            if valid_selection(user_input, devices):
                return self.async_create_entry(
                    title=f"{NAME} ({source.title})",
                    data={CONF_SOURCE: self._source_id, **user_input},
                )
            errors["base"] = "invalid_selection"
        return self.async_show_form(
            step_id="devices", data_schema=device_schema(devices, user_input or {}), errors=errors
        )


class ExtendedOptionsFlow(config_entries.OptionsFlowWithReload):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        source = source_entry(self.hass, self.config_entry.data[CONF_SOURCE])
        if source is None or native_data(source) is None:
            return self.async_abort(reason="native_required")
        devices = hood_devices(source)
        errors: dict[str, str] = {}
        if user_input is not None:
            if valid_selection(user_input, devices):
                return self.async_create_entry(title="", data=user_input)
            errors["base"] = "invalid_selection"
        return self.async_show_form(
            step_id="init",
            data_schema=device_schema(
                devices, user_input or {**self.config_entry.data, **self.config_entry.options}
            ),
            errors=errors,
        )
