"""Config flow and options flow for Aosu Cameras."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from .api import AosuAuthError, AsyncAosuClient
from .const import (
    CONF_COMPREFACE_API_KEY,
    CONF_COMPREFACE_URL,
    CONF_EMAIL,
    CONF_FACE_THRESHOLD,
    CONF_PASSWORD,
    CONF_REGION,
    CONF_SCAN_INTERVAL,
    DEFAULT_FACE_THRESHOLD,
    DEFAULT_REGION,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)


class AosuConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Aosu Cameras."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        if user_input is not None:
            client = AsyncAosuClient(
                email=user_input[CONF_EMAIL],
                password=user_input[CONF_PASSWORD],
                region=user_input.get(CONF_REGION, DEFAULT_REGION),
            )
            try:
                await client.async_login()
            except AosuAuthError:
                errors["base"] = "invalid_auth"
            except Exception:
                errors["base"] = "cannot_connect"
            finally:
                await client.async_close()

            if not errors:
                await self.async_set_unique_id(user_input[CONF_EMAIL].strip().lower())
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Aosu ({user_input[CONF_EMAIL].strip().lower()})",
                    data=user_input,
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_EMAIL): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Optional(CONF_REGION, default=DEFAULT_REGION): vol.In(["eu", "us", "ap", "cn"]),
                vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(int, vol.Range(min=10, max=300)),
                vol.Optional(CONF_COMPREFACE_URL, default=""): str,
                vol.Optional(CONF_COMPREFACE_API_KEY, default=""): str,
                vol.Optional(CONF_FACE_THRESHOLD, default=DEFAULT_FACE_THRESHOLD): vol.All(vol.Coerce(float), vol.Range(min=0.3, max=0.99)),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return AosuOptionsFlow(config_entry)


class AosuOptionsFlow(config_entries.OptionsFlow):
    """Options flow to adjust polling and local CompreFace settings."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        opts = {**self._entry.data, **self._entry.options}
        schema = vol.Schema(
            {
                vol.Optional(CONF_SCAN_INTERVAL, default=opts.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)): vol.All(int, vol.Range(min=10, max=300)),
                vol.Optional(CONF_COMPREFACE_URL, default=opts.get(CONF_COMPREFACE_URL, "")): str,
                vol.Optional(CONF_COMPREFACE_API_KEY, default=opts.get(CONF_COMPREFACE_API_KEY, "")): str,
                vol.Optional(CONF_FACE_THRESHOLD, default=opts.get(CONF_FACE_THRESHOLD, DEFAULT_FACE_THRESHOLD)): vol.All(vol.Coerce(float), vol.Range(min=0.3, max=0.99)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
