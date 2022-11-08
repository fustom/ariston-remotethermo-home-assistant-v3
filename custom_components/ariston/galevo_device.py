"""Galevo device class for Ariston module."""
from __future__ import annotations

import logging

from datetime import date
from typing import Any

from .device import AristonDevice
from .ariston import (
    CustomDeviceFeatures,
    DeviceAttribute,
    DeviceFeatures,
    DeviceProperties,
    PlantMode,
    PropertyType,
    ThermostatProperties,
    ZoneMode,
)

_LOGGER = logging.getLogger(__name__)


class AristonGalevoDevice(AristonDevice):
    """Class representing a physical device, it's state and properties."""

    async def async_update_state(self) -> None:
        """Update the device states from the cloud"""
        self.data = await self.api.async_get_properties(
            self.attributes.get(DeviceAttribute.GW),
            self.features,
            self.location,
            self.umsys,
        )

        if self.custom_features.get(CustomDeviceFeatures.HAS_OUTSIDE_TEMP) is None:
            temp = self._get_item_by_id(
                DeviceProperties.OUTSIDE_TEMP, PropertyType.VALUE
            )
            max_temp = self._get_item_by_id(
                DeviceProperties.OUTSIDE_TEMP, PropertyType.MAX
            )
            self.custom_features[CustomDeviceFeatures.HAS_OUTSIDE_TEMP] = (
                temp != max_temp
            )

        if self.custom_features.get(DeviceProperties.DHW_STORAGE_TEMPERATURE) is None:
            storage_temp = self._get_item_by_id(
                DeviceProperties.DHW_STORAGE_TEMPERATURE, PropertyType.VALUE
            )
            self.custom_features[DeviceProperties.DHW_STORAGE_TEMPERATURE] = (
                storage_temp is not None
            )

    async def async_get_features(self) -> None:
        """Get device features wrapper"""
        await super().async_get_features()
        self.custom_features[CustomDeviceFeatures.HAS_DHW] = self.features.get(
            DeviceFeatures.HAS_BOILER
        )

    def get_water_heater_current_temperature(self) -> float:
        """Get water heater current temperature"""
        if self.custom_features[DeviceProperties.DHW_STORAGE_TEMPERATURE]:
            return self._get_item_by_id(
                DeviceProperties.DHW_STORAGE_TEMPERATURE, PropertyType.VALUE
            )
        return self._get_item_by_id(DeviceProperties.DHW_TEMP, PropertyType.VALUE)

    def get_water_heater_minimum_temperature(self) -> float:
        """Get water heater minimum temperature"""
        return self._get_item_by_id(DeviceProperties.DHW_TEMP, PropertyType.MIN)

    def get_water_heater_maximum_temperature(self) -> float:
        """Get water heater maximum temperature"""
        return self._get_item_by_id(DeviceProperties.DHW_TEMP, PropertyType.MAX)

    def get_water_heater_target_temperature(self) -> float:
        """Get water heater target temperature"""
        return self._get_item_by_id(DeviceProperties.DHW_TEMP, PropertyType.VALUE)

    def get_water_heater_temperature_decimals(self) -> int:
        """Get water heater temperature decimals"""
        return self._get_item_by_id(DeviceProperties.DHW_TEMP, PropertyType.DECIMALS)

    def get_water_heater_temperature_unit(self) -> str:
        """Get water heater temperature unit"""
        return self._get_item_by_id(DeviceProperties.DHW_TEMP, PropertyType.UNIT)

    def get_water_heater_temperature_step(self) -> str:
        """Get water heater temperature step"""
        return self._get_item_by_id(DeviceProperties.DHW_TEMP, PropertyType.STEP)

    def get_water_heater_mode_opertation_texts(self) -> list[str]:
        """Get water heater operation mode texts"""
        return self._get_item_by_id(DeviceProperties.DHW_MODE, PropertyType.OPT_TEXTS)

    def get_water_heater_mode_options(self) -> list[int]:
        """Get water heater operation options"""
        return self._get_item_by_id(DeviceProperties.DHW_MODE, PropertyType.OPTIONS)

    def get_water_heater_mode_value(self) -> int:
        """Get water heater mode value"""
        return self._get_item_by_id(DeviceProperties.DHW_MODE, PropertyType.VALUE)

    def get_zone_heat_request_value(self, zone_number: int) -> str:
        """Get zone heat request value"""
        return self._get_item_by_id(
            ThermostatProperties.ZONE_HEAT_REQUEST, PropertyType.VALUE, zone_number
        )

    def get_zone_economy_temp_value(self, zone_number: int) -> str:
        """Get zone economy temperature value"""
        return self._get_item_by_id(
            ThermostatProperties.ZONE_ECONOMY_TEMP, PropertyType.VALUE, zone_number
        )

    @staticmethod
    def get_zone_number(zone_number: int) -> str:
        """Get zone number"""
        return zone_number

    def get_holiday_expires_on(self) -> str:
        """Get holiday expires on"""
        return self._get_item_by_id(DeviceProperties.HOLIDAY, PropertyType.EXPIRES_ON)

    def get_automatic_thermoregulation(self) -> str:
        """Get automatic thermoregulation"""
        return self._get_item_by_id(
            DeviceProperties.AUTOMATIC_THERMOREGULATION, PropertyType.VALUE
        )

    def get_heating_circuit_pressure_value(self) -> str:
        """Get heating circuit pressure value"""
        return self._get_item_by_id(
            DeviceProperties.HEATING_CIRCUIT_PRESSURE, PropertyType.VALUE
        )

    def get_heating_circuit_pressure_unit(self) -> str:
        """Get heating circuit pressure unit"""
        return self._get_item_by_id(
            DeviceProperties.HEATING_CIRCUIT_PRESSURE, PropertyType.UNIT
        )

    def get_ch_flow_setpoint_temp_value(self) -> str:
        """Get central heating flow setpoint temperature value"""
        return self._get_item_by_id(
            DeviceProperties.CH_FLOW_SETPOINT_TEMP, PropertyType.VALUE
        )

    def get_ch_flow_temp_value(self) -> str:
        """Get central heating flow temperature value"""
        return self._get_item_by_id(DeviceProperties.CH_FLOW_TEMP, PropertyType.VALUE)

    def get_outside_temp_value(self) -> str:
        """Get outside temperature value"""
        return self._get_item_by_id(DeviceProperties.OUTSIDE_TEMP, PropertyType.VALUE)

    def get_outside_temp_unit(self) -> str:
        """Get outside temperature unit"""
        return self._get_item_by_id(DeviceProperties.OUTSIDE_TEMP, PropertyType.UNIT)

    def get_ch_flow_setpoint_temp_unit(self) -> str:
        """Get central heating flow setpoint temperature unit"""
        return self._get_item_by_id(
            DeviceProperties.CH_FLOW_SETPOINT_TEMP, PropertyType.UNIT
        )

    def get_ch_flow_temp_unit(self) -> str:
        """Get central heating flow temperature unit"""
        return self._get_item_by_id(DeviceProperties.CH_FLOW_TEMP, PropertyType.UNIT)

    def get_is_flame_on_value(self) -> bool:
        """Get is flame on value"""
        return self._get_item_by_id(DeviceProperties.IS_FLAME_ON, PropertyType.VALUE)

    def get_holiday_mode_value(self) -> bool:
        """Get holiday mode on value"""
        return self._get_item_by_id(DeviceProperties.HOLIDAY, PropertyType.VALUE)

    def get_zone_mode(self, zone) -> ZoneMode:
        """Get zone mode on value"""
        return ZoneMode(
            self._get_item_by_id(
                ThermostatProperties.ZONE_MODE, PropertyType.VALUE, zone
            )
        )

    def get_zone_mode_options(self, zone) -> list[int]:
        """Get zone mode on options"""
        return self._get_item_by_id(
            ThermostatProperties.ZONE_MODE, PropertyType.OPTIONS, zone
        )

    def get_plant_mode(self) -> PlantMode:
        """Get plant mode on value"""
        return PlantMode(
            self._get_item_by_id(DeviceProperties.PLANT_MODE, PropertyType.VALUE)
        )

    def get_plant_mode_options(self) -> list[int]:
        """Get plant mode on options"""
        return self._get_item_by_id(DeviceProperties.PLANT_MODE, PropertyType.OPTIONS)

    def get_plant_mode_opt_texts(self) -> list[str]:
        """Get plant mode on option texts"""
        return self._get_item_by_id(DeviceProperties.PLANT_MODE, PropertyType.OPT_TEXTS)

    def get_plant_mode_text(self) -> str:
        """Get plant mode on option texts"""
        index = self.get_plant_mode_options().index(self.get_plant_mode())
        return self._get_item_by_id(
            DeviceProperties.PLANT_MODE, PropertyType.OPT_TEXTS
        )[index]

    def get_measured_temp_unit(self, zone) -> str:
        """Get zone measured temp unit"""
        return self._get_item_by_id(
            ThermostatProperties.ZONE_MEASURED_TEMP, PropertyType.UNIT, zone
        )

    def get_measured_temp_decimals(self, zone) -> int:
        """Get zone measured temp decimals"""
        return self._get_item_by_id(
            ThermostatProperties.ZONE_MEASURED_TEMP, PropertyType.DECIMALS, zone
        )

    def get_measured_temp_value(self, zone) -> int:
        """Get zone measured temp value"""
        return self._get_item_by_id(
            ThermostatProperties.ZONE_MEASURED_TEMP, PropertyType.VALUE, zone
        )

    def get_comfort_temp_min(self, zone) -> int:
        """Get zone comfort temp min"""
        return self._get_item_by_id(
            ThermostatProperties.ZONE_COMFORT_TEMP, PropertyType.MIN, zone
        )

    def get_comfort_temp_max(self, zone) -> int:
        """Get zone comfort temp max"""
        return self._get_item_by_id(
            ThermostatProperties.ZONE_COMFORT_TEMP, PropertyType.MAX, zone
        )

    def get_comfort_temp_step(self, zone) -> int:
        """Get zone comfort temp step"""
        return self._get_item_by_id(
            ThermostatProperties.ZONE_COMFORT_TEMP, PropertyType.STEP, zone
        )

    def get_comfort_temp_value(self, zone) -> int:
        """Get zone comfort temp value"""
        return self._get_item_by_id(
            ThermostatProperties.ZONE_COMFORT_TEMP, PropertyType.VALUE, zone
        )

    def _get_item_by_id(
        self, item_id: DeviceProperties, item_value: PropertyType, zone_number: int = 0
    ):
        """Get item attribute from data"""
        return next(
            (
                item.get(item_value)
                for item in self.data.get("items")
                if item.get("id") == item_id
                and item.get(PropertyType.ZONE) == zone_number
            ),
            None,
        )

    async def async_get_consumptions_sequences(self) -> dict[str, Any]:
        """Get consumption sequence"""
        self.consumptions_sequences = await self.api.async_get_consumptions_sequences(
            self.attributes.get(DeviceAttribute.GW),
            f"Ch{'%2CDhw' if self.custom_features.get(CustomDeviceFeatures.HAS_DHW) else ''}",
        )

    async def async_set_water_heater_temperature(self, temperature: float):
        """Set water heater temperature"""
        await self.async_set_item_by_id(DeviceProperties.DHW_TEMP, temperature)

    async def async_set_water_heater_operation_mode(self, operation_mode):
        """Set water heater operation mode"""
        await self.async_set_item_by_id(
            DeviceProperties.DHW_MODE,
            self._get_item_by_id(
                DeviceProperties.DHW_MODE, PropertyType.OPT_TEXTS
            ).index(operation_mode),
        )

    async def async_set_automatic_thermoregulation(self, auto_thermo: bool):
        """Set automatic thermoregulation"""
        await self.async_set_item_by_id(
            DeviceProperties.AUTOMATIC_THERMOREGULATION, 1.0 if auto_thermo else 0.0
        )

    async def async_set_plant_mode(self, plant_mode: PlantMode):
        """Set plant mode"""
        await self.async_set_item_by_id(DeviceProperties.PLANT_MODE, plant_mode)

    async def async_set_zone_mode(self, zone_mode: ZoneMode, zone):
        """Set zone mode"""
        await self.async_set_item_by_id(ThermostatProperties.ZONE_MODE, zone_mode, zone)

    async def async_set_comfort_temp(self, temp: float, zone):
        """Set comfort temp"""
        await self.async_set_item_by_id(
            ThermostatProperties.ZONE_COMFORT_TEMP, temp, zone
        )

    async def async_set_item_by_id(
        self,
        item_id: DeviceProperties or ThermostatProperties,
        value: float,
        zone_number: int = 0,
    ):
        """Set item attribute on device"""
        current_value = self._get_item_by_id(item_id, PropertyType.VALUE, zone_number)
        await self.api.async_set_property(
            self.attributes.get(DeviceAttribute.GW),
            zone_number,
            self.features,
            item_id,
            value,
            current_value,
            self.umsys,
        )
        for item in self.data.get("items"):
            if item.get("id") == item_id and item.get(PropertyType.ZONE) == zone_number:
                item[PropertyType.VALUE] = value
                break

    async def async_set_holiday(self, holiday_end: date):
        """Set holiday on device"""
        holiday_end_date = (
            None if holiday_end is None else holiday_end.strftime("%Y-%m-%dT00:00:00")
        )

        await self.api.async_set_holiday(
            self.attributes.get(DeviceAttribute.GW),
            holiday_end_date,
        )

        for item in self.data.get("items"):
            if item.get("id") == DeviceProperties.HOLIDAY:
                item[PropertyType.VALUE] = False if holiday_end_date is None else True
                item[PropertyType.EXPIRES_ON] = (
                    None if holiday_end_date is None else holiday_end_date
                )
                break
