"""Config flow for Ariston integration."""
from __future__ import annotations

import logging
import voluptuous as vol

from typing import Any

from homeassistant import config_entries
from homeassistant.const import (
    CONF_DEVICE,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
)
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from ariston import Ariston, DeviceAttribute

from .const import (
    DEFAULT_ENERGY_SCAN_INTERVAL_MINUTES,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    DOMAIN,
    ENERGY_SCAN_INTERVAL,
)

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
        self.cloud_username: str | None = None
        self.cloud_password: str | None = None
        self.cloud_devices = {}

    async def async_step_reauth(self, user_input=None):
        """Perform reauth upon an API authentication error."""
        return await self.async_step_user()

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
            ariston = Ariston()

            reponse = await ariston.async_connect(
                self.cloud_username, self.cloud_password
            )
            if not reponse:
                errors["base"] = "invalid_auth"
                return self.async_show_form(
                    step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
                )
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
        else:
            cloud_devices = await ariston.async_discover()
            if len(cloud_devices) == 0:
                errors["base"] = "no device found"
            if len(cloud_devices) == 1:
                return await self.async_create_or_update_entry(cloud_devices[0])
            if len(cloud_devices) > 1:
                for device in cloud_devices:
                    name = device[DeviceAttribute.NAME]
                    model = device[DeviceAttribute.SN]
                    list_name = f"{name} - {model}"
                    self.cloud_devices[list_name] = device

                return await self.async_step_select()

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_create_or_update_entry(self, cloud_device):
        """Create or update config entry"""
        existing_entry = await self.async_set_unique_id(
            cloud_device[DeviceAttribute.GW], raise_on_progress=False
        )
        if existing_entry:
            data = existing_entry.data.copy()
            self.hass.config_entries.async_update_entry(existing_entry, data=data)
            await self.hass.config_entries.async_reload(existing_entry.entry_id)
            return self.async_abort(reason="reauth_successful")

        return self.async_create_entry(
            title=cloud_device[DeviceAttribute.NAME],
            data={
                CONF_USERNAME: self.cloud_username,
                CONF_PASSWORD: self.cloud_password,
                CONF_DEVICE: cloud_device,
            },
        )

    async def async_step_select(self, user_input=None):
        """Multiple device found, select one of them"""
        errors = {}
        if user_input is not None:
            return await self.async_create_or_update_entry(
                self.cloud_devices[user_input["select_device"]]
            )

        select_schema = vol.Schema(
            {vol.Required("select_device"): vol.In(list(self.cloud_devices))}
        )

        return self.async_show_form(
            step_id="select", data_schema=select_schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return AristonOptionsFlow(config_entry)


class AristonOptionsFlow(config_entries.OptionsFlow):
    """Handle Ariston options."""

    def __init__(self, config_entry):
        """Initialize Ariston options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        scan_interval = options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS)
        energy_scan_interval = options.get(
            ENERGY_SCAN_INTERVAL, DEFAULT_ENERGY_SCAN_INTERVAL_MINUTES
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=scan_interval,
                    ): int,
                    vol.Optional(
                        ENERGY_SCAN_INTERVAL,
                        default=energy_scan_interval,
                    ): int,
                }
            ),
            last_step=True,
        )
