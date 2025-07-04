"""Config flow for Ariston integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from ariston import Ariston, DeviceAttribute
from ariston.const import ARISTON_API_URL, ARISTON_USER_AGENT
from homeassistant import config_entries
from homeassistant.const import (
    CONF_DEVICE,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
)
from homeassistant.core import callback

from .const import (
    API_URL_SETTING,
    API_USER_AGENT,
    BUS_ERRORS_SCAN_INTERVAL,
    DEFAULT_BUS_ERRORS_SCAN_INTERVAL_SECONDS,
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
        vol.Optional(API_URL_SETTING, default=ARISTON_API_URL): str,
        vol.Optional(API_USER_AGENT, default=ARISTON_USER_AGENT): str,
    }
)


class AristonConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Ariston Config Flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize Ariston config flow."""
        self.cloud_username: str = ""
        self.cloud_password: str = ""
        self.cloud_api_url: str = ARISTON_API_URL
        self.cloud_api_user_agent: str = ARISTON_USER_AGENT
        self.cloud_devices = {}

    async def async_step_reauth(self, user_input=None):
        """Perform reauth upon an API authentication error."""
        return await self.async_step_user()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA
            )

        errors = {}

        try:
            self.cloud_username = user_input[CONF_USERNAME]
            self.cloud_password = user_input[CONF_PASSWORD]
            self.cloud_api_url = user_input[API_URL_SETTING]
            self.cloud_api_user_agent = user_input[API_USER_AGENT]
            ariston = Ariston()

            reponse = await ariston.async_connect(
                self.cloud_username,
                self.cloud_password,
                self.cloud_api_url,
                self.cloud_api_user_agent,
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
        """Create or update config entry."""
        existing_entry = await self.async_set_unique_id(
            cloud_device[DeviceAttribute.GW], raise_on_progress=False
        )
        if existing_entry:
            self.hass.config_entries.async_update_entry(
                existing_entry,
                data={
                    CONF_USERNAME: self.cloud_username,
                    CONF_PASSWORD: self.cloud_password,
                    API_URL_SETTING: self.cloud_api_url,
                    API_USER_AGENT: self.cloud_api_user_agent,
                    CONF_DEVICE: cloud_device,
                },
            )
            await self.hass.config_entries.async_reload(existing_entry.entry_id)
            return self.async_abort(reason="reauth_successful")

        return self.async_create_entry(
            title=cloud_device[DeviceAttribute.NAME],
            data={
                CONF_USERNAME: self.cloud_username,
                CONF_PASSWORD: self.cloud_password,
                API_URL_SETTING: self.cloud_api_url,
                API_USER_AGENT: self.cloud_api_user_agent,
                CONF_DEVICE: cloud_device,
            },
        )

    async def async_step_select(self, user_input=None):
        """Multiple device found, select one of them."""
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
        return AristonOptionsFlow()


class AristonOptionsFlow(config_entries.OptionsFlow):
    """Handle Ariston options."""

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        scan_interval = options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS)
        energy_scan_interval = options.get(
            ENERGY_SCAN_INTERVAL, DEFAULT_ENERGY_SCAN_INTERVAL_MINUTES
        )
        bus_errors_scan_interval = options.get(
            BUS_ERRORS_SCAN_INTERVAL, DEFAULT_BUS_ERRORS_SCAN_INTERVAL_SECONDS
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
                    vol.Optional(
                        BUS_ERRORS_SCAN_INTERVAL,
                        default=bus_errors_scan_interval,
                    ): int,
                }
            ),
            last_step=True,
        )
