"""Device class for Ariston module."""
from __future__ import annotations

import logging

from typing import Any
from ctypes import Array

from .ariston import (
    AristonAPI,
    DeviceAttribute,
    DeviceFeatures,
    DeviceProperties,
    PlantMode,
    PropertyType,
    ThermostatProperties,
    ZoneMode,
)

_LOGGER = logging.getLogger(__name__)


class AristonDevice:
    """Class representing a physical device, it's state and properties."""

    def __init__(self, device: dict[str, Any], api: AristonAPI) -> None:
        self.api = api

        """Device properites"""
        self.gw_id = device[DeviceAttribute.GW_ID]
        self.gw_serial = device[DeviceAttribute.GW_SERIAL]
        self.plant_name = device[DeviceAttribute.PLANT_NAME]
        self.gw_fw_ver = device[DeviceAttribute.GW_FW_VER]
        self.gw_sys_type = device[DeviceAttribute.GW_SYS_TYPE]
        self.model = device[DeviceAttribute.PLANT_NAME]
        self.location = "en-US"

        self.thermostats = []
        self.features: AristonDeviceFeatures = None
        self.data = None

        self.plant_mode: PlantMode = None
        self.plant_modes = []
        self.plant_mode_texts = []
        self.is_flame_on: int = None
        self.holiday = None
        self.outside_temp: float = None
        self.heating_circuit_pressure: float = None
        self.heating_circuit_pressure_unit: str = None
        self.ch_flow_setpoint_temp: int = None
        self.ch_flow_setpoint_temp_unit: str = None

        self.dhw_temp: float = None
        self.dhw_temp_min: float = None
        self.dhw_temp_max: float = None
        self.dhw_temp_step: float = None
        self.dhw_temp_unit: str = None
        self.dhw_mode = None
        self.dhw_modes = []
        self.dhw_mode_texts = []

    async def async_get_features(self) -> None:
        """Get device features wrapper"""
        self.features = AristonDeviceFeatures(
            await self.api.async_get_features_for_device(self.gw_id)
        )
        thermostats: Array[Thermostat] = []
        for zone in self.features.zones:
            thermostats.append(Thermostat(self, zone))
        self.thermostats = thermostats

    async def async_update_state(self) -> None:
        """Update the device states from the cloud"""
        self.data = await self.api.async_get_device_properties(
            self.gw_id, self.features.data, self.location
        )

        self.plant_mode = self.get_item_by_id(
            DeviceProperties.PLANT_MODE, PropertyType.VALUE
        )
        self.plant_modes = self.get_item_by_id(
            DeviceProperties.PLANT_MODE, PropertyType.OPTIONS
        )
        self.plant_mode_texts = self.get_item_by_id(
            DeviceProperties.PLANT_MODE, PropertyType.OPT_TEXTS
        )
        self.is_flame_on = self.get_item_by_id(
            DeviceProperties.IS_FLAME_ON, PropertyType.VALUE
        )
        self.ch_flow_setpoint_temp = self.get_item_by_id(
            DeviceProperties.CH_FLOW_SETPOINT_TEMP, PropertyType.VALUE
        )
        self.ch_flow_setpoint_temp_unit = self.get_item_by_id(
            DeviceProperties.CH_FLOW_SETPOINT_TEMP, PropertyType.UNIT
        )
        self.heating_circuit_pressure = self.get_item_by_id(
            DeviceProperties.HEATING_CIRCUIT_PRESSURE, PropertyType.VALUE
        )
        self.heating_circuit_pressure_unit = self.get_item_by_id(
            DeviceProperties.HEATING_CIRCUIT_PRESSURE, PropertyType.UNIT
        )

        if self.features.has_boiler:
            self.dhw_temp = self.get_item_by_id(
                DeviceProperties.DHW_TEMP, PropertyType.VALUE
            )
            self.dhw_temp_min = self.get_item_by_id(
                DeviceProperties.DHW_TEMP, PropertyType.MIN
            )
            self.dhw_temp_max = self.get_item_by_id(
                DeviceProperties.DHW_TEMP, PropertyType.MAX
            )
            self.dhw_temp_step = self.get_item_by_id(
                DeviceProperties.DHW_TEMP, PropertyType.STEP
            )
            self.dhw_temp_unit = self.get_item_by_id(
                DeviceProperties.DHW_TEMP, PropertyType.UNIT
            )
            self.dhw_mode = self.get_item_by_id(
                DeviceProperties.DHW_MODE, PropertyType.VALUE
            )
            self.dhw_modes = self.get_item_by_id(
                DeviceProperties.DHW_MODE, PropertyType.OPTIONS
            )
            self.dhw_mode_texts = self.get_item_by_id(
                DeviceProperties.DHW_MODE, PropertyType.OPT_TEXTS
            )

        for thermostat in self.thermostats:
            await thermostat.async_update_state()

    def thermostat(self, zone: int) -> Thermostat:
        """Return a termostate by zone number"""
        for thermostat in self.thermostats:
            if thermostat.zone == zone:
                return thermostat
        return None

    async def async_set_plant_mode(self, plant_mode: PlantMode):
        """Set plant mode wrapper"""
        await self.api.async_set_plant_mode(self.gw_id, plant_mode, self.plant_mode)
        self.plant_mode = plant_mode

    async def async_set_dhwtemp(self, temperature: float):
        """Set domestic hot water temperature wrapper"""
        await self.api.async_set_dhwtemp(self.gw_id, temperature, self.dhw_temp)
        self.dhw_temp = temperature

    def get_item_by_id(self, item_id: str, item_value: str):
        """Get item attribute from data"""
        return [
            item[item_value] for item in self.data["items"] if item["id"] == item_id
        ][0]

    async def set_item_by_id(self, item_id: str, value: float):
        """Set item attribute on device"""
        current_value = self.get_item_by_id(item_id, PropertyType.VALUE)
        await self.api.async_set_device_properties(
            self.gw_id, self.features.data, item_id, value, current_value
        )
        for item in self.data["items"]:
            if item["id"] == item_id:
                item["value"] = value


class Thermostat:
    """Class representing a physical thermostat, it's state and properties."""

    def __init__(self, device: AristonDevice, zone: int) -> None:
        self.device = device
        self.zone = zone["num"]

        self.data = None
        self.measured_temp: float = None
        self.measured_temp_unit: str = None
        self.measured_temp_decimals: int = None
        self.desired_temp: float = None
        self.comfort_temp: float = None
        self.comfort_temp_min: float = None
        self.comfort_temp_max: float = None
        self.comfort_temp_step: float = None
        self.mode: ZoneMode = None
        self.modes = []
        self.heat_request: int = None
        self.zone_economy_temp: float = None

    async def async_update_state(self) -> None:
        """Update the thermostat states from the cloud"""
        self.data = await self.device.api.async_update_thermostat(
            self.device.gw_id,
            self.zone,
            self.device.features.data,
            self.device.location,
        )

        self.measured_temp = self.get_item_by_id(
            ThermostatProperties.ZONE_MEASURED_TEMP, PropertyType.VALUE
        )
        self.measured_temp_unit = self.get_item_by_id(
            ThermostatProperties.ZONE_MEASURED_TEMP, PropertyType.UNIT
        )
        self.measured_temp_decimals = self.get_item_by_id(
            ThermostatProperties.ZONE_MEASURED_TEMP, PropertyType.DECIMALS
        )
        self.desired_temp = self.get_item_by_id(
            ThermostatProperties.ZONE_DESIRED_TEMP, PropertyType.VALUE
        )
        self.comfort_temp = self.get_item_by_id(
            ThermostatProperties.ZONE_COMFORT_TEMP, PropertyType.VALUE
        )
        self.comfort_temp_min = self.get_item_by_id(
            ThermostatProperties.ZONE_COMFORT_TEMP, PropertyType.MIN
        )
        self.comfort_temp_max = self.get_item_by_id(
            ThermostatProperties.ZONE_COMFORT_TEMP, PropertyType.MAX
        )
        self.comfort_temp_step = self.get_item_by_id(
            ThermostatProperties.ZONE_COMFORT_TEMP, PropertyType.STEP
        )
        self.mode = self.get_item_by_id(
            ThermostatProperties.ZONE_MODE, PropertyType.VALUE
        )
        self.modes = self.get_item_by_id(
            ThermostatProperties.ZONE_MODE, PropertyType.OPTIONS
        )
        self.heat_request = self.get_item_by_id(
            ThermostatProperties.ZONE_HEAT_REQUEST, PropertyType.VALUE
        )
        self.zone_economy_temp = self.get_item_by_id(
            ThermostatProperties.ZONE_ECONOMY_TEMP, PropertyType.VALUE
        )

    async def async_set_temperature(self, temperature: float):
        """Set comfort temperature wrapper"""
        await self.device.api.async_set_temperature(
            self.device.gw_id, self.zone, temperature, self.comfort_temp
        )
        self.comfort_temp = temperature

    async def async_set_mode(self, mode: ZoneMode):
        """Set zone mode wrapper"""
        await self.device.api.async_set_zone_mode(
            self.device.gw_id, self.zone, mode, self.mode
        )
        self.mode = mode

    def get_item_by_id(self, item_id: str, item_value: str):
        """Get item attribute from data"""
        return [
            item[item_value] for item in self.data["items"] if item["id"] == item_id
        ][0]


class AristonDeviceFeatures:
    """Class representing a device feature properties."""

    def __init__(self, features: dict[str, Any]) -> None:
        self.data = features
        self.has_boiler = features[DeviceFeatures.HAS_BOILER]
        self.zones = features[DeviceFeatures.ZONES]
        self.dhw_mode_changeable = features[DeviceFeatures.DHW_MODE_CHANGEABLE]
