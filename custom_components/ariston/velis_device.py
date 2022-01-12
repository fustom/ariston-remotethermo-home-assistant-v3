"""Device class for Ariston module."""
from __future__ import annotations

import logging

from .device import AristonDevice
from .ariston import (
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

    async def async_update_settings(self) -> None:
        self.plant_settings = await self.api.async_get_med_plant_settings(
            self.attributes.get(DeviceAttribute.GW)
        )

    def get_water_heater_current_temperature(self) -> float:
        return self.data.get(VelisDeviceProperties.TEMP)

    def get_water_heater_minimum_temperature(self) -> float:
        return self.plant_settings.get(
            MedDeviceSettings.MED_MAX_SETPOINT_TEMPERATURE_MIN
        )

    def get_water_heater_maximum_temperature(self) -> float:
        return self.plant_settings.get(
            MedDeviceSettings.MED_MAX_SETPOINT_TEMPERATURE_MAX
        )

    def get_water_heater_target_temperature(self) -> float:
        return self.data.get(VelisDeviceProperties.REQ_TEMP)

    def get_water_heater_temperature_step(self) -> str:
        return 1

    def get_water_heater_decimals(self) -> int:
        return 0

    def get_water_heater_temperature_unit(self) -> str:
        return "°C"

    def get_water_heater_mode_opertation_texts(self) -> list:
        return [flag.name for flag in VelisPlantMode]

    def get_water_heater_mode_options(self) -> list:
        return [flag.value for flag in VelisPlantMode]

    def get_water_heater_mode_value(self) -> int:
        return self.data.get(VelisDeviceProperties.MODE)

    async def async_set_water_heater_temperature(self, temperature: float):
        await self.api.async_set_velis_temperature(
            self.attributes.get(DeviceAttribute.GW),
            self.data.get(VelisDeviceProperties.ECO),
            temperature,
        )
        self.data[VelisDeviceProperties.REQ_TEMP] = temperature

    async def async_set_water_heater_operation_mode(self, operation_mode):
        await self.api.async_set_velis_mode(
            self.attributes.get(DeviceAttribute.GW), VelisPlantMode(operation_mode)
        )
        self.data[VelisDeviceProperties.MODE] = VelisPlantMode(operation_mode)
