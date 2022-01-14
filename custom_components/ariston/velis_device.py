"""Device class for Ariston module."""
from __future__ import annotations

import logging

from .device import AristonDevice
from .ariston import (
    CustomDeviceFeatures,
    DeviceAttribute,
    VelisDeviceProperties,
    MedDeviceSettings,
    VelisPlantMode,
)

_LOGGER = logging.getLogger(__name__)


class AristonVelisDevice(AristonDevice):
    """Class representing a physical device, it's state and properties."""

    async def async_update_state(self) -> None:
        """Update the device states from the cloud"""
        self.data = await self.api.async_get_med_plant_data(
            self.attributes.get(DeviceAttribute.GW)
        )

    async def async_get_features(self) -> None:
        """Get device features wrapper"""
        await super().async_get_features()
        self.features[CustomDeviceFeatures.HAS_CH] = False
        self.features[CustomDeviceFeatures.HAS_DHW] = True

    async def async_update_settings(self) -> None:
        """Get device settings wrapper"""
        self.plant_settings = await self.api.async_get_med_plant_settings(
            self.attributes.get(DeviceAttribute.GW)
        )

    def get_water_heater_current_temperature(self) -> float:
        """Get water heater current temperature"""
        return self.data.get(VelisDeviceProperties.TEMP)

    def get_water_heater_minimum_temperature(self) -> float:
        """Get water heater minimum temperature"""
        return self.plant_settings.get(
            MedDeviceSettings.MED_MAX_SETPOINT_TEMPERATURE_MIN
        )

    def get_water_heater_maximum_temperature(self) -> float:
        """Get water heater maximum temperature"""
        return self.plant_settings.get(
            MedDeviceSettings.MED_MAX_SETPOINT_TEMPERATURE_MAX
        )

    def get_water_heater_target_temperature(self) -> float:
        """Get water heater target temperature"""
        return self.data.get(VelisDeviceProperties.REQ_TEMP)

    def get_water_heater_temperature_step(self) -> str:
        """Get water heater temperature step"""
        return 1

    def get_water_heater_temperature_decimals(self) -> int:
        """Get water heater temperature decimals"""
        return 0

    def get_water_heater_temperature_unit(self) -> str:
        """Get water heater temperature unit"""
        return "°C"

    def get_water_heater_mode_opertation_texts(self) -> list:
        """Get water heater operation mode texts"""
        return [flag.name for flag in VelisPlantMode]

    def get_water_heater_mode_options(self) -> list:
        """Get water heater operation options"""
        return [flag.value for flag in VelisPlantMode]

    def get_water_heater_mode_value(self) -> int:
        """Get water heater mode value"""
        return self.data.get(VelisDeviceProperties.MODE)

    def get_water_heater_eco_value(self) -> int:
        """Get water heater eco value"""
        return self.data.get(VelisDeviceProperties.ECO)

    async def async_set_water_heater_temperature(self, temperature: float):
        """Set water heater temperature"""
        await self.api.async_set_velis_temperature(
            self.attributes.get(DeviceAttribute.GW),
            self.data.get(VelisDeviceProperties.ECO),
            temperature,
        )
        self.data[VelisDeviceProperties.REQ_TEMP] = temperature

    async def async_set_eco_mode(self, eco_mode: bool):
        """Set water heater eco_mode"""
        await self.api.async_set_velis_temperature(
            self.attributes.get(DeviceAttribute.GW),
            eco_mode,
            self.data.get(VelisDeviceProperties.REQ_TEMP),
        )
        self.data[VelisDeviceProperties.ECO] = eco_mode

    async def async_set_water_heater_operation_mode(self, operation_mode):
        """Set water heater operation mode"""
        await self.api.async_set_velis_mode(
            self.attributes.get(DeviceAttribute.GW), VelisPlantMode[operation_mode]
        )
        self.data[VelisDeviceProperties.MODE] = VelisPlantMode[operation_mode].value
