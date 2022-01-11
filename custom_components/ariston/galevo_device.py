"""Device class for Ariston module."""
from __future__ import annotations

import logging

from datetime import date

from .device import AristonDevice
from .ariston import (
    DeviceAttribute,
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

    def get_water_heater_current_temperature(self) -> float:
        return self.get_item_by_id(DeviceProperties.DHW_TEMP, PropertyType.VALUE)

    def get_water_heater_minimum_temperature(self) -> float:
        return self.get_item_by_id(DeviceProperties.DHW_TEMP, PropertyType.MIN)

    def get_water_heater_maximum_temperature(self) -> float:
        return self.get_item_by_id(DeviceProperties.DHW_TEMP, PropertyType.MAX)

    def get_water_heater_target_temperature(self) -> float:
        return self.get_item_by_id(DeviceProperties.DHW_TEMP, PropertyType.VALUE)

    def get_water_heater_decimals(self) -> int:
        return self.get_item_by_id(DeviceProperties.DHW_TEMP, PropertyType.DECIMALS)

    def get_water_heater_temperature_unit(self) -> str:
        return self.get_item_by_id(DeviceProperties.DHW_TEMP, PropertyType.UNIT)

    def get_water_heater_mode_opertation_texts(self) -> list:
        return self.get_item_by_id(DeviceProperties.DHW_MODE, PropertyType.OPT_TEXTS)

    def get_water_heater_mode_options(self) -> list:
        return self.get_item_by_id(DeviceProperties.DHW_MODE, PropertyType.OPTIONS)

    def get_water_heater_mode_value(self) -> int:
        return self.get_item_by_id(DeviceProperties.DHW_MODE, PropertyType.VALUE)

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
        self.async_set_item_by_id(DeviceProperties.DHW_TEMP, temperature)

    async def async_set_water_heater_operation_mode(self, operation_mode):
        self.async_set_item_by_id(
            DeviceProperties.DHW_MODE,
            self.get_item_by_id(
                DeviceProperties.DHW_MODE, PropertyType.OPT_TEXTS
            ).index(operation_mode),
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
