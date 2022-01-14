"""Device class for Ariston module."""
from __future__ import annotations

import logging

from datetime import date

from .device import AristonDevice
from .ariston import (
    CustomDeviceFeatures,
    DeviceAttribute,
    DeviceFeatures,
    DeviceProperties,
    PropertyType,
    ThermostatProperties,
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

    async def async_get_features(self) -> None:
        """Get device features wrapper"""
        await super().async_get_features()
        self.features[CustomDeviceFeatures.HAS_CH] = True
        self.features[CustomDeviceFeatures.HAS_DHW] = self.features.get(
            DeviceFeatures.HAS_BOILER
        )

    def get_water_heater_current_temperature(self) -> float:
        """Get water heater current temperature"""
        return self.get_item_by_id(DeviceProperties.DHW_TEMP, PropertyType.VALUE)

    def get_water_heater_minimum_temperature(self) -> float:
        """Get water heater minimum temperature"""
        return self.get_item_by_id(DeviceProperties.DHW_TEMP, PropertyType.MIN)

    def get_water_heater_maximum_temperature(self) -> float:
        """Get water heater maximum temperature"""
        return self.get_item_by_id(DeviceProperties.DHW_TEMP, PropertyType.MAX)

    def get_water_heater_target_temperature(self) -> float:
        """Get water heater target temperature"""
        return self.get_item_by_id(DeviceProperties.DHW_TEMP, PropertyType.VALUE)

    def get_water_heater_temperature_decimals(self) -> int:
        """Get water heater temperature decimals"""
        return self.get_item_by_id(DeviceProperties.DHW_TEMP, PropertyType.DECIMALS)

    def get_water_heater_temperature_unit(self) -> str:
        """Get water heater temperature unit"""
        return self.get_item_by_id(DeviceProperties.DHW_TEMP, PropertyType.UNIT)

    def get_water_heater_temperature_step(self) -> str:
        """Get water heater temperature step"""
        return self.get_item_by_id(DeviceProperties.DHW_TEMP, PropertyType.STEP)

    def get_water_heater_mode_opertation_texts(self) -> list:
        """Get water heater operation mode texts"""
        return self.get_item_by_id(DeviceProperties.DHW_MODE, PropertyType.OPT_TEXTS)

    def get_water_heater_mode_options(self) -> list:
        """Get water heater operation options"""
        return self.get_item_by_id(DeviceProperties.DHW_MODE, PropertyType.OPTIONS)

    def get_water_heater_mode_value(self) -> int:
        """Get water heater mode value"""
        return self.get_item_by_id(DeviceProperties.DHW_MODE, PropertyType.VALUE)

    def get_zone_heat_request_value(self, zone_number: int) -> str:
        """Get zone heat request value"""
        return self.get_item_by_id(
            ThermostatProperties.ZONE_HEAT_REQUEST, PropertyType.VALUE, zone_number
        )

    def get_zone_economy_temp_value(self, zone_number: int) -> str:
        """Get zone economy temperature value"""
        return self.get_item_by_id(
            ThermostatProperties.ZONE_ECONOMY_TEMP, PropertyType.VALUE, zone_number
        )

    def get_zone_number(self, zone_number: int) -> str:
        """Get zone number"""
        return zone_number

    def get_holiday_expires_on(self) -> str:
        """Get holiday expires on"""
        return self.get_item_by_id(DeviceProperties.HOLIDAY, PropertyType.EXPIRES_ON)

    def get_automatic_thermoregulation(self) -> str:
        """Get automatic thermoregulation"""
        return self.get_item_by_id(
            DeviceProperties.AUTOMATIC_THERMOREGULATION, PropertyType.VALUE
        )

    def get_item_by_id(
        self, item_id: DeviceProperties, item_value: PropertyType, zone_number: int = 0
    ):
        """Get item attribute from data"""
        return next(
            item.get(item_value)
            for item in self.data.get("items")
            if item.get("id") == item_id and item.get(PropertyType.ZONE) == zone_number
        )

    async def async_set_water_heater_temperature(self, temperature: float):
        """Set water heater temperature"""
        await self.async_set_item_by_id(DeviceProperties.DHW_TEMP, temperature)

    async def async_set_water_heater_operation_mode(self, operation_mode):
        """Set water heater operation mode"""
        await self.async_set_item_by_id(
            DeviceProperties.DHW_MODE,
            self.get_item_by_id(
                DeviceProperties.DHW_MODE, PropertyType.OPT_TEXTS
            ).index(operation_mode),
        )

    async def async_set_automatic_thermoregulation(self, auto_thermo: bool):
        """Set automatic thermoregulation"""
        await self.async_set_item_by_id(
            DeviceProperties.AUTOMATIC_THERMOREGULATION, 1.0 if auto_thermo else 0.0
        )

    async def async_set_item_by_id(
        self,
        item_id: DeviceProperties or ThermostatProperties,
        value: float,
        zone_number: int = 0,
    ):
        """Set item attribute on device"""
        current_value = self.get_item_by_id(item_id, PropertyType.VALUE, zone_number)
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
