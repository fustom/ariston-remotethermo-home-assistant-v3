"""Config flow for Ariston integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import (
    CONF_DEVICE,
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_AUTH_PROVIDERS,
)
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .ariston import AristonAPI

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class AristonConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Ariston Config Flow."""

    VERSION = 1

    def __init__(self):
        self.api = AristonAPI()
        self.cloud_username = None
        self.cloud_password = None
        self.cloud_devices = {}

    async def try_login(self) -> None:
        """Validate the user input allows us to connect.

        Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
        """
        response = await self.api.connect(
            username=self.cloud_username,
            password=self.cloud_password,
        )

        if not response:
            raise InvalidAuth

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA
            )

        errors = {}

        try:
            self.cloud_username = user_input[CONF_USERNAME]
            self.cloud_password = user_input[CONF_PASSWORD]
            await self.try_login()
        except CannotConnect:
            errors["base"] = "cannot_connect"
        except InvalidAuth:
            errors["base"] = "invalid_auth"
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
        else:
            cloud_devices = await self.api.get_devices()
            if len(cloud_devices) == 1:
                cloud_device = cloud_devices[0]
                existing_entry = await self.async_set_unique_id(
                    cloud_device["gwId"], raise_on_progress=False
                )
                if existing_entry:
                    data = existing_entry.data.copy()
                    self.hass.config_entries.async_update_entry(
                        existing_entry, data=data
                    )
                    await self.hass.config_entries.async_reload(existing_entry.entry_id)
                    return self.async_abort(reason="reauth_successful")

                return self.async_create_entry(
                    title=cloud_device["plantName"],
                    data={
                        CONF_USERNAME: self.cloud_username,
                        CONF_PASSWORD: self.cloud_password,
                        CONF_DEVICE: cloud_device,
                    },
                )
            for device in cloud_devices:
                name = device["plantName"]
                model = device["gwSerial"]
                list_name = f"{name} - {model}"
                self.cloud_devices[list_name] = device

            return await self.async_step_select()

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_select(self, user_input=None):
        errors = {}
        if user_input is not None:
            cloud_device = self.cloud_devices[user_input["select_device"]]
            return self.async_create_entry(
                title=cloud_device["plantName"],
                data={
                    CONF_USERNAME: self.cloud_username,
                    CONF_PASSWORD: self.cloud_password,
                    CONF_DEVICE: cloud_device,
                },
            )

        select_schema = vol.Schema(
            {vol.Required("select_device"): vol.In(list(self.cloud_devices))}
        )

        return self.async_show_form(
            step_id="select", data_schema=select_schema, errors=errors
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
