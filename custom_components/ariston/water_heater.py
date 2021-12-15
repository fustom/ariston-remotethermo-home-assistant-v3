"""Support for Ariston water heaters."""
import logging

from .ariston import AristonAPI
from .const import DOMAIN, FEATURES, API

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
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    api: AristonAPI = hass.data[DOMAIN][API]
    device = entry.data[CONF_DEVICE]
    features = hass.data[DOMAIN][FEATURES]
    ariston_water_heater = AristonWaterHeater(api, device, features)
    await ariston_water_heater.async_update()
    async_add_entities([ariston_water_heater])
    return


class AristonWaterHeater(WaterHeaterEntity):
    """Ariston Water Heater Device."""

    def __init__(self, api: AristonAPI, device, features):
        """Initialize the thermostat."""
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

    async def async_update(self) -> None:
        data = await self.api.update_device(self.gw_id, 0, self.features, self.location)
        for item in data["items"]:
            if item["id"] == "DhwTemp":
                self.dhw_temp = item
            if item["id"] == "DhwMode":
                self.dhw_mode = item
