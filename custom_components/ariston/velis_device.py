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
        await self.async_update_settings()

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

    @staticmethod
    def get_water_heater_mode_opertation_texts() -> list:
        """Get water heater operation mode texts"""
        return [flag.name for flag in VelisPlantMode]

    @staticmethod
    def get_water_heater_mode_options() -> list:
        """Get water heater operation options"""
        return [flag.value for flag in VelisPlantMode]

    def get_water_heater_mode_value(self) -> int:
        """Get water heater mode value"""
        return self.data.get(VelisDeviceProperties.MODE)

    def get_water_heater_eco_value(self) -> int:
        """Get water heater eco value"""
        return self.data.get(VelisDeviceProperties.ECO)

    def get_av_shw_value(self) -> int:
        """Get average showers value"""
        return self.data.get(VelisDeviceProperties.AV_SHW)

    def get_water_heater_power_value(self) -> bool:
        """Get water heater power value"""
        return self.data.get(VelisDeviceProperties.ON)

    def get_rm_tm_value(self) -> str:
        """Get remaining time value"""
        return self.data.get(VelisDeviceProperties.RM_TM)

    def get_is_heating(self) -> bool:
        """Get is the water heater heating"""
        return self.data.get(VelisDeviceProperties.HEAT_REQ)

    def get_water_anti_leg_value(self) -> bool:
        """Get water heater anti-legionella value"""
        return self.plant_settings.get(MedDeviceSettings.MED_ANTILEGIONELLA_ON_OFF)

    def get_water_heater_maximum_setpoint_temperature_minimum(self) -> float:
        """Get water heater maximum setpoint temperature minimum"""
        return self.plant_settings.get(
            MedDeviceSettings.MED_MAX_SETPOINT_TEMPERATURE_MIN
        )

    def get_water_heater_maximum_setpoint_temperature_maximum(self) -> float:
        """Get water heater maximum setpoint maximum temperature"""
        return self.plant_settings.get(
            MedDeviceSettings.MED_MAX_SETPOINT_TEMPERATURE_MAX
        )

    def get_water_heater_maximum_setpoint_temperature(self) -> float:
        """Get water heater maximum setpoint temperature value"""
        return self.plant_settings.get(MedDeviceSettings.MED_MAX_SETPOINT_TEMPERATURE)

    @staticmethod
    def get_empty_unit() -> int:
        """Get empty unit"""
        return ""

    def get_electric_consumption_for_water_last_two_hours(self) -> int:
        """Get electric consumption for water last two hours"""
        return self.consumptions_sequences[0]["v"][-1]

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

    async def async_set_power(self, power: bool):
        """Set water heater power"""
        await self.api.async_set_velis_power(
            self.attributes.get(DeviceAttribute.GW), power
        )
        self.data[VelisDeviceProperties.ON] = power

    async def async_set_antilegionella(self, anti_leg: bool):
        """Set water heater anti-legionella"""
        await self.api.async_set_velis_plant_setting(
            self.attributes.get(DeviceAttribute.GW),
            MedDeviceSettings.MED_ANTILEGIONELLA_ON_OFF,
            1.0 if anti_leg else 0.0,
            1.0
            if self.plant_settings[MedDeviceSettings.MED_ANTILEGIONELLA_ON_OFF]
            else 0.0,
        )
        self.plant_settings[MedDeviceSettings.MED_ANTILEGIONELLA_ON_OFF] = anti_leg

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
