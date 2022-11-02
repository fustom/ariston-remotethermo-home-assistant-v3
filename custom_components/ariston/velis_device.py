"""Velis device class for Ariston module."""
from __future__ import annotations

import logging

from ast import Raise
from abc import ABC, abstractmethod

from .device import AristonDevice
from .ariston import (
    CustomDeviceFeatures,
    DeviceAttribute,
    DeviceFeatures,
    VelisDeviceProperties,
    MedDeviceSettings,
)

_LOGGER = logging.getLogger(__name__)


class AristonVelisDevice(AristonDevice, ABC):
    """Class representing a physical device, it's state and properties."""

    async def async_get_features(self) -> None:
        """Get device features wrapper"""
        await super().async_get_features()
        self.features[CustomDeviceFeatures.HAS_DHW] = True
        self.features[DeviceFeatures.DHW_MODE_CHANGEABLE] = True
        await self.async_update_settings()

    @abstractmethod
    async def async_update_settings(self) -> None:
        """Get device settings wrapper"""
        Raise(NotImplementedError)

    @abstractmethod
    def get_water_anti_leg_value(self) -> bool:
        """Get water heater anti-legionella value"""
        Raise(NotImplementedError)

    @abstractmethod
    def get_water_heater_maximum_setpoint_temperature_minimum(self) -> float:
        """Get water heater maximum setpoint temperature minimum"""
        Raise(NotImplementedError)

    @abstractmethod
    def get_water_heater_maximum_setpoint_temperature_maximum(self) -> float:
        """Get water heater maximum setpoint maximum temperature"""
        Raise(NotImplementedError)

    @abstractmethod
    def get_water_heater_maximum_setpoint_temperature(self) -> float:
        """Get water heater maximum setpoint temperature value"""
        Raise(NotImplementedError)

    def get_water_heater_current_temperature(self) -> float:
        """Get water heater current temperature"""
        return self.data.get(VelisDeviceProperties.TEMP)

    def get_water_heater_minimum_temperature(self) -> float:
        """Get water heater minimum temperature"""
        return 40.0

    def get_water_heater_maximum_temperature(self) -> float:
        """Get water heater maximum temperature"""
        return self.get_water_heater_maximum_setpoint_temperature()

    def get_water_heater_target_temperature(self) -> float:
        """Get water heater target temperature"""
        return self.data.get(VelisDeviceProperties.REQ_TEMP)

    def get_water_heater_temperature_step(self) -> str:
        """Get water heater temperature step"""
        return 1

    @staticmethod
    def get_water_heater_temperature_decimals() -> int:
        """Get water heater temperature decimals"""
        return 0

    @staticmethod
    def get_water_heater_temperature_unit() -> str:
        """Get water heater temperature unit"""
        return "°C"

    def get_water_heater_mode_value(self) -> int:
        """Get water heater mode value"""
        return self.data.get(VelisDeviceProperties.MODE)

    def get_av_shw_value(self) -> int:
        """Get average showers value"""
        return self.data.get(VelisDeviceProperties.AV_SHW)

    def get_water_heater_power_value(self) -> bool:
        """Get water heater power value"""
        return self.data.get(VelisDeviceProperties.ON)

    def get_is_heating(self) -> bool:
        """Get is the water heater heating"""
        return self.data.get(VelisDeviceProperties.HEAT_REQ)

    @staticmethod
    def get_empty_unit() -> int:
        """Get empty unit"""
        return ""

    @abstractmethod
    async def async_set_antilegionella(self, anti_leg: bool):
        """Set water heater anti-legionella"""
        Raise(NotImplementedError)

    @abstractmethod
    async def async_set_water_heater_temperature(self, temperature: float):
        """Set water heater temperature"""
        Raise(NotImplementedError)

    @abstractmethod
    async def async_set_power(self, power: bool):
        """Set water heater power"""
        Raise(NotImplementedError)

    async def async_set_max_setpoint_temp(self, max_setpoint_temp: float):
        """Set water heater anti-legionella"""
        await self.api.async_set_velis_plant_setting(
            self.attributes.get(DeviceAttribute.GW),
            MedDeviceSettings.MED_MAX_SETPOINT_TEMPERATURE,
            max_setpoint_temp,
            self.plant_settings[MedDeviceSettings.MED_MAX_SETPOINT_TEMPERATURE],
        )
        self.plant_settings[
            MedDeviceSettings.MED_MAX_SETPOINT_TEMPERATURE
        ] = max_setpoint_temp
