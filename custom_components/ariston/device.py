"""Device class for Ariston module."""
from __future__ import annotations

import logging

from typing import Any
from datetime import date

from .ariston import (
    AristonAPI,
    ConsumptionProperties,
    DeviceAttribute,
    DeviceFeatures,
    DeviceProperties,
    PropertyType,
)

_LOGGER = logging.getLogger(__name__)


class AristonDevice:
    """Class representing a physical device, it's state and properties."""

    def __init__(
        self,
        attributes: dict[str, Any],
        api: AristonAPI,
        extra_energy_features: bool,
        is_metric: bool = True,
    ) -> None:
        self.api = api
        self.attributes = attributes
        self.extra_energy_features = extra_energy_features
        self.umsys = "si" if is_metric else "us"

        self.location = "en-US"

        self.features = None
        self.consumptions_settings = None

        self.energy_account = None
        self.consumptions_sequences = None
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
            self.umsys,
        )

    async def async_update_energy(self) -> None:
        """Update the device energy settings from the cloud"""

        # k=1: heating k=2: water
        # p=1: 12*2 hours p=2: 7*1 day p=3: 15*2 days p=4: 12*? year
        # v: first element is the latest, last element is the newest"""
        self.consumptions_sequences = await self.api.async_get_consumptions_sequences(
            self.attributes[DeviceAttribute.GW_ID],
            self.features[DeviceFeatures.HAS_BOILER],
            self.features[DeviceFeatures.HAS_SLP],
        )

        if self.extra_energy_features:
            # These settings only for official clients
            self.consumptions_settings = await self.api.async_get_consumptions_settings(
                self.attributes[DeviceAttribute.GW_ID]
            )

            # Last month consumption in kwh
            self.energy_account = await self.api.async_get_energy_account(
                self.attributes[DeviceAttribute.GW_ID]
            )

    async def async_set_consumptions_settings(
        self, consumption_property: ConsumptionProperties, value: int
    ):
        """Set consumption settings"""
        new_settings = self.consumptions_settings.copy()
        new_settings[consumption_property] = value
        await self.api.async_set_consumptions_settings(
            self.attributes[DeviceAttribute.GW_ID], new_settings
        )
        self.consumptions_settings[consumption_property] = value

    def get_item_by_id(
        self, item_id: DeviceProperties, item_value: PropertyType, zone_number: int = 0
    ):
        """Get item attribute from data"""
        return [
            item.get(item_value, None)
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
            self.umsys,
        )
        for item in self.data["items"]:
            if item["id"] == item_id and item[PropertyType.ZONE] == zone_number:
                item[PropertyType.VALUE] = value
                break

    async def async_set_holiday(self, holiday_end: date):
        """Set holiday on device"""
        holiday_end_date = (
            None if holiday_end is None else holiday_end.strftime("%Y-%m-%dT00:00:00")
        )

        await self.api.async_set_holiday(
            self.attributes[DeviceAttribute.GW_ID],
            holiday_end_date,
        )

        for item in self.data["items"]:
            if item["id"] == DeviceProperties.HOLIDAY:
                item[PropertyType.VALUE] = False if holiday_end_date is None else True
                item[PropertyType.EXPIRES_ON] = (
                    None if holiday_end_date is None else holiday_end_date
                )
                break
