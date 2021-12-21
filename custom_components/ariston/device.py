"""Device class for Ariston module."""
from __future__ import annotations

import logging

from typing import Any

from .ariston import (
    AristonAPI,
    DeviceAttribute,
    DeviceProperties,
    PropertyType,
)

_LOGGER = logging.getLogger(__name__)


class AristonDevice:
    """Class representing a physical device, it's state and properties."""

    def __init__(self, attributes: dict[str, Any], api: AristonAPI) -> None:
        self.api = api
        self.attributes = attributes

        self.location = "en-US"

        self.features = None
        self.data = None

    async def async_get_features(self) -> None:
        """Get device features wrapper"""
        self.features = await self.api.async_get_features_for_device(
            self.attributes[DeviceAttribute.GW_ID]
        )

    async def async_update_state(self) -> None:
        """Update the device states from the cloud"""
        self.data = await self.api.async_get_properties(
            self.attributes[DeviceAttribute.GW_ID],
            self.features,
            self.location,
        )

    def get_item_by_id(
        self, item_id: DeviceProperties, item_value: PropertyType, zone_number: int = 0
    ):
        """Get item attribute from data"""
        return [
            item[item_value]
            for item in self.data["items"]
            if item["id"] == item_id and item[PropertyType.ZONE] == zone_number
        ][0]

    async def set_item_by_id(self, item_id: str, value: float, zone_number: int = 0):
        """Set item attribute on device"""
        current_value = self.get_item_by_id(item_id, PropertyType.VALUE, zone_number)
        await self.api.async_set_property(
            self.attributes[DeviceAttribute.GW_ID],
            zone_number,
            self.features,
            item_id,
            value,
            current_value,
        )
        for item in self.data["items"]:
            if item["id"] == item_id and item[PropertyType.ZONE] == zone_number:
                item[PropertyType.VALUE] = value
