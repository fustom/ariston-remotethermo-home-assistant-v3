"""Support for Ariston water heaters."""
from __future__ import annotations

import logging

from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .ariston import AristonAPI
from .const import COORDINATORS, DOMAIN, FEATURES, API

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.water_heater import (
    SUPPORT_OPERATION_MODE,
    SUPPORT_TARGET_TEMPERATURE,
    WaterHeaterEntity,
)
from homeassistant.const import (
    CONF_DEVICE,
    TEMP_CELSIUS,
    TEMP_FAHRENHEIT,
    ATTR_TEMPERATURE,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Set up the Ariston water heater device from config entry."""
    api: AristonAPI = hass.data[DOMAIN][API]
    device = entry.data[CONF_DEVICE]
    features = hass.data[DOMAIN][FEATURES]
    coordinator = hass.data[DOMAIN][COORDINATORS]
    ariston_water_heater = AristonWaterHeater(api, device, features, coordinator)
    await ariston_water_heater.async_update()
    async_add_entities([ariston_water_heater])
    return


class AristonWaterHeater(CoordinatorEntity, WaterHeaterEntity):
    """Ariston Water Heater Device."""

    def __init__(
        self,
        api: AristonAPI,
        device,
        features,
        coordinator: DataUpdateCoordinator,
    ):
        """Initialize the thermostat."""

        # Pass coordinator to CoordinatorEntity.
        super().__init__(coordinator)

        self.api = api
        self.features = features
        self.location = "en-US"
        self.gw_id = device["gwId"]
        self.plant_name = device["plantName"]

        self.dhw_temp = None
        self.dhw_mode = None

    @property
    def name(self) -> str:
        """Return the name of the device."""
        return self.plant_name

    @property
    def unique_id(self) -> str:
        """Return a unique id for the device."""
        return f"{self.gw_id}-water_heater"

    @property
    def icon(self):
        return "mdi:water-pump"

    @property
    def current_temperature(self):
        """Return the temperature"""
        return self.dhw_temp["value"]

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        return self.dhw_temp["min"]

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self.dhw_temp["value"]

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        return self.dhw_temp["max"]

    @property
    def target_temperature_step(self):
        """Return the target temperature step support by the device."""
        return self.dhw_temp["step"]

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return TEMP_CELSIUS if self.dhw_temp["unit"] == "°C" else TEMP_FAHRENHEIT

    @property
    def supported_features(self) -> int:
        """Return the supported features for this device integration."""
        if self.features["dhwModeChangeable"]:
            return SUPPORT_TARGET_TEMPERATURE | SUPPORT_OPERATION_MODE
        return SUPPORT_TARGET_TEMPERATURE

    @property
    def operation_list(self):
        """List of available operation modes."""
        return self.dhw_mode["optTexts"]

    @property
    def current_operation(self):
        """Return current operation"""
        res = self.dhw_mode["options"].index(self.dhw_mode["value"])
        return self.dhw_mode["optTexts"][res]

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        if ATTR_TEMPERATURE not in kwargs:
            raise ValueError(f"Missing parameter {ATTR_TEMPERATURE}")

        temperature = kwargs[ATTR_TEMPERATURE]
        _LOGGER.debug(
            "Setting temperature to %d for %s",
            temperature,
            self.name,
        )

        await self.api.async_set_dhwtemp(
            self.gw_id, temperature, self.target_temperature
        )
        self.async_write_ha_state()

    async def async_set_operation_mode(self, operation_mode):
        """Set operation mode."""
        # self.api.set_dhw_mode(operation_mode)
        # self.dhw_mode["value"] = operation_mode
        # self.async_write_ha_state()
        _LOGGER.warning(
            "Set operation mode is currently not supported. I need device to get the api calls"
        )
        return

    async def async_update(self) -> None:
        """Update device properies"""
        data = await self.api.async_get_water_heater_properties(
            self.gw_id, self.features, self.location
        )
        for item in data["items"]:
            if item["id"] == "DhwTemp":
                self.dhw_temp = item
            if item["id"] == "DhwMode":
                self.dhw_mode = item
