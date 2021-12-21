"""Device class for Ariston module."""
from __future__ import annotations

import logging

from typing import Any
from abc import ABC

from .ariston import (
    AristonAPI,
    DeviceAttribute,
    DeviceFeatures,
    DeviceProperties,
    PropertyType,
    ZoneAttribute,
)

_LOGGER = logging.getLogger(__name__)


class AristonData(ABC):
    """Abstract class for handling Ariston json data"""

    def __init__(self, device: AristonDevice, zone_number: int) -> None:
        self.device = device
        self.data = None
        self.zone_number = zone_number

    def get_item_by_id(self, item_id: DeviceProperties, item_value: PropertyType):
        """Get item attribute from data"""
        return [
            item[item_value]
            for item in self.data["items"]
            if item["id"] == item_id and item["zone"] == self.zone_number
        ][0]

    async def set_item_by_id(self, item_id: str, value: float):
        """Set item attribute on device"""
        current_value = self.get_item_by_id(item_id, PropertyType.VALUE)
        await self.device.api.async_set_property(
            self.device.attributes[DeviceAttribute.GW_ID],
            self.zone_number,
            self.device.features,
            item_id,
            value,
            current_value,
        )
        for item in self.data["items"]:
            if item["id"] == item_id:
                item[PropertyType.VALUE] = value


class AristonDevice(AristonData):
    """Class representing a physical device, it's state and properties."""

    def __init__(self, attributes: dict[str, Any], api: AristonAPI) -> None:
        super().__init__(self, 0)
        self.api = api
        self.attributes = attributes

        """Device properites"""
        self.location = "en-US"

        self.thermostats = []
        self.features = None

    async def async_get_features(self) -> None:
        """Get device features wrapper"""
        self.features = await self.api.async_get_features_for_device(
            self.attributes[DeviceAttribute.GW_ID]
        )
        thermostats = []
        for zone in self.features[DeviceFeatures.ZONES]:
            thermostats.append(Thermostat(self, zone))
        self.thermostats = thermostats

    async def async_update_state(self) -> None:
        """Update the device states from the cloud"""
        self.data = await self.api.async_get_properties(
            self.attributes[DeviceAttribute.GW_ID],
            self.features,
            self.location,
        )

        for thermostat in self.thermostats:
            thermostat.data = self.data

    def thermostat(self, zone: int) -> Thermostat:
        """Return a termostate by zone number"""
        for thermostat in self.thermostats:
            if thermostat.zone[ZoneAttribute.NUM] == zone:
                return thermostat
        return None


class Thermostat(AristonData):
    """Class representing a physical thermostat, it's state and properties."""

    def __init__(self, device: AristonDevice, zone: dict[str, Any]) -> None:
        super().__init__(device, zone[ZoneAttribute.NUM])
        self.zone = zone
