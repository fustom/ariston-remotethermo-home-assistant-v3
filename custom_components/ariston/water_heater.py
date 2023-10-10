"""Support for Ariston water heaters."""
from __future__ import annotations

import logging

from .entity import AristonEntity
from .const import (
    ARISTON_WATER_HEATER_TYPES,
    DOMAIN,
    AristonWaterHeaterEntityDescription,
)
from .coordinator import DeviceDataUpdateCoordinator

from ariston.const import SystemType
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.water_heater import (
    WaterHeaterEntityFeature,
    WaterHeaterEntity,
)
from homeassistant.const import (
    ATTR_TEMPERATURE,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Set up the Ariston water heater device from config entry."""
    ariston_water_heaters: list[AristonWaterHeater] = []
    for description in ARISTON_WATER_HEATER_TYPES:
        coordinator: DeviceDataUpdateCoordinator = hass.data[DOMAIN][entry.unique_id][
            description.coordinator
        ]

        if (
            coordinator
            and coordinator.device
            and coordinator.device.are_device_features_available(
                description.device_features,
                description.system_types,
                description.whe_types,
            )
        ):
            ariston_water_heaters.append(AristonWaterHeater(coordinator, description))

    async_add_entities(ariston_water_heaters)


class AristonWaterHeater(AristonEntity, WaterHeaterEntity):
    """Ariston Water Heater Device."""

    def __init__(
        self,
        coordinator: DeviceDataUpdateCoordinator,
        description: AristonWaterHeaterEntityDescription,
    ) -> None:
        """Initialize the water heater."""
        super().__init__(coordinator, description)

    @property
    def name(self) -> str:
        """Return the name of the device."""
        return self.device.name

    @property
    def unique_id(self) -> str:
        """Return a unique id for the device."""
        return f"{self.device.gateway}-water_heater"

    @property
    def icon(self):
        return "mdi:water-pump"

    @property
    def current_temperature(self):
        """Return the temperature"""
        return self.device.water_heater_current_temperature

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        return self.device.water_heater_minimum_temperature

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self.device.water_heater_target_temperature

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        return self.device.water_heater_maximum_temperature

    @property
    def precision(self) -> float:
        """Return the precision of temperature for the device."""
        return 1 / 10**self.device.water_heater_temperature_decimals

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return self.device.water_heater_temperature_unit

    @property
    def supported_features(self) -> int:
        """Return the supported features for this device integration."""
        features = WaterHeaterEntityFeature.TARGET_TEMPERATURE
        if self.device.dhw_mode_changeable:
            features |= WaterHeaterEntityFeature.OPERATION_MODE
        if (
            self.device.system_type == SystemType.VELIS
            and "ON_OFF"
            in WaterHeaterEntityFeature.__members__  # check entity feature for backward compatibility
        ):
            features |= WaterHeaterEntityFeature.ON_OFF
        return features

    @property
    def operation_list(self):
        """List of available operation modes."""
        return self.device.water_heater_mode_operation_texts

    @property
    def current_operation(self):
        """Return current operation"""
        return self.device.water_heater_current_mode_text

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

        await self.device.async_set_water_heater_temperature(temperature)
        self.async_write_ha_state()

    async def async_set_operation_mode(self, operation_mode):
        """Set operation mode."""
        await self.device.async_set_water_heater_operation_mode(operation_mode)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the water heater off."""
        await self.device.async_set_power(False)

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the water heater on."""
        await self.device.async_set_power(True)
