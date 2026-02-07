"""Config flow for Ariston integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
import voluptuous_serialize

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
from homeassistant.helpers import config_validation as cv

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
        self.cloud_devices = []

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

            response = await ariston.async_connect(
                self.cloud_username,
                self.cloud_password,
                self.cloud_api_url,
                self.cloud_api_user_agent,
            )
            if not response:
                errors["base"] = "invalid_auth"
                return self.async_show_form(
                    step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
                )
                
            self.cloud_devices = await ariston.async_discover()
            if len(self.cloud_devices) == 0:
                errors["base"] = "no device found"
                return self.async_show_form(
                    step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
                )
                
            if len(self.cloud_devices) == 1:
                return await self.async_create_or_update_entry(self.cloud_devices[0])
                
            if len(self.cloud_devices) > 1:
                return await self.async_step_select()
                
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
            )

        # This shouldn't be reached, but just in case
        errors["base"] = "unknown"
        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_create_or_update_entry(self, cloud_device=None, selected_indices=None):
        """Create or update config entry."""
        if selected_indices is not None:
            # Create entries for selected devices
            selected_devices = [self.cloud_devices[i] for i in selected_indices]
            
            for device in selected_devices:
                unique_id = device[DeviceAttribute.GW]
                existing_entry = await self.async_set_unique_id(unique_id, raise_on_progress=False)
                
                if existing_entry:
                    # Update existing entry
                    self.hass.config_entries.async_update_entry(
                        existing_entry,
                        data={
                            CONF_USERNAME: self.cloud_username,
                            CONF_PASSWORD: self.cloud_password,
                            API_URL_SETTING: self.cloud_api_url,
                            API_USER_AGENT: self.cloud_api_user_agent,
                            CONF_DEVICE: device,
                        },
                    )
                    await self.hass.config_entries.async_reload(existing_entry.entry_id)
                else:
                    # Create new entry
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured()
                    
                    return self.async_create_entry(
                        title=device[DeviceAttribute.NAME],
                        data={
                            CONF_USERNAME: self.cloud_username,
                            CONF_PASSWORD: self.cloud_password,
                            API_URL_SETTING: self.cloud_api_url,
                            API_USER_AGENT: self.cloud_api_user_agent,
                            CONF_DEVICE: device,
                        },
                    )
            
            # If all were existing entries, abort
            return self.async_abort(reason="reauth_successful")
        else:
            # Single device flow (original)
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
        """Multiple device found, let user select which ones to add."""
        errors = {}
        
        if user_input is not None:
            # Get selected device indices
            selected_indices = user_input.get("devices", [])
            
            if not selected_indices:
                errors["base"] = "no_device_selected"
                return self.async_show_form(
                    step_id="select",
                    data_schema=self._get_select_schema(),
                    errors=errors
                )
            
            if len(selected_indices) == 1:
                # If only one device selected, use the single device flow
                return await self.async_create_or_update_entry(
                    self.cloud_devices[selected_indices[0]]
                )
            else:
                # Multiple devices selected - we'll handle them one by one
                # Store selected indices to process them
                self.selected_indices = selected_indices
                # Process first device
                return await self.async_create_or_update_entry(
                    selected_indices=selected_indices
                )

        return self.async_show_form(
            step_id="select",
            data_schema=self._get_select_schema(),
            errors=errors
        )

    def _get_select_schema(self):
        """Get schema for device selection."""
        # Create list of device names for selection
        device_options = {}
        for i, device in enumerate(self.cloud_devices):
            name = device.get(DeviceAttribute.NAME, "Unknown")
            model = device.get(DeviceAttribute.SN, "Unknown")
            gw_id = device.get(DeviceAttribute.GW, "Unknown")
            device_options[str(i)] = f"{name} - {model} ({gw_id})"
        
        return vol.Schema({
            vol.Optional(
                "devices",
                default=[],
                description="Select devices to add"
            ): cv.multi_select(device_options),
        })

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
            # Update config entry data if credentials were changed
            if any(
                user_input.get(key) != self.config_entry.data.get(key)
                for key in [CONF_USERNAME, CONF_PASSWORD, API_URL_SETTING, API_USER_AGENT]
            ):
                # Test new credentials before updating
                try:
                    ariston = Ariston()
                    response = await ariston.async_connect(
                        user_input[CONF_USERNAME],
                        user_input[CONF_PASSWORD],
                        user_input.get(API_URL_SETTING, ARISTON_API_URL),
                        user_input.get(API_USER_AGENT, ARISTON_USER_AGENT),
                    )
                    
                    if not response:
                        return self.async_show_form(
                            step_id="init",
                            data_schema=self._get_options_schema(),
                            errors={"base": "invalid_auth"}
                        )
                    
                    # Update config entry data with new credentials
                    new_data = {**self.config_entry.data}
                    new_data.update({
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        API_URL_SETTING: user_input.get(API_URL_SETTING, ARISTON_API_URL),
                        API_USER_AGENT: user_input.get(API_USER_AGENT, ARISTON_USER_AGENT),
                    })
                    
                    self.hass.config_entries.async_update_entry(
                        self.config_entry,
                        data=new_data
                    )
                    
                except Exception:
                    return self.async_show_form(
                        step_id="init",
                        data_schema=self._get_options_schema(),
                        errors={"base": "unknown"}
                    )
            
            # Return options (scan intervals)
            return self.async_create_entry(
                title="",
                data={
                    CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL],
                    ENERGY_SCAN_INTERVAL: user_input[ENERGY_SCAN_INTERVAL],
                    BUS_ERRORS_SCAN_INTERVAL: user_input[BUS_ERRORS_SCAN_INTERVAL],
                }
            )

        return self.async_show_form(
            step_id="init",
            data_schema=self._get_options_schema(),
        )

    def _get_options_schema(self):
        """Get options schema."""
        # Get current values
        data = self.config_entry.data
        options = self.config_entry.options
        
        scan_interval = options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS)
        energy_scan_interval = options.get(
            ENERGY_SCAN_INTERVAL, DEFAULT_ENERGY_SCAN_INTERVAL_MINUTES
        )
        bus_errors_scan_interval = options.get(
            BUS_ERRORS_SCAN_INTERVAL, DEFAULT_BUS_ERRORS_SCAN_INTERVAL_SECONDS
        )
        
        # Build schema with current values
        return vol.Schema({
            vol.Required(
                CONF_USERNAME,
                default=data.get(CONF_USERNAME, "")
            ): str,
            vol.Required(
                CONF_PASSWORD,
                default=data.get(CONF_PASSWORD, "")
            ): str,
            vol.Optional(
                API_URL_SETTING,
                default=data.get(API_URL_SETTING, ARISTON_API_URL)
            ): str,
            vol.Optional(
                API_USER_AGENT,
                default=data.get(API_USER_AGENT, ARISTON_USER_AGENT)
            ): str,
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
        })