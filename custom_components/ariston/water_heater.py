"""Support for Ariston water heaters."""
from __future__ import annotations

import logging

from .const import DOMAIN
from .coordinator import DeviceDataUpdateCoordinator

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.water_heater import (
    SUPPORT_OPERATION_MODE,
    SUPPORT_TARGET_TEMPERATURE,
    WaterHeaterEntity,
)
from homeassistant.const import (
    ATTR_TEMPERATURE,
)
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Set up the Ariston water heater device from config entry."""
    coordinator: DeviceDataUpdateCoordinator = hass.data[DOMAIN][entry.unique_id]
    async_add_entities([AristonWaterHeater(coordinator)])
    return


class AristonWaterHeater(CoordinatorEntity, WaterHeaterEntity):
    """Ariston Water Heater Device."""

    def __init__(
        self,
        coordinator: DeviceDataUpdateCoordinator,
    ) -> None:
        """Initialize the thermostat."""

        # Pass coordinator to CoordinatorEntity.
        super().__init__(coordinator)

        self.coordinator = coordinator

    @property
    def name(self) -> str:
        """Return the name of the device."""
        return self.coordinator.device.plant_name

    @property
    def unique_id(self) -> str:
        """Return a unique id for the device."""
        return f"{self.coordinator.device.gw_id}-water_heater"

    @property
    def icon(self):
        return "mdi:water-pump"

    @property
    def current_temperature(self):
        """Return the temperature"""
        return self.coordinator.device.dhw_temp

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        return self.coordinator.device.dhw_temp_min

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self.coordinator.device.dhw_temp

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        return self.coordinator.device.dhw_temp_max

    @property
    def target_temperature_step(self):
        """Return the target temperature step support by the device."""
        return self.coordinator.device.dhw_temp_step

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return self.coordinator.device.dhw_temp_unit

    @property
    def supported_features(self) -> int:
        """Return the supported features for this device integration."""
        if self.coordinator.device.features.dhw_mode_changeable:
            return SUPPORT_TARGET_TEMPERATURE | SUPPORT_OPERATION_MODE
        return SUPPORT_TARGET_TEMPERATURE

    @property
    def operation_list(self):
        """List of available operation modes."""
        return self.coordinator.device.dhw_mode_texts

    @property
    def current_operation(self):
        """Return current operation"""
        res = self.coordinator.device.dhw_modes.index(self.coordinator.device.dhw_mode)
        return self.coordinator.device.dhw_mode_texts[res]

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

        await self.coordinator.async_set_dhwtemp(temperature)
        self.async_write_ha_state()

    async def async_set_operation_mode(self, operation_mode):
        """Set operation mode."""
        _LOGGER.error(
            "Set operation mode is currently not supported. I need device to grab the api calls"
        )
        return
